"""Import a TMMLU+ split pinned to a tag or resolved repository commit."""

import csv
import io
import random
import re
from functools import lru_cache
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/benchmarks/tmmluplus", tags=["benchmarks"])
REVISION = "v1.1"
BASE_URL = "https://huggingface.co/datasets/ikala/tmmluplus"
API_URL = "https://huggingface.co/api/datasets/ikala/tmmluplus"
MAX_CSV_BYTES = 5_000_000
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
SUBJECT_PATTERN = re.compile(r"[a-z0-9_()]{1,100}\Z")

# Pinned to the 66 configurations listed in the publisher's v1.1 dataset card.
SUBJECTS = tuple(
    """engineering_math dentistry traditional_chinese_medicine_clinical_medicine
    clinical_psychology technical culinary_skills mechanical logic_reasoning
    real_estate general_principles_of_law finance_banking anti_money_laundering
    ttqav2 marketing_management business_management organic_chemistry
    advance_chemistry physics secondary_physics human_behavior
    national_protection jce_humanities politic_science agriculture
    official_document_management financial_analysis pharmacy
    educational_psychology statistics_and_machine_learning management_accounting
    introduction_to_law computer_science veterinary_pathology accounting
    fire_science optometry insurance_studies pharmacology taxation trust_practice
    geography_of_taiwan physical_education auditing administrative_law
    education_(profession_level) economics veterinary_pharmacology nautical_science
    occupational_therapy_for_psychological_disorders basic_medical_science
    macroeconomics trade chinese_language_and_literature tve_design
    junior_science_exam junior_math_exam junior_chinese_exam junior_social_studies
    tve_mathematics tve_chinese_language tve_natural_sciences junior_chemistry music
    education three_principles_of_people taiwanese_hokkien""".split()
)


class PreviewInput(BaseModel):
    subject: str
    revision: str = Field(default=REVISION, pattern=r"^(v1\.1|[0-9a-f]{40})$")
    split: Literal["validation", "test"] = "validation"
    limit: int | None = Field(default=50, ge=1, le=1000)
    csv_text: str | None = Field(default=None, max_length=MAX_CSV_BYTES)


def source_url(subject: str, split: str, revision: str = REVISION) -> str:
    suffix = "val" if split == "validation" else "test"
    return f"{BASE_URL}/blob/{revision}/data/{subject}_{suffix}.csv"


def download_csv(subject: str, split: str, revision: str = REVISION) -> str:
    suffix = "val" if split == "validation" else "test"
    url = f"{BASE_URL}/resolve/{revision}/data/{subject}_{suffix}.csv"
    try:
        with httpx.stream("GET", url, timeout=20, follow_redirects=True) as response:
            response.raise_for_status()
            chunks = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_CSV_BYTES:
                    raise HTTPException(502, "TMMLU+ 原始檔案超過大小限制")
                chunks.append(chunk)
        return b"".join(chunks).decode("utf-8-sig")
    except (httpx.HTTPError, UnicodeError) as error:
        raise HTTPException(502, "無法下載 TMMLU+ 題目，請稍後重試或改用 CSV 檔案匯入") from error


