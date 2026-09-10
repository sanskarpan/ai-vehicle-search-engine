from fastapi.testclient import TestClient

from vehicle_search.api import create_app
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

def test_frontend_is_served(tmp_path, monkeypatch):
    assert client(tmp_path, monkeypatch).get('/').status_code == 200
