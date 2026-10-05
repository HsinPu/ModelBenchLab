"""Data-only imports from allowlisted Hugging Face coding benchmarks."""

import hashlib
import io
import json
import random
import re
from functools import lru_cache
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/benchmarks/coding", tags=["benchmarks"])
BENCHMARKS = {
    "humaneval": {
        "repo": "openai/openai_humaneval",
        "name": "HumanEval",
        "license": "MIT",
        "revision": "7dce6050a7d6d172f3cc5c32aa97f52fa1a2e544",
        "path": "openai_humaneval/test-00000-of-00001.parquet",
    },
    "humanevalplus": {
        "repo": "evalplus/humanevalplus",
        "name": "HumanEval+",
        "license": "Apache-2.0",
        "revision": "d32357cf319e50e9c8d8dab5ea876c72b0fd321b",
        "path": "test.jsonl",
    },
}
MAX_BYTES = 20_000_000
SHA = re.compile(r"[0-9a-f]{40}\Z")


class CodingPreviewInput(BaseModel):
    benchmark: Literal["humaneval", "humanevalplus"]
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    limit: int | None = Field(default=20, ge=1, le=164)
    seed: int = Field(default=0, ge=0, le=2147483647)


def metadata(benchmark, revision="main"):
    spec = BENCHMARKS[benchmark]
    try:
        response = httpx.get(
            f"https://huggingface.co/api/datasets/{spec['repo']}/revision/{revision}",
            timeout=20,
            follow_redirects=False,
        )
        response.raise_for_status()
        data = response.json()
        if not SHA.fullmatch(data.get("sha", "")):
            raise ValueError("invalid commit")
        if spec["path"] not in {entry["rfilename"] for entry in data["siblings"]}:
            raise ValueError("unrecognized dataset layout")
        return {"revision": data["sha"], "last_modified": data.get("lastModified")}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(502, "無法確認官方 coding 題庫版本，請稍後重試") from error


@lru_cache(maxsize=8)
def load_rows(benchmark, revision):
    spec = BENCHMARKS[benchmark]
    metadata(benchmark, revision)
    url = f"https://huggingface.co/datasets/{spec['repo']}/resolve/{revision}/{spec['path']}"
    try:
        with httpx.stream("GET", url, timeout=30, follow_redirects=True) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("dataset too large")
                chunks.append(chunk)
        content = b"".join(chunks)
        if spec["path"].endswith(".parquet"):
            import pyarrow.parquet as pq

            rows = pq.read_table(io.BytesIO(content)).to_pylist()
        else:
            rows = [
                json.loads(line)
                for line in content.decode("utf-8").splitlines()
                if line.strip()
            ]
        if not 1 <= len(rows) <= 164:
            raise ValueError("unexpected question count")
        ids = set()
        for row in rows:
            if row["task_id"] in ids or not re.fullmatch(
                r"HumanEval/\d+", row["task_id"]
            ):
                raise ValueError("invalid task id")
            ids.add(row["task_id"])
            if not re.fullmatch(
                r"[A-Za-z_]\w{0,99}", row["entry_point"], flags=re.ASCII
            ):
                raise ValueError("invalid entry point")
            if (
                not 1 <= len(row["prompt"]) <= 18000
                or not 1 <= len(row["test"]) <= 1_000_000
            ):
                raise ValueError("invalid task size")
        return sorted(rows, key=lambda row: int(row["task_id"].split("/")[-1]))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            502, "無法解析官方 coding 題庫；檔案格式或大小不符合支援範圍"
        ) from error


@router.get("/{benchmark}")
def catalog(benchmark: Literal["humaneval", "humanevalplus"], latest: bool = False):
    spec = BENCHMARKS[benchmark]
    resolved = metadata(benchmark) if latest else {"revision": spec["revision"]}
    return {
        **spec,
        **resolved,
        "questions": 164,
        "source_url": f"https://huggingface.co/datasets/{spec['repo']}",
    }


@router.post("/preview")
def preview(body: CodingPreviewInput):
    spec = BENCHMARKS[body.benchmark]
    rows = load_rows(body.benchmark, body.revision)
    selected = (
        rows
        if body.limit is None
        else sorted(
            random.Random(body.seed).sample(rows, min(body.limit, len(rows))),
            key=lambda row: int(row["task_id"].split("/")[-1]),
        )
    )
    cases = []
    for row in selected:
        source = {
            "dataset": spec["repo"],
            "revision": body.revision,
            "split": "test",
            "task_id": row["task_id"],
            "license": spec["license"],
            "seed": body.seed,
            "url": f"https://huggingface.co/datasets/{spec['repo']}/blob/{body.revision}/{spec['path']}",
        }
        cases.append(
            {
                "title": f"{spec['name']} · {row['task_id']} · {row['entry_point']}",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Implement the following Python function. Return only complete Python code, "
                            "including the required imports and function definition. Do not include explanations.\n\n"
                            + row["prompt"]
                        ),
                    }
                ],
                "rule": {
                    "kind": "code",
                    "coding": {
                        "benchmark": body.benchmark,
                        "task_id": row["task_id"],
                        "entry_point": row["entry_point"],
                        "prompt": row["prompt"],
                        "tests": row["test"],
                        "tests_sha256": hashlib.sha256(
                            row["test"].encode()
                        ).hexdigest(),
                        "dataset_repo": spec["repo"],
                        "dataset_revision": body.revision,
                        "suite_version": "hf-tests-v1",
                    },
                },
                "tags": [spec["name"], "coding", "python"],
                "source": source,
            }
        )
    return {
        "name": f"{spec['name']} {body.revision[:12]} · Python · {len(cases)} 題",
        "cases": cases,
        "revision": body.revision,
        "available": len(rows),
        "license": spec["license"],
        "source_url": f"https://huggingface.co/datasets/{spec['repo']}",
    }