def convert_csv(text: str, subject: str, split: str, limit: int | None, imported_from: str, revision: str = REVISION):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or not {"question", "A", "B", "C", "D", "answer"}.issubset(reader.fieldnames):
        raise HTTPException(422, "CSV 欄位需包含 question、A、B、C、D、answer")
    rows = []
    for row_number, row in enumerate(reader, start=2):
        question = (row.get("question") or "").strip()
        options = [(row.get(letter) or "").strip() for letter in "ABCD"]
        answer = (row.get("answer") or "").strip().upper()
        if not question or any(not option for option in options) or answer not in ("A", "B", "C", "D"):
            raise HTTPException(422, f"CSV 第 {row_number} 列的題目、選項或答案無效")
        content = (
            question
            + "\n\n"
            + "\n".join(f"{letter}. {option}" for letter, option in zip("ABCD", options))
            + "\n\n請只回答一個選項字母（A、B、C 或 D），不要解釋。"
        )
        if len(content) > 20000:
            raise HTTPException(422, f"CSV 第 {row_number} 列超過題目長度限制")
        rows.append((row_number, content, answer))
    if not rows:
        raise HTTPException(422, "CSV 沒有可匯入的題目")
    selected = rows if limit is None else sorted(random.Random(0).sample(rows, min(limit, len(rows))))
    cases = [
        {
            "title": f"TMMLU+ {subject} #{row_number - 1}",
            "messages": [{"role": "user", "content": content}],
            "rule": {"kind": "choice", "expected": answer},
            "tags": ["TMMLU+", revision, subject, split],
            "source": {
                "dataset": "ikala/tmmluplus",
                "revision": revision,
                "subject": subject,
                "split": split,
                "row": row_number,
                "url": source_url(subject, split, revision),
                "license": "MIT",
                "imported_from": imported_from,
            },
        }
        for row_number, content, answer in selected
    ]
    return {
        "name": f"TMMLU+ {revision[:12]} · {subject} · {split} · {len(cases)} 題",
        "cases": cases,
        "revision": revision,
        "available": len(rows),
        "source_url": source_url(subject, split, revision),
        "license": "MIT",
        "imported_from": imported_from,
    }


def dataset_metadata(revision: str) -> dict:
    try:
        response = httpx.get(f"{API_URL}/revision/{revision}", timeout=15, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(502, "無法取得 TMMLU+ 最新版本資訊，請稍後重試") from error
    if not isinstance(data, dict) or data.get("id") != "ikala/tmmluplus" or not SHA_PATTERN.fullmatch(str(data.get("sha", ""))):
        raise HTTPException(502, "TMMLU+ 版本資訊格式不正確")
    siblings = data.get("siblings")
    if not isinstance(siblings, list):
        raise HTTPException(502, "TMMLU+ 科目清單格式不正確")
    files = {item.get("rfilename") for item in siblings if isinstance(item, dict)}
    subjects = tuple(sorted({
        path[5:-8] for path in files
        if isinstance(path, str) and path.startswith("data/") and path.endswith("_val.csv")
        and SUBJECT_PATTERN.fullmatch(path[5:-8]) and f"data/{path[5:-8]}_test.csv" in files
    }))
    if not subjects:
        raise HTTPException(502, "TMMLU+ 最新版本沒有可匯入的科目")
    return {"revision": data["sha"], "subjects": subjects, "source_url": BASE_URL,
            "license": "MIT", "last_modified": data.get("lastModified")}


@lru_cache(maxsize=8)
def pinned_subjects(revision: str) -> tuple[str, ...]:
    metadata = dataset_metadata(revision)
    if metadata["revision"] != revision:
        raise HTTPException(502, "TMMLU+ 版本與指定的 commit 不一致")
    return metadata["subjects"]


@router.get("")
def catalog():
    return {"revision": REVISION, "subjects": SUBJECTS, "source_url": BASE_URL, "license": "MIT"}


@router.get("/latest")
def latest():
    return dataset_metadata("main")


@router.post("/preview")
def preview(body: PreviewInput):
    if body.csv_text is not None and body.revision != REVISION:
        raise HTTPException(422, "本機 CSV 無法驗證為最新官方版本；請選擇 v1.1 或直接從官方下載")
    subjects = SUBJECTS if body.revision == REVISION else pinned_subjects(body.revision)
    if body.subject not in subjects:
        raise HTTPException(422, "不支援此 TMMLU+ 科目")
    text = body.csv_text if body.csv_text is not None else download_csv(body.subject, body.split, body.revision)
    return convert_csv(
        text, body.subject, body.split, body.limit,
        "uploaded_csv" if body.csv_text is not None else "official_download",
        body.revision,
    )
