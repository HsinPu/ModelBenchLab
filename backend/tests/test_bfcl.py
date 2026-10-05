import copy
import json

import httpx
import pytest
from sqlalchemy import select
from app.bfcl import digest, evaluate_tools, runtime, tools_for, CATEGORIES
from app import bfcl_benchmarks
from app.db import Session, Item, Run
from app.execution import execute_item
from app.providers import generate
from app.schemas import BfclRule


def spec(category='simple'):
    functions = [{'name': 'math.add', 'description': 'Add two numbers', 'parameters': {
        'type': 'dict', 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'integer'}}, 'required': ['a', 'b']}}]
    answers = [] if category == 'irrelevance' else [{'math.add': {'a': [2], 'b': [3]}}]
    return {'category': category, 'task_id': category + '_0', 'functions': functions, 'answers': answers,
            'dataset_repo': bfcl_benchmarks.REPO, 'dataset_revision': 'a' * 40,
            'data_sha256': digest({'functions': functions, 'answers': answers})}


def call(a=2, b=3):
    return {'name': 'bfcl_0', 'arguments': json.dumps({'a': a, 'b': b})}


@pytest.mark.parametrize('calls,passed', [([call()], True), ([call(9)], False),
    ([call(True)], False), ([], False), ([call(), call()], False),
    ([{'name': 'bfcl_0', 'arguments': '{broken'}], False),
    ([{'name': 'bfcl_0', 'arguments': '{"a":NaN,"b":3}'}], False),
    ([{'name': 'invented', 'arguments': '{}'}], False)])
def test_official_python_comparison(calls, passed):
    result = evaluate_tools({'tool_calls': calls}, spec(), {'bfcl_runtime': runtime()})
    assert result['passed'] is passed
    assert not result.get('error')


def test_irrelevance_and_pinned_runtime():
    assert evaluate_tools({'tool_calls': []}, spec('irrelevance'), {'bfcl_runtime': runtime()})['passed']
    assert not evaluate_tools({'tool_calls': [call()]}, spec('irrelevance'), {'bfcl_runtime': runtime()})['passed']
    assert evaluate_tools({}, spec(), {'bfcl_runtime': {}})['error']


def test_alias_and_digest():
    s = spec()
    assert tools_for(s)[0]['function']['name'] == 'bfcl_0'
    assert tools_for(s)[0]['function']['parameters']['type'] == 'object'
    BfclRule.model_validate(s)
    s['answers'][0]['math.add']['a'] = [9]
    with pytest.raises(ValueError):
        BfclRule.model_validate(s)


def test_parameter_named_type_is_not_schema_type():
    s = spec()
    s['functions'][0]['parameters']['properties']['type'] = {'type': 'string'}
    assert tools_for(s)[0]['function']['parameters']['properties']['type']['type'] == 'string'


def test_schema_conversion_preserves_literals_and_nested_schemas():
    s = spec()
    literal = {'type': 'dict', 'nested': [{'type': 'any'}, {'type': 'float'}]}
    params = s['functions'][0]['parameters']
    params['properties']['config'] = {'type': 'dict', 'enum': [literal],
                                     'const': literal, 'default': literal, 'examples': [literal],
                                     'properties': {'type': {'type': 'string'}, 'value': {'type': 'float'}}}
    params['$defs'] = {'type': {'type': 'tuple', 'items': {'type': 'float'}}}
    params['allOf'] = [{'properties': {'extra': {'type': 'any'}}}]
    params['additionalProperties'] = False
    params['x-data'] = literal
    before = copy.deepcopy(s)
    converted = tools_for(s)[0]['function']['parameters']
    config = converted['properties']['config']
    assert config['type'] == 'object'
    assert config['properties']['value']['type'] == 'number'
    assert config['properties']['type']['type'] == 'string'
    for key in ('const', 'default'):
        assert config[key] == literal
    for key in ('enum', 'examples'):
        assert config[key] == [literal]
    assert converted['$defs']['type'] == {'type': 'array', 'items': {'type': 'number'}}
    assert converted['allOf'][0]['properties']['extra'] == {}
    assert converted['additionalProperties'] is False
    assert converted['x-data'] == literal
    assert s == before
    config['default']['type'] = 'changed'
    assert s == before


