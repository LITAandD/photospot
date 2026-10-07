import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from api.growth_models import FeedbackSubmission, CampaignIn
from api.growth_services import triage, subscription, instagram_identity, redact
from api.config import Settings
from api.providers import build_verifiers

def idea(ids=['f1']):
    return dict(title='지도 수정',summary='주소 연결 오류 제보',feedback_ids=ids,impact=4,urgency=3,effort=2,reason='방문 흐름에 영향',acceptance='정확한 지도가 열림')

def response(ideas=None, **kwargs):
    return {'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps({'ideas':ideas or [idea()]})}]}],**kwargs}

def rows():
    return [{'id':'f1','user_id':'private-user','category':'bug','reviewed_text':'지도 수정 요청 test@example.com 010-1234-5678'}]

def test_ai_only_sends_reviewed_minimized_text_and_counts_evidence():
    def transport(url,token,body):
        assert url=='https://api.openai.com/v1/responses' and token=='test'
        assert body['store'] is False and body['text']['format']['strict'] is True
        assert 'private-user' not in body['input'] and 'example.com' not in body['input'] and '010' not in body['input']
        assert set(json.loads(body['input'])[0])=={'id','category','text'}
        return response()
    result=triage(SimpleNamespace(openai_api_key='test',feedback_model='gpt-4o-mini'),rows(),transport)
    assert result[0]['reporters']==1 and result[0]['priority_score']==9.5

@pytest.mark.parametrize('data',[response([idea(['invented'])]), response([idea(),idea()]),response(status='incomplete'),
    {'status':'completed','output':[{'content':[{'type':'refusal'}]}]},response([{**idea(),'impact':10}])])
def test_ai_rejects_incomplete_refused_invented_and_duplicate_evidence(data):
    with pytest.raises(ValueError): triage(SimpleNamespace(openai_api_key='test',feedback_model='test'),rows(),lambda *a,**k:data)

def test_redaction_and_validation():
    assert 'user@mail.com' not in redact('user@mail.com @private https://secret.test')
    with pytest.raises(ValidationError): FeedbackSubmission(category='bug',message='     ')
    with pytest.raises(ValidationError): CampaignIn(place_id='00000000-0000-0000-0000-000000000001',sponsor='a',headline='b',placement='banner',starts_at='2026-01-01',ends_at='2026-01-02')

def test_billing_checks_server_subscription_and_production_sandbox():
    future=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()
    data={'subscriber':{'entitlements':{'plus':{'expires_date':future,'product_identifier':'monthly'}},'subscriptions':{'monthly':{'is_sandbox':True}},'management_url':'https://evil.test'}}
    settings=SimpleNamespace(revenuecat_secret_key='secret',premium_entitlement='plus',environment='production')
    assert subscription(settings,'user',lambda *a,**k:data)==(None,None)
    data['subscriber']['subscriptions']['monthly']['is_sandbox']=False
    until,url=subscription(settings,'user',lambda *a,**k:data)
    assert until>datetime.now(timezone.utc) and url is None
    data['subscriber']['entitlements']={}
    assert subscription(settings,'user',lambda *a,**k:data)[0] is None

def test_instagram_exchanges_code_server_side_without_retaining_token():
    cfg=SimpleNamespace(instagram_client_id='id',instagram_client_secret='secret',instagram_redirect_uri='https://api.test/callback')
    def transport(url,**kwargs):
        if 'oauth/access_token' in url:
            assert kwargs['form']['client_secret']=='secret' and kwargs['form']['code']=='code'
            return {'access_token':'private-token','user_id':123}
        assert kwargs['token']=='private-token'
        return {'user_id':'123','username':'photo.owner'}
    assert instagram_identity(cfg,'code',transport)==('123','photo.owner')
    with pytest.raises(ValueError): instagram_identity(cfg,'code',lambda url,**k: {'access_token':'t','user_id':123} if 'oauth' in url else {'user_id':999,'username':'other'})

def test_unconfigured_providers_fail_closed():
    assert build_verifiers(Settings(google_client_ids=[],apple_audiences=[],kakao_app_id=None,naver_login_enabled=False,dev_login=False))=={}
    assert 'kakao' in build_verifiers(Settings(kakao_app_id=123))
