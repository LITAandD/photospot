"""Run against migrated PostgreSQL in CI; each test owns and removes its user rows."""
import os
from uuid import uuid4
from datetime import datetime, timezone, timedelta
import psycopg
import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from api.config import Settings
from api.providers import DevVerifier
from api import growth_services

DSN=os.environ.get('DATABASE_URL')
pytestmark=pytest.mark.skipif(not DSN,reason='DATABASE_URL required for growth persistence tests')

@pytest.fixture
def account():
    settings=Settings(database_url=DSN,google_client_ids=[],apple_audiences=[],environment='test',
                      openai_api_key='test-only',revenuecat_secret_key='test-only')
    app=create_app(settings,verifiers={'google':DevVerifier()})
    with TestClient(app) as client:
        pair=client.post('/v1/auth/google',json={'token':'dev:growth-'+uuid4().hex}).json()
        user=pair['user_id']; headers={'Authorization':'Bearer '+pair['access_token']}
        try: yield client,headers,user
        finally:
            with psycopg.connect(DSN) as conn:
                conn.execute('DELETE FROM feedback_triages WHERE feedback_ids && ARRAY(SELECT id FROM app_feedback WHERE user_id=%s)',(user,))
                conn.execute('DELETE FROM growth_audit WHERE actor_id=%s',(user,))
                conn.execute('DELETE FROM users WHERE id=%s',(user,))

def test_feedback_consent_review_ai_approval_and_erasure(account,monkeypatch):
    client,h,user=account
    one=client.post('/v1/feedback',headers=h,json={'category':'bug','message':'테스트 지도 연결 오류','ai_consent':True})
    assert one.status_code==201
    fid=one.json()['id']
    assert client.get('/v1/admin/feedback',headers=h).status_code==403
    with psycopg.connect(DSN) as conn: conn.execute('UPDATE users SET is_admin=true WHERE id=%s',(user,))
    assert client.post('/v1/admin/feedback/triage',headers=h,json={'feedback_ids':[fid]}).status_code==409
    assert client.patch('/v1/admin/feedback/'+fid,headers=h,json={'reviewed_text':'개인정보 없는 지도 연결 오류'}).status_code==204
    def fake_triage(settings,rows):
        assert len(rows)==1 and rows[0]['ai_consent'] and rows[0]['reviewed_text']
        return [{'feedback_ids':[fid],'title':'지도 수정','summary':'지도 연결 개선','impact':4,'urgency':3,'effort':2,'reason':'방문 영향','acceptance':'지도 정상 열림','reporters':1,'priority_score':9.5}]
    monkeypatch.setattr(growth_services,'triage',fake_triage)
    assert client.post('/v1/admin/feedback/triage',headers=h,json={'feedback_ids':[fid]}).status_code==200
    assert client.post('/v1/admin/feedback/triage',headers=h,json={'feedback_ids':[fid]}).status_code==409
    triages=client.get('/v1/admin/triages',headers=h).json()
    tid=next(t['id'] for t in triages if fid in t['feedback_ids'])
    assert client.patch('/v1/admin/triages/'+tid,headers=h,json={'status':'done','note':'잘못된 건너뛰기'}).status_code==409
    for state in ['approved','planned','done']:
        assert client.patch('/v1/admin/triages/'+tid,headers=h,json={'status':state,'note':'개발자 검토 결과'}).status_code==204
    assert client.delete('/v1/me/feedback/'+fid,headers=h).status_code==204
    assert all(t['id']!=tid for t in client.get('/v1/admin/triages',headers=h).json())

def test_only_server_verified_entitlement_enables_plus_and_last_provider_is_preserved(account,monkeypatch):
    client,h,user=account
    assert client.get('/v1/me/billing',headers=h).json()['premium'] is False
    assert client.delete('/v1/me/identities/google',headers=h).status_code==409
    monkeypatch.setattr(growth_services,'subscription',lambda s,uid:(datetime.now(timezone.utc)+timedelta(days=1),None))
    result=client.post('/v1/me/billing/sync',headers=h)
    assert result.status_code==200 and result.json()['premium'] is True
    with psycopg.connect(DSN) as conn:
        conn.execute("UPDATE billing_entitlements SET checked_at=now()-interval '16 minutes' WHERE user_id=%s",(user,))
    monkeypatch.setattr(growth_services,'subscription',lambda s,uid:(None,None))
    assert client.get('/v1/me/billing',headers=h).json()['premium'] is False
