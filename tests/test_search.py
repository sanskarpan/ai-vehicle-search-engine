from fastapi.testclient import TestClient

from vehicle_search.api import create_app
from vehicle_search.parsing import ParserError
from vehicle_search.seed import build
from vehicle_search.storage import connect, insert_vehicle


def fixture_db(tmp_path):
    db=tmp_path/'cat.db'; c=connect(str(db));
    for v in build(8,42): insert_vehicle(c,v)
    c.execute("INSERT INTO catalogue_metadata VALUES ('catalogue_version','test-v1')"); c.commit(); c.close(); return db

def client(tmp_path, monkeypatch):
    db=fixture_db(tmp_path); monkeypatch.setenv('PARSER_MODE','offline'); return TestClient(create_app(str(db)))

def test_strict_price_boundary(tmp_path, monkeypatch):
    r=client(tmp_path,monkeypatch).post('/api/v1/search',json={'query':'Show SUVs under ₹15L'}); assert r.status_code==200
    ids=[x['vehicle']['id'] for x in r.json()['results']]; assert 'veh_000002' not in ids; assert 'veh_000001' in ids

def test_inclusive_price_boundary(tmp_path, monkeypatch):
    r=client(tmp_path,monkeypatch).post('/api/v1/search',json={'query':'Show SUVs up to ₹15L'}); assert r.status_code==200
    ids=[x['vehicle']['id'] for x in r.json()['results']]; assert 'veh_000002' in ids; assert 'veh_000003' not in ids

def test_diesel_automatic_odometer(tmp_path, monkeypatch):
    r=client(tmp_path,monkeypatch).post('/api/v1/search',json={'query':'Diesel automatic cars below 80k km'}); assert r.status_code==200
    ids=[x['vehicle']['id'] for x in r.json()['results']]; assert ids==['veh_000005','veh_000006','veh_000001']

def test_family_safety_and_nulls(tmp_path, monkeypatch):
    r=client(tmp_path,monkeypatch).post('/api/v1/search',json={'query':'Family cars with high safety ratings'}); assert r.status_code==200
    ids={x['vehicle']['id'] for x in r.json()['results']}; assert ids=={'veh_000001','veh_000002','veh_000003','veh_000004','veh_000006'}

def test_clarification_and_zero_results(tmp_path, monkeypatch):
    c=client(tmp_path,monkeypatch)
    assert c.post('/api/v1/search',json={'query':'Low mileage cars'}).json()['status']=='needs_clarification'
    r=c.post('/api/v1/search',json={'query':'SUVs under ₹1L'}).json(); assert r['status']=='ok' and r['total']==0

def test_pagination(tmp_path, monkeypatch):
    c=client(tmp_path,monkeypatch); a=c.post('/api/v1/search',json={'query':'Show cars','limit':3}).json(); b=c.post('/api/v1/search',json={'query':'Show cars','limit':3,'offset':3}).json(); assert a['total']==8 and b['total']==8 and not ({x['vehicle']['id'] for x in a['results']} & {x['vehicle']['id'] for x in b['results']})

def test_validation_rejects_extra_and_empty(tmp_path, monkeypatch):
    c=client(tmp_path,monkeypatch); assert c.post('/api/v1/search',json={'query':' ','x':1}).status_code==422
    assert c.post('/api/v1/search',json={'query':'Show cars','sort':'random'}).status_code==422

def test_frontend_is_served(tmp_path, monkeypatch):
    response=client(tmp_path, monkeypatch).get('/')
    assert response.status_code == 200
    assert 'aria-label="Vehicle search query"' in response.text
    assert 'role="status"' in response.text
    assert not any(symbol in response.text for symbol in ("⌕", "↗", "✦", "◌", "←", "→", "★", "×"))
    assert '<svg class="icon icon-search"' in response.text

def test_detail_and_missing_detail_are_stable(tmp_path, monkeypatch):
    c=client(tmp_path,monkeypatch)
    assert c.get('/api/v1/vehicles/veh_000001').status_code == 200
    missing=c.get('/api/v1/vehicles/does-not-exist')
    assert missing.status_code==404 and missing.json()['error']['code']=='not_found'

def test_large_request_and_unseeded_readiness(tmp_path, monkeypatch):
    c=client(tmp_path,monkeypatch)
    assert c.post('/api/v1/search',content='{"query":"x"}',headers={'content-type':'application/json','content-length':'9000'}).status_code == 413
    unseeded=tmp_path/'missing.db'
    empty_client=TestClient(create_app(str(unseeded)))
    assert empty_client.get('/health/ready').status_code == 503
    assert empty_client.get('/api/v1/vehicles/veh_000001').status_code == 503

def test_offset_beyond_results_returns_empty_page(tmp_path, monkeypatch):
    response=client(tmp_path,monkeypatch).post('/api/v1/search',json={'query':'Show cars','offset':10000})
    body=response.json()
    assert response.status_code==200 and body['total']==8 and body['results']==[] and body['has_more'] is False

def test_budget_shorthand_is_not_partially_matched(tmp_path, monkeypatch):
    body=client(tmp_path,monkeypatch).post('/api/v1/search',json={'query':'SUVs under ₹1k'}).json()
    assert body['status']=='needs_clarification'

def test_invalid_provider_output_can_use_explicit_degraded_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('PARSER_MODE','llm'); monkeypatch.setenv('LLM_PROVIDER','openrouter')
    monkeypatch.setenv('LLM_MODEL','openrouter/free'); monkeypatch.setenv('OPENROUTER_API_KEY','test-key')
    monkeypatch.setenv('ALLOW_OFFLINE_FALLBACK','true')
    class BrokenParser:
        def parse(self, query): raise ParserError('llm_invalid_response','bad structured output')
    monkeypatch.setattr('vehicle_search.api.build_parser', lambda *args, **kwargs: BrokenParser())
    body=TestClient(create_app(str(fixture_db(tmp_path)))).post('/api/v1/search',json={'query':'Show SUVs'}).json()
    assert body['status']=='ok' and body['degraded'] is True and body['parser_mode']=='offline'

def test_unknown_issue_codes_are_normalized(tmp_path, monkeypatch):
    from vehicle_search.domain import Intent
    from vehicle_search.service import execute
    conn=connect(str(fixture_db(tmp_path)), read_only=True)
    body=execute(Intent(issues=[{'code':'PARAMETER_MISSING','evidence':'budget'}]),conn,'query',10,0)
    conn.close()
    assert body['clarification']['code']=='unsupported'
