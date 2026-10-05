"""Docker-only functional evaluation; never execute candidate code on the host."""

import ast
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/coding", tags=["coding"])
VERSION = "hf-tests-v1"
CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def runtime():
    try:
        server = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}"],
            capture_output=True,
            text=True,
            timeout=8,
            check=True,
            creationflags=CREATION_FLAGS,
        )
        if server.stdout.strip() != "linux":
            raise ValueError("Linux containers required")
        inspected = subprocess.run(
            [
                "docker",
                "image",
                "inspect",
                os.getenv("CODING_RUNNER_IMAGE", "modelbench-coding:1"),
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=True,
            creationflags=CREATION_FLAGS,
        )
        data = json.loads(inspected.stdout)[0]
        if (data["Config"].get("Labels") or {}).get("modelbench.coding.version") != "1":
            raise ValueError("runner version mismatch")
        return {
            "image_id": data["Id"],
            "runner_version": VERSION,
            "python": "3.12",
            "numpy": "2.2.6",
            "memory_mb": 512,
            "cpus": 1,
        }
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise HTTPException(
            409,
            "程式評分器尚未就緒；請啟動 Docker Linux 並執行 scripts/build-coding-runner.ps1",
        )


@router.get("/runner")
def runner_status():
    try:
        return {"available": True, "runtime": runtime()}
    except HTTPException as error:
        return {"available": False, "reason": error.detail}


def run_settings(cases, settings):
    if any(case["rule"]["kind"] == "code" for case in cases):
        if settings["repeats"] != 1:
            raise HTTPException(422, "第一版程式測試每題生成一次，請將重複次數設為 1")
        return {**settings, "coding_runtime": runtime()}
    return settings


def program_from_output(output, prompt, entry_point):
    if len(output) > 200000:
        raise ValueError("程式回答過長")
    fences = re.findall(r"```([^\n]*)\n(.*?)```", output, flags=re.S)
    if fences:
        if len(fences) != 1 or fences[0][0].strip().lower() not in ("", "python", "py"):
            raise ValueError("請回傳單一 Python 程式區塊")
        output = fences[0][1]
    # Complete programs stand alone (including legal __future__ imports).
    # Body-only continuations retain the original prompt's imports and indentation.
    combined = (
        output
        if re.search(r"(?m)^def\s+" + re.escape(entry_point) + r"\s*\(", output)
        else prompt + output
    )
    ast.parse(combined)
    return combined


def evaluate_code(output, spec, settings, cancelled=lambda: False):
    started = time.monotonic()
    base = {"kind": "code", "version": VERSION, "passed": None, "error": True}
    try:
        program = program_from_output(output, spec["prompt"], spec["entry_point"])
    except (ValueError, SyntaxError, RecursionError):
        return {
            **base,
            "passed": False,
            "error": False,
            "outcome": "syntax_error",
            "reason": "回答不是可辨識的 Python 程式或語法錯誤",
        }
    base.update(
        generated_code=program,
        program_sha256=hashlib.sha256(program.encode()).hexdigest(),
        tests_sha256=spec["tests_sha256"],
        runtime=settings.get("coding_runtime"),
    )
    environment = settings.get("coding_runtime") or {}
    image = environment.get("image_id", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        return {
            **base,
            "outcome": "runner_unavailable",
            "reason": "缺少固定評分環境，可重新評分",
        }
    name = "modelbench-code-" + uuid4().hex
    timeout = settings.get("code_timeout", 10)
    command = [
        "docker",
        "run",
        "--pull=never",
        "-i",
        "--name",
        name,
        "--network=none",
        "--ipc=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user=65534:65534",
        "--pids-limit=64",
        "--memory=512m",
        "--memory-swap=512m",
        "--cpus=1",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
        "--ulimit=nofile=128:128",
        image,
    ]
    process = None
    finished = threading.Event()
    captured = {}
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=CREATION_FLAGS,
        )

        def communicate():
            try:
                captured["streams"] = process.communicate(
                    json.dumps(
                        {
                            "program": program,
                            "tests": spec["tests"],
                            "entry_point": spec["entry_point"],
                            "timeout": timeout,
                        }
                    ).encode(),
                    timeout=timeout + 20,
                )
            except subprocess.TimeoutExpired:
                captured["timeout"] = True
            finally:
                finished.set()

        thread = threading.Thread(target=communicate, daemon=True)
        thread.start()
        while not finished.wait(0.2):
            if cancelled():
                return {**base, "outcome": "cancelled", "reason": "程式評分已取消"}
        if cancelled():
            return {**base, "outcome": "cancelled", "reason": "程式評分已取消"}
        if captured.get("timeout"):
            return {
                **base,
                "outcome": "runner_timeout",
                "reason": "評分器啟動或回應逾時，可重新評分",
            }
        stdout, _ = captured.get("streams", (b"", b""))
        if process.returncode == 137:
            inspected = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.OOMKilled}}", name],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=CREATION_FLAGS,
            )
            if inspected.stdout.strip() == "true":
                return {
                    **base,
                    "passed": False,
                    "error": False,
                    "outcome": "memory_limit",
                    "reason": "程式執行超過記憶體限制",
                }
        if process.returncode != 0 or len(stdout) > 4000:
            return {
                **base,
                "outcome": "runner_error",
                "reason": "隔離評分器執行失敗，可重新評分",
            }
        data = json.loads(stdout)
        reasons = {
            "passed": "通過全部程式測試",
            "wrong_answer": "程式輸出未通過測試",
            "syntax_error": "Python 語法錯誤",
            "runtime_error": "程式執行錯誤或提前退出",
            "time_limit": "程式執行超過時間限制",
            "suite_error": "測試套件執行失敗，可重新評分",
        }
        outcome = data["outcome"]
        if outcome not in reasons or data["passed"] not in (True, False, None):
            raise ValueError("invalid runner result")
        return {
            **base,
            "passed": data["passed"],
            "error": data["passed"] is None,
            "outcome": outcome,
            "reason": reasons[outcome],
            "latency_ms": round((time.monotonic() - started) * 1000),
        }
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return {
            **base,
            "outcome": "runner_error",
            "reason": "無法啟動或解析隔離評分器，可重新評分",
        }
    finally:
        if process is not None:
            # Only this task's randomly named container may be removed.
            try:
                subprocess.run(
                    ["docker", "rm", "-f", name],
                    capture_output=True,
                    timeout=8,
                    creationflags=CREATION_FLAGS,
                )
            except (OSError, subprocess.SubprocessError):
                pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
