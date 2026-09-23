import httpx
import pytest
from app.providers import generate, ProviderError

CONFIG={'provider':'openai-compatible','endpoint':'https://model.example/v1','model':'test'}
SETTINGS={'timeout':5,'temperature':0,'max_tokens':10}

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


@pytest.mark.parametrize('payload',[None,{}, {'choices':[]}, {'choices':[{'message':{'content':None}}]}])
def test_malformed_payload_is_sanitized(payload):
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload))) as client:
        with pytest.raises(ProviderError):
            generate(CONFIG,[],SETTINGS,'private',client)