@pytest.mark.parametrize('value', [10 ** 400, -(10 ** 400)])
def test_numeric_overflow_is_incorrect_answer(value):
    s = spec()
    s['functions'][0]['parameters']['properties']['a']['type'] = 'float'
    s['answers'][0]['math.add']['a'] = [2.0]
    result = evaluate_tools({'tool_calls': [call(value)]}, s, {'bfcl_runtime': runtime()})
    assert result['passed'] is False
    assert result['error'] is False
    assert result['error_type'] == 'numeric_range'
    assert evaluate_tools({'tool_calls': [call(2)]}, s, {'bfcl_runtime': runtime()})['passed']


def test_checker_failure_remains_separate_from_wrong_answer(monkeypatch):
    def broken(*args):
        raise RuntimeError('checker unavailable')
    monkeypatch.setattr('app.bfcl.ast_checker', broken)
    result = evaluate_tools({'tool_calls': [call()]}, spec(), {'bfcl_runtime': runtime()})
    assert result['passed'] is None
    assert result['error'] is True


def test_single_bundle_part_cannot_receive_formal_ranking(client, monkeypatch):
    from app.db import Dataset
    monkeypatch.setattr('app.main.dispatch', lambda ids: None)
    case = {'title': 'BFCL', 'messages': [{'role': 'user', 'content': 'Add'}],
            'rule': {'kind': 'tool_call', 'bfcl': spec()}}
    bundle = client.post('/api/datasets/batch', json={'name': 'BFCL bundle', 'cases': [case] * 1001})
    assert bundle.status_code == 201, bundle.text
    with Session() as db:
        dataset_id = db.scalar(select(Dataset.id).where(Dataset.bundle_index == 1))
    model = client.post('/api/models', json={'name': 'Demo', 'provider': 'demo', 'model': 'demo-stable'}).json()['id']
    prompt = client.post('/api/prompts', json={'name': 'BFCL', 'text': ''}).json()['id']
    response = client.post('/api/runs', json={'name': 'subset', 'dataset_id': dataset_id,
                                           'model_ids': [model], 'prompt_id': prompt})
    assert response.status_code == 201, response.text
    run_id = response.json()['id']
    with Session() as db:
        db.get(Run, run_id).status = 'completed'
        for item in db.scalars(select(Item).where(Item.run_id == run_id)):
            item.status = 'completed'
            item.result = {'evaluation': {'passed': True}}
        db.commit()
    ranking = client.get(f'/api/runs/{run_id}/dataset-ranking').json()
    assert ranking['question_count'] == 1001
    assert ranking['models'] == []


def test_parallel_order_and_duplicate_calls():
    s = spec('parallel')
    s['answers'] = [{'math.add': {'a': [2], 'b': [3]}}, {'math.add': {'a': [4], 'b': [5]}}]
    assert evaluate_tools({'tool_calls': [call(4, 5), call()]}, s, {'bfcl_runtime': runtime()})['passed']
    assert not evaluate_tools({'tool_calls': [call(), call()]}, s, {'bfcl_runtime': runtime()})['passed']


def test_capability_not_silently_dropped():
    from fastapi import HTTPException
    from app.bfcl import run_settings
    case = {'rule': {'kind': 'tool_call'}}
    with pytest.raises(HTTPException):
        run_settings([case], {'repeats': 1}, [{'provider': 'openrouter', 'name': 'text only', 'catalog': {'supported_parameters': ['temperature']}}])


