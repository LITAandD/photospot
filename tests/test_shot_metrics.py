import pytest
from pydantic import ValidationError
from api.analytics import EventIn
from fastapi.testclient import TestClient
from api.preview import app

def event(kind,props):
    return {'event':kind,'session_id':'metrics-test-123','route':'/today-shot','props':props}

@pytest.mark.parametrize('kind,props',[
 ('shot_view',{'result':'empty','cut_id':None}),
 ('shot_view',{'result':'primary','cut_id':'gbg-01'}),
 ('shot_view',{'result':'alternative_available','cut_id':'square-01'}),
 ('shot_directions',{'cut_id':'gbg-01','outcome':'opened','provider':'kakao'}),
 ('shot_alternative',{'cut_id':'square-01','from_cut_id':'gbg-01','outcome':'opened'}),
 ('shot_completed',{'cut_id':'gbg-01','outcome':'reported'}),
 ('share_click',{'surface':'today_shot','cut_id':'gbg-01','outcome':'copied'}),
])
def test_minimal_shot_event(kind,props):
    assert EventIn.model_validate(event(kind,props)).event==kind

@pytest.mark.parametrize('kind,props',[
 ('shot_view',{'result':'empty','cut_id':'gbg-01'}),
 ('shot_view',{'result':'primary'}), ('shot_view',{'result':'replaced','cut_id':'gbg-01'}),
 ('shot_view',{'result':'empty','arrival':'10:00'}),
 ('shot_completed',{'outcome':'reported'}),
 ('shot_completed',{'cut_id':123,'outcome':'reported'}),
 ('shot_completed',{'cut_id':'test-cut-a','outcome':'reported'}),
 ('shot_completed',{'cut_id':'gbg-01','outcome':'opened'}),
 ('shot_directions',{'cut_id':'gbg-01','outcome':'reported','provider':'kakao'}),
 ('shot_directions',{'cut_id':'gbg-01','outcome':'opened'}),
 ('shot_alternative',{'cut_id':'square-01','from_cut_id':'gbg-01','outcome':'reported'}),
 ('shot_alternative',{'cut_id':'square-01','outcome':'opened'}),
 ('share_click',{'surface':'today_shot','cut_id':'gbg-01','outcome':'opened'}),
])
def test_invalid_or_synthetic_payload_rejected(kind,props):
    with pytest.raises(ValidationError):EventIn.model_validate(event(kind,props))

def test_empty_view_http_and_completion_requires_cut(monkeypatch):
    monkeypatch.setattr('api.analytics_routes.store',lambda e:True)
    with TestClient(app) as client:
        assert client.post('/preview/events',json=event('shot_view',{'result':'empty'})).status_code in (200,204)
        assert client.post('/preview/events',json=event('shot_completed',{'outcome':'reported'})).status_code==422

