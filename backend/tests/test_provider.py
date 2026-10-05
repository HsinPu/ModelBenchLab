import asyncio
import json
import httpx
import pytest
from app.providers import generate, ProviderError, _cancellable_post

CONFIG={'provider':'openai-compatible','endpoint':'https://model.example/v1','model':'test'}
SETTINGS={'timeout':5,'temperature':0,'max_tokens':10}


def test_force_cancel_aborts_pending_http_request(monkeypatch):
    real_client = httpx.AsyncClient
    started = asyncio.Event()
    interrupted = asyncio.Event()
    cancelled = {'value': False}

    async def handle(_):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            interrupted.set()
            raise
        return httpx.Response(200, json={'choices': [{'message': {'content': 'late'}}]})

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(
        'app.providers.httpx.AsyncClient',
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    async def run():
        async def request_cancel():
            await started.wait()
            cancelled['value'] = True

        trigger = asyncio.create_task(request_cancel())
        with pytest.raises(ProviderError) as error:
            await _cancellable_post('https://model.example/v1', {}, {}, 5, lambda: cancelled['value'])
        await trigger
        assert error.value.code == 'force_cancelled'
        assert interrupted.is_set()

    asyncio.run(run())

def test_adapter_request_and_usage():
    def handle(request):
        assert str(request.url)=='https://model.example/v1/chat/completions'
        assert request.headers['authorization']=='Bearer private'
        return httpx.Response(200,json={'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}],'usage':{'prompt_tokens':2,'completion_tokens':1}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result=generate(CONFIG,[{'role':'user','content':'hi'}],SETTINGS,'private',client)
    assert result['output']=='ok' and result['output_tokens']==1

def test_error_does_not_leak_body():
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(429,text='secret-private'))) as client:
        with pytest.raises(ProviderError) as e:
            generate(CONFIG,[],SETTINGS,'private',client)
    assert e.value.retryable
    assert 'private' not in str(e.value)


@pytest.mark.parametrize('payload',[None,{}, {'choices':[]}])
def test_malformed_payload_is_sanitized(payload):
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload))) as client:
        with pytest.raises(ProviderError):
            generate(CONFIG,[],SETTINGS,'private',client)


@pytest.mark.parametrize('choice, expected', [
    ({'message': {'content': None}, 'finish_reason': 'length'}, '長度限制'),
    ({'message': {'content': ''}, 'finish_reason': 'stop'}, '空白文字'),
    ({'message': {'content': [{'type': 'image_url'}]}, 'finish_reason': 'stop'}, '非文字內容'),
])
def test_no_text_response_has_actionable_error(choice, expected):
    response = {
        'model': 'maker/resolved', 'choices': [choice],
        'usage': {'completion_tokens': 8, 'completion_tokens_details': {'reasoning_tokens': 5}},
    }
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))) as client:
        with pytest.raises(ProviderError, match=expected) as error:
            generate(CONFIG, [], SETTINGS, 'private', client)
    assert 'private' not in str(error.value)
    if error.value.code == 'no_text_output':
        assert error.value.diagnostics['finish_reason'] == choice['finish_reason']
        assert error.value.diagnostics['completion_tokens'] == 8
        assert error.value.diagnostics['reasoning_tokens'] == 5
        assert error.value.diagnostics['resolved_model'] == 'maker/resolved'
        assert error.value.diagnostics['requested_max_tokens'] == 10


def test_openrouter_no_text_preserves_reported_cost_without_response_body():
    response = {
        'choices': [{'message': {'content': ''}, 'finish_reason': 'length'}],
        'usage': {'cost': 0.00005, 'completion_tokens': 10},
    }
    config = {**CONFIG, 'provider': 'openrouter'}
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))) as client:
        with pytest.raises(ProviderError) as error:
            generate(config, [], SETTINGS, 'private', client)
    assert error.value.code == 'no_text_output'
    assert error.value.diagnostics['reported_cost_usd'] == '0.00005'


@pytest.mark.parametrize('provider, effort, field', [
    ('openrouter', 'low', 'reasoning'),
    ('openrouter', 'ultra', 'reasoning'),
    ('openai-compatible', 'xhigh', 'reasoning_effort'),
])
def test_reasoning_effort_is_sent_as_selected(provider, effort, field):
    def handle(request):
        payload = json.loads(request.content)
        if field == 'reasoning':
            assert payload['reasoning'] == {'effort': effort}
            assert 'reasoning_effort' not in payload
        else:
            assert payload['reasoning_effort'] == effort
            assert 'reasoning' not in payload
        return httpx.Response(200, json={'choices': [{'message': {'content': 'OK'}}]})

    config = {**CONFIG, 'provider': provider, 'reasoning_effort': effort}
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert generate(config, [], SETTINGS, 'private', client)['output'] == 'OK'


def test_rejected_reasoning_effort_has_helpful_error():
    config = {**CONFIG, 'provider': 'openrouter', 'reasoning_effort': 'ultra'}
    response = httpx.Response(400, json={'error': {'message': 'upstream-secret'}})
    with httpx.Client(transport=httpx.MockTransport(lambda _: response)) as client:
        with pytest.raises(ProviderError, match='可能不支援思考程度 ultra') as error:
            generate(config, [], SETTINGS, 'private', client)
    assert 'upstream-secret' not in str(error.value)


def test_dynamic_router_records_resolved_model_without_forcing_provider_policy():
    def handle(request):
        payload = json.loads(request.content)
        assert payload['model'] == 'openrouter/auto'
        assert payload['temperature'] == 0
        assert payload['max_tokens'] == 128
        assert 'provider' not in payload
        return httpx.Response(200, json={
            'id': 'gen-test', 'model': 'maker/resolved',
            'choices': [{'message': {'content': 'OK'}}],
            'usage': {'cost': 0.002},
        })

    config = {
        **CONFIG, 'provider': 'openrouter', 'model': 'openrouter/auto',
        'catalog': {'fixed_model': False, 'supported_parameters': ['temperature', 'max_tokens']},
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = generate(config, [], {**SETTINGS, 'max_tokens': 128}, 'private', client)
    assert result['requested_model'] == 'openrouter/auto'
    assert result['resolved_model'] == 'maker/resolved'
    assert result['cost'] == '0.002'


def test_catalog_unsupported_parameters_are_omitted_from_request():
    def handle(request):
        payload = json.loads(request.content)
        assert payload['model'] == 'maker/limited'
        assert 'temperature' not in payload
        assert 'max_tokens' not in payload
        assert payload['provider']['require_parameters'] is True
        return httpx.Response(200, json={
            'choices': [{'message': {'content': 'OK'}}],
        })

    config = {
        **CONFIG, 'provider': 'openrouter', 'model': 'maker/limited',
        'catalog': {'fixed_model': True, 'supported_parameters': []},
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert generate(config, [], SETTINGS, 'private', client)['output'] == 'OK'