def test_native_payload_and_empty_text_tool_response():
    s = spec()
    def handler(request):
        body = json.loads(request.content)
        assert body['tools'] == tools_for(s)
        assert body['tool_choice'] == 'auto'
        assert 'answers' not in str(body)
        return httpx.Response(200, json={'choices': [{'message': {'content': None, 'tool_calls': [
            {'type': 'function', 'function': call()}]}, 'finish_reason': 'tool_calls'}],
            'usage': {'cost': 0.002, 'completion_tokens': 20}, 'model': 'actual-model'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate({'provider': 'openrouter', 'model': 'test', 'catalog': None},
                          [{'role': 'user', 'content': 'Add 2 and 3'}],
                          {'temperature': 0, 'max_tokens': 100, 'timeout': 5, '_bfcl': s},
                          'sk-test-not-real', client)
    assert result['tool_calls'] == [call()]
    assert result['cost'] is not None
    assert result['resolved_model'] == 'actual-model'


def test_preview_sampling_and_answers_not_in_messages(client, monkeypatch):
    def rows(revision, category):
        return [({'id': f'{category}_{i}', 'question': [[{'role': 'user', 'content': f'Add {i}'}]],
                  'function': spec()['functions']}, spec(category)['answers']) for i in range(5)]
    monkeypatch.setattr(bfcl_benchmarks, 'load_rows', rows)
    body = {'revision': 'a' * 40, 'categories': list(CATEGORIES), 'limit': 2, 'seed': 3}
    p = client.post('/api/benchmarks/bfcl/preview', json=body)
    assert p.status_code == 200, p.text
    assert p.json() == client.post('/api/benchmarks/bfcl/preview', json=body).json()
    assert len(p.json()['cases']) == 10
    assert all('answers' not in str(c['messages']) for c in p.json()['cases'])
    assert all('answers' not in c['rule']['bfcl'] for c in p.json()['cases'])
    request = {**p.json()['import_spec'], 'preview_sha256': p.json()['preview_sha256']}
    assert client.post('/api/benchmarks/bfcl/import', json=request).status_code == 201
    request['preview_sha256'] = '0' * 64
    assert client.post('/api/benchmarks/bfcl/import', json=request).status_code == 409


def test_server_import_keeps_float_and_large_integer_precision(client, monkeypatch):
    from app.db import Dataset
    s = spec()
    s['functions'][0]['parameters']['properties']['a']['type'] = 'float'
    answer = [{'math.add': {'a': [1.0], 'b': [9007199254740993]}}]
    monkeypatch.setattr(bfcl_benchmarks, 'load_rows', lambda *args: [({'id': 'simple_0',
        'question': [[{'role': 'user', 'content': 'Add numbers'}]], 'function': s['functions']}, answer)])
    data = client.post('/api/benchmarks/bfcl/preview', json={'revision': 'a' * 40, 'categories': ['simple']}).json()
    response = client.post('/api/benchmarks/bfcl/import', json={**data['import_spec'], 'preview_sha256': data['preview_sha256']})
    assert response.status_code == 201, response.text
    with Session() as db:
        rule = db.get(Dataset, response.json()['id']).cases[0]['rule']['bfcl']
        assert type(rule['answers'][0]['math.add']['a'][0]) is float
        assert rule['answers'][0]['math.add']['b'][0] == 9007199254740993
        BfclRule.model_validate(rule)


def test_server_import_full_bundle(client, monkeypatch):
    monkeypatch.setattr(bfcl_benchmarks, 'load_rows', lambda *args: [({'id': f'simple_{i}',
        'question': [[{'role': 'user', 'content': 'Add'}]], 'function': spec()['functions']}, spec()['answers']) for i in range(1001)])
    body = {'revision': 'a' * 40, 'categories': ['simple'], 'limit': None}
    data = client.post('/api/benchmarks/bfcl/preview', json=body).json()
    response = client.post('/api/benchmarks/bfcl/import', json={**data['import_spec'], 'preview_sha256': data['preview_sha256']})
    assert response.status_code == 201, response.text
    assert response.json()['cases'] == 1001
    assert response.json()['batches'] == 2


def create(client, **settings):
    model = client.post('/api/models', json={'name': 'Mock BFCL', 'provider': 'demo', 'model': 'demo-stable'}).json()['id']
    case = {'title': 'BFCL', 'messages': [{'role': 'user', 'content': 'Add 2 and 3'}],
            'rule': {'kind': 'tool_call', 'bfcl': spec()}}
    dataset = client.post('/api/datasets', json={'name': 'BFCL', 'cases': [case]}).json()['id']
    prompt = client.post('/api/prompts', json={'name': 'BFCL', 'text': ''}).json()['id']
    return client.post('/api/runs', json={'name': 'BFCL', 'dataset_id': dataset, 'model_ids': [model], 'prompt_id': prompt, **settings})


def test_worker_reevaluate_and_ranking(client, monkeypatch):
    response = create(client)
    assert response.status_code == 201, response.text
    run_id = response.json()['id']
    calls = []
    def fake(config, messages, settings, key):
        assert settings['_bfcl']['answers']
        assert 'answers' not in str(messages)
        calls.append(1)
        return {'output': 'calls', 'tool_calls': [call()], 'latency_ms': 1, 'demo': True}
    monkeypatch.setattr('app.execution.generate', fake)
    with Session() as db:
        item_id = db.scalar(select(Item.id).where(Item.run_id == run_id))
        assert db.get(Run, run_id).snapshot['version'] == 4
    execute_item(item_id)
    execute_item(item_id)  # duplicate delivery
    detail = client.get('/api/runs/' + run_id).json()
    assert 'answers' not in detail['snapshot']['cases'][0]['rule']['bfcl']
    assert detail['items'][0]['result']['evaluation']['passed']
    ranking = client.get(f'/api/runs/{run_id}/dataset-ranking').json()['models'][0]
    assert ranking['ranked']
    assert ranking['categories']['simple'] == {'graded': 1, 'passed': 1}
    assert client.post('/api/items/' + item_id + '/evaluate', json={}).status_code == 200
    execute_item(item_id)
    assert len(calls) == 1
    with Session() as db:
        run = db.get(Run, run_id)
        snapshot = copy.deepcopy(run.snapshot)
        snapshot['settings']['bfcl_runtime']['version'] = 'changed'
        run.snapshot = snapshot
        db.commit()
    assert client.post('/api/items/' + item_id + '/evaluate', json={}).status_code == 200
    execute_item(item_id)
    assert len(calls) == 1
    assert client.get('/api/runs/' + run_id).json()['items'][0]['result']['evaluation']['error']


def test_repeats_rejected(client):
    assert create(client, repeats=2).status_code == 422


def test_force_cancel_discards_late_tool_answer(client, monkeypatch):
    run_id = create(client).json()['id']
    with Session() as db:
        item_id = db.scalar(select(Item.id).where(Item.run_id == run_id))
    def late(*args):
        assert client.post(f'/api/runs/{run_id}/force-cancel', json={}).status_code == 200
        return {'output': 'calls', 'tool_calls': [call()], 'latency_ms': 1, 'demo': True}
    monkeypatch.setattr('app.execution.generate', late)
    execute_item(item_id)
    detail = client.get('/api/runs/' + run_id).json()
    assert detail['status'] == 'cancelled'
    assert detail['items'][0]['status'] == 'cancelled'
    assert detail['items'][0]['result'] is None


def test_malformed_tool_shape_keeps_reported_charge():
    from app.providers import ProviderError
    def handler(request):
        return httpx.Response(200, json={'choices': [{'message': {'content': None,
            'tool_calls': [{'type': 'function', 'function': {'name': None, 'arguments': '{}'}}]}}],
            'usage': {'cost': 0.012}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as error:
            generate({'provider': 'openrouter', 'model': 'test'}, [{'role': 'user', 'content': 'Add'}],
                     {'temperature': 0, 'max_tokens': 100, 'timeout': 5, '_bfcl': spec()}, 'sk-test-not-real', client)
    assert error.value.diagnostics['reported_cost_usd'] == '0.012'
