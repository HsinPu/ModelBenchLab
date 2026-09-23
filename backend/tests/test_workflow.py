from sqlalchemy import select
from app.db import Session, Item, Model, Run
from app.execution import execute_item, recover_stale
from app.providers import ProviderError
from app.evaluators import evaluate

def setup_run(client, rule=None, models=2):
    mids = [client.post('/api/models', json={'name': 'model '+str(i), 'provider':'demo', 'model':'demo-stable' if i == 0 else 'demo-experimental', 'api_key':'secret-value'}).json()['id'] for i in range(models)]
    dataset = client.post('/api/datasets', json={'name':'test', 'cases':[{'title':'Math', 'messages':[{'role':'user','content':'2 + 2'}], 'rule': rule or {'kind':'exact','expected':'4'}}]}).json()['id']
    prompt = client.post('/api/prompts', json={'name':'v1','text':'be concise'}).json()['id']
    run = client.post('/api/runs', json={'name':'test run','dataset_id':dataset,'prompt_id':prompt,'model_ids':mids})
    assert run.status_code == 201
    return run.json()['id']

def execute_all(run_id):
    with Session() as db: ids = list(db.scalars(select(Item.id).where(Item.run_id == run_id)))
    for item_id in ids: execute_item(item_id)

def test_complete_workflow_snapshot_and_secrets(client):
    rid = setup_run(client)
    assert 'secret-value' not in client.get('/api/models').text
    with Session() as db:
        assert all(m.secret != 'secret-value' for m in db.scalars(select(Model)))
    execute_all(rid)
    data = client.get('/api/runs/'+rid).json()
    assert data['status'] == 'completed'
    assert data['pass_rate'] == 50
    assert len(data['items']) == 2
    assert 'secret-value' not in str(data)
    execute_all(rid)  # duplicate delivery is a no-op
    assert all(len(i['attempts']) == 1 for i in client.get('/api/runs/'+rid).json()['items'])
    assert client.get('/api/runs/'+rid+'/export').json()['snapshot']['cases'][0]['title'] == 'Math'
    assert 'latency_ms' in client.get('/api/runs/'+rid+'/export?format=csv').text
    item_id=data['items'][0]['id']
    assert client.post('/api/items/'+item_id+'/review',json={'score':5,'note':'good'}).status_code == 201
    assert client.post('/api/items/'+item_id+'/evaluate',json={}).status_code == 200
    assert client.get('/api/runs/'+rid).json()['reviews'][0]['score'] == 5

def test_cancellation_and_no_reexecution(client):
    rid=setup_run(client)
    assert client.post('/api/runs/'+rid+'/cancel').status_code == 200
    execute_all(rid)
    data=client.get('/api/runs/'+rid).json()
    assert data['status']=='cancelled'
    assert data['counts']=={'cancelled':2}
    assert client.post('/api/runs/'+rid+'/cancel').status_code == 409

def test_retry_preserves_original(client,monkeypatch):
    rid=setup_run(client,models=1)
    def fail(*args,**kwargs): raise ProviderError('HTTP 401')
    monkeypatch.setattr('app.execution.generate',fail)
    execute_all(rid)
    assert client.get('/api/runs/'+rid).json()['counts']=={'failed':1}
    retry=client.post('/api/runs/'+rid+'/retry').json()['id']
    assert retry!=rid
    assert client.get('/api/runs/'+retry).json()['snapshot']['retry_of']==rid
    assert client.get('/api/runs/'+rid).json()['counts']=={'failed':1}

def test_transient_retry_is_not_extra_sample(client,monkeypatch):
    rid=setup_run(client,models=1)
    from app.providers import generate
    calls=[]
    def transient(*args,**kwargs):
        calls.append(1)
        if len(calls)<3: raise ProviderError('HTTP 429',True)
        return generate(*args,**kwargs)
    monkeypatch.setattr('app.execution.generate',transient)
    monkeypatch.setattr('app.execution.time.sleep',lambda _:None)
    execute_all(rid)
    data=client.get('/api/runs/'+rid).json()
    assert data['total']==1 and data['passed']==1
    assert len(data['items'][0]['attempts'])==3

def test_stale_worker_not_automatically_replayed(client):
    rid=setup_run(client,models=1)
    with Session() as db:
        item=db.scalar(select(Item).where(Item.run_id==rid))
        item.status='running';item.started_at='2000-01-01T00:00:00+00:00'
        db.get(Run,rid).status='running';db.commit()
    recover_stale()
    data=client.get('/api/runs/'+rid).json()
    assert data['status']=='completed_with_errors'
    assert data['counts']=={'failed':1}

def test_validation_and_missing(client):
    assert client.get('/api/runs/missing').status_code==404
    assert client.post('/api/models',json={'name':'x','model':'x','endpoint':'file:///etc/passwd'}).status_code==422
    body={'name':'x','cases':[{'title':'x','messages':[{'role':'user','content':'x'}],'rule':{'kind':'contains','expected':''}}]}
    assert client.post('/api/datasets',json=body).status_code==422
    body['cases'][0]['rule']={'kind':'json_schema','schema':{'$ref':'https://example.com/schema'}}
    assert client.post('/api/datasets',json=body).status_code==422
    assert client.post('/api/prompts',json={'name':'x','text':'x'},headers={'origin':'https://evil.example'}).status_code==403

def test_evaluators():
    assert evaluate(' 4 ',{'kind':'exact','expected':'4'})['passed']
    assert evaluate('HELLO world',{'kind':'contains','expected':'hello'})['passed']
    schema={'type':'object','required':['age'],'properties':{'age':{'type':'integer'}}}
    assert evaluate('{"age":3}',{'kind':'json_schema','schema':schema})['passed']
    assert not evaluate('{"age":"3"}',{'kind':'json_schema','schema':schema})['passed']
    assert not evaluate('not json',{'kind':'json_schema','schema':schema})['passed']
    assert evaluate('anything',{'kind':'manual'})['passed'] is None


def test_cancel_during_inflight_preserves_answer(client,monkeypatch):
    rid=setup_run(client,models=1)
    from app.providers import generate
    def inflight(*args,**kwargs):
        assert client.post('/api/runs/'+rid+'/cancel').status_code==200
        return generate(*args,**kwargs)
    monkeypatch.setattr('app.execution.generate',inflight)
    execute_all(rid)
    data=client.get('/api/runs/'+rid).json()
    assert data['status']=='cancelled'
    assert data['items'][0]['result']['output']=='4'

def test_terminal_sse_and_csv_injection(client):
    rid=setup_run(client,models=1)
    execute_all(rid)
    with Session() as db:
        item=db.scalar(select(Item).where(Item.run_id==rid))
        item.result={**item.result,'output':'=HYPERLINK("https://example.com")'}
        db.commit()
    response=client.get('/api/runs/'+rid+'/events')
    assert response.status_code==200 and 'data: ' in response.text
    assert 'completed' in response.text
    response=client.get('/api/runs/'+rid+'/export?format=csv')
    assert "'=HYPERLINK" in response.text
