"""HTTP authorization and adapter failures without requiring external credentials."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.growth_routes import router
from api.auth import current_user, CurrentUser
from api.db import get_conn
from api.config import Settings

class Conn:
    def __init__(self): self.sql=[]; self.rows=[]; self.commits=0
    def execute(self,sql,args=()): self.sql.append((sql,args)); return self
    def fetchone(self): return self.rows.pop(0) if self.rows else None
    def commit(self): self.commits+=1

@pytest.fixture
def setup():
    app=FastAPI();app.include_router(router);app.state.settings=Settings()
    conn=Conn();user=CurrentUser(str(uuid4()),False)
    app.dependency_overrides[get_conn]=lambda:conn
    app.dependency_overrides[current_user]=lambda:user
    return TestClient(app),conn,user

@pytest.mark.parametrize('method,path,body',[('get','/v1/admin/feedback',None),('get','/v1/admin/triages',None),('get','/v1/admin/campaigns',None),('post','/v1/admin/feedback/triage',{'feedback_ids':[str(uuid4())]})])
def test_non_admin_cannot_read_or_analyze(setup,method,path,body):
    client,conn,_=setup
    res=client.request(method,path,json=body)
    assert res.status_code==403 and conn.sql==[]

def test_instagram_state_replay_expiry_rejected_before_external_call(setup):
    client,conn,_=setup
    res=client.get('/v1/social/instagram/callback',params={'state':'expired','code':'secret'})
    assert res.status_code==400 and conn.commits==1

def test_not_configured_billing_never_grants_or_writes(setup):
    client,conn,_=setup
    assert client.post('/v1/me/billing/sync').status_code==503
    assert conn.sql==[]

def test_feedback_limit_and_validation(setup):
    client,conn,_=setup
    assert client.post('/v1/feedback',json={'category':'bug','message':'   '}).status_code==422
    conn.rows=[('active-user',),(5,)]
    assert client.post('/v1/feedback',json={'category':'bug','message':'지도에 오류가 있어요'}).status_code==429
    assert not any('INSERT' in sql for sql,args in conn.sql)

def test_approval_cannot_skip_to_done(setup):
    client,conn,user=setup;user.is_admin=True;conn.rows=[('proposed',)]
    res=client.patch('/v1/admin/triages/'+str(uuid4()),json={'status':'done','note':'완료합니다'})
    assert res.status_code==409 and not any(sql.startswith('UPDATE') for sql,args in conn.sql)

def test_cancelled_instagram_attempt_cannot_reconnect_after_unlink(setup,monkeypatch):
    from api import growth_services
    client,conn,user=setup
    conn.rows=[(user.id,),(user.id,),None]
    monkeypatch.setattr(growth_services,'instagram_identity',lambda *_:('123','photospot'))
    res=client.get('/v1/social/instagram/callback',params={'state':'previous-attempt','code':'code'})
    assert res.status_code==409
    assert not any('INSERT INTO social_connections' in sql for sql,args in conn.sql)

def test_user_feedback_after_account_deletion_is_rejected(setup):
    client,conn,_=setup
    res=client.post('/v1/feedback',json={'category':'bug','message':'삭제 이후 요청 차단'})
    assert res.status_code==401 and not any(sql.startswith('INSERT') for sql,args in conn.sql)

def test_sponsored_places_respect_region_group_and_minimize_public_fields(setup,monkeypatch):
    from api import growth_routes as g
    client,conn,_=setup
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,*args): pass
        def fetchall(self): return [dict(id='ad',place_id='seoul',sponsor='광고주',headline='촬영 공간',placement='priority',starts_at='2026-01-01',ends_at='2027-01-01',approved=True,created_by='private-admin')]
    conn.cursor=lambda **_:Cursor()
    monkeypatch.setattr(g,'billing_status',lambda *_:{'premium':False})
    monkeypatch.setattr(g.catalog_bridge,'find',lambda *_:dict(id='seoul',name='Test cafe',category='cafe',lat=37.5796,lng=126.977))
    monkeypatch.setattr(g,'display_name',lambda p:p['name'])
    monkeypatch.setattr(g,'photos_for',lambda ids:{ids[0]:[{'url':'https://example.test/photo.jpg'}]})
    q='/v1/sponsorships?lat=37.5796&lng=126.977&radius_m=5000'
    visible=client.get(q).json()
    assert len(visible)==1 and 'created_by' not in visible[0]
    assert client.get(q+'&place_group=travel').json()==[]
    assert client.get('/v1/sponsorships?lat=35.15&lng=129.16').json()==[]
    monkeypatch.setattr(g,'billing_status',lambda *_:{'premium':True})
    assert client.get(q).json()==[]
