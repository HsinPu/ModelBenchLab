"""Allowlisted BFCL V3 data-only imports, bounded and pinned per preview."""
import json
import random
from functools import lru_cache
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .bfcl import REPO, FIXED_REVISION, CATEGORIES, digest
from .schemas import Case

router = APIRouter(prefix='/api/benchmarks/bfcl', tags=['benchmarks'])
Category = Literal['simple', 'multiple', 'parallel', 'parallel_multiple', 'irrelevance']


class PreviewInput(BaseModel):
    revision: str = Field(pattern=r'^[0-9a-f]{40}$')
    categories: list[Category] = Field(min_length=1, max_length=5)
    limit: int | None = Field(default=20, ge=1, le=1000)
    seed: int = Field(default=0, ge=0, le=2147483647)


class ImportInput(PreviewInput):
    preview_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def metadata(revision='main'):
    try:
        response = httpx.get(f'https://huggingface.co/api/datasets/{REPO}/revision/{revision}', timeout=20)
        response.raise_for_status()
        data = response.json()
        import re
        if not re.fullmatch(r'[0-9a-f]{40}', data['sha']):
            raise ValueError('invalid SHA')
        files = {entry['rfilename'] for entry in data['siblings']}
        if not all(f'BFCL_v3_{category}.json' in files for category in CATEGORIES):
            raise ValueError('unexpected layout')
        return data['sha']
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, '無法確認官方 BFCL V3 題庫版本') from None


def read_jsonl(revision, path):
    try:
        chunks, size = [], 0
        with httpx.stream('GET', f'https://huggingface.co/datasets/{REPO}/resolve/{revision}/{path}', timeout=30, follow_redirects=True) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 5_000_000:
                    raise ValueError('file too large')
                chunks.append(chunk)
        lines = b''.join(chunks).decode().splitlines()
        if len(lines) > 2000:
            raise ValueError('too many rows')
        return [json.loads(line) for line in lines if line.strip()]
    except (httpx.HTTPError, ValueError, UnicodeError):
        raise HTTPException(502, 'BFCL 檔案下載或格式驗證失敗') from None


@lru_cache(maxsize=20)
def load_rows(revision, category):
    metadata(revision)
    rows = read_jsonl(revision, f'BFCL_v3_{category}.json')
    answers = {} if category == 'irrelevance' else {
        row['id']: row['ground_truth'] for row in read_jsonl(revision, f'possible_answer/BFCL_v3_{category}.json')
    }
    ids = [row['id'] for row in rows]
    if not rows or len(ids) != len(set(ids)) or (category != 'irrelevance' and set(ids) != set(answers)):
        raise HTTPException(502, 'BFCL 題目與答案無法完整對應')
    return [(row, answers.get(row['id'], [])) for row in rows]


@router.get('')
def catalog(latest: bool = False):
    return {'revision': metadata() if latest else FIXED_REVISION,
            'release': 'BFCL V3', 'categories': CATEGORIES, 'repo': REPO}


def build_preview(body: PreviewInput):
    cases, available, counts = [], 0, {}
    for category in CATEGORIES:
        if category not in body.categories:
            continue
        rows = load_rows(body.revision, category)
        available += len(rows)
        selected = rows if body.limit is None else random.Random(f'{body.seed}:{category}').sample(rows, min(body.limit, len(rows)))
        counts[category] = len(selected)
        for row, answer in sorted(selected, key=lambda pair: pair[0]['id']):
            try:
                if len(row['question']) != 1:
                    raise ValueError('not single turn')
                spec = {'category': category, 'task_id': row['id'], 'functions': row['function'],
                        'answers': answer, 'dataset_repo': REPO, 'dataset_revision': body.revision,
                        'data_sha256': digest({'functions': row['function'], 'answers': answer})}
                case = Case.model_validate({'title': f"BFCL V3 · {row['id']}", 'messages': row['question'][0],
                    'rule': {'kind': 'tool_call', 'bfcl': spec}, 'tags': ['BFCL V3', 'tool_call', category],
                    'source': {'dataset': REPO, 'revision': body.revision, 'split': category, 'task_id': row['id'],
                               'seed': body.seed, 'license': 'Apache-2.0',
                               'url': f'https://huggingface.co/datasets/{REPO}/blob/{body.revision}/BFCL_v3_{category}.json'}})
                cases.append(case.model_dump(by_alias=True))
            except (ValueError, KeyError, TypeError):
                raise HTTPException(502, 'BFCL 題目規格不支援；未建立題庫') from None
    if len(cases) > 1000:
        # Use the existing immutable bundle mechanism for the complete 1240 questions.
        if len(cases) > 10000:
            raise HTTPException(422, '題數超過 BFCL 匯入限制')
    return {'name': f'BFCL V3 {body.revision[:12]} · {len(cases)} 題', 'cases': cases,
            'revision': body.revision, 'available': available, 'counts': counts,
            'import_spec': body.model_dump(include={'revision', 'categories', 'limit', 'seed'}), 'preview_sha256': digest(cases),
            'license': 'Apache-2.0', 'source_url': f'https://huggingface.co/datasets/{REPO}'}


@router.post('/preview')
def preview(body: PreviewInput):
    data = build_preview(body)
    return {**data, 'cases': [{**case, 'rule': {**case['rule'], 'bfcl': {
        key: value for key, value in case['rule']['bfcl'].items() if key != 'answers'
    }}} for case in data['cases']]}


@router.post('/import', status_code=201)
def import_preview(body: ImportInput):
    data = build_preview(PreviewInput.model_validate(body.model_dump()))
    if digest(data['cases']) != body.preview_sha256:
        raise HTTPException(409, '預覽內容已變動，請重新預覽')
    # Reconstruct on the server: browser JSON rewrites 1.0 to 1 and may lose
    # large-number precision. Never accept round-tripped reference answers.
    from .main import create_dataset, create_dataset_batch
    from .schemas import DatasetInput, DatasetBundleInput
    if len(data['cases']) > 1000:
        return create_dataset_batch(DatasetBundleInput(name=data['name'], cases=data['cases']))
    return create_dataset(DatasetInput(name=data['name'], cases=data['cases']))
