from datetime import date,time,datetime
from zoneinfo import ZoneInfo
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api import shot_guides as g
from api.shot_review import fixture_places
from deploy.vercel.frontend import register_spa_routes
D=date(2026,11,24)
@pytest.fixture
def places(monkeypatch):
    monkeypatch.setattr('api.shot_review.today',lambda:D)
    monkeypatch.setattr(g,'kst_today',lambda:D)
    return fixture_places('open',D)

def card(places):
    return g.choose(places,D,time(10),today=D,now=datetime(2026,11,24,8,tzinfo=ZoneInfo('Asia/Seoul')))['primary']

def test_sources_deduplicate_and_label_roles(places):
    assert len(card(places)['sources'])==1
    assert card(places)['sources'][0]['kinds']==['place_hours','cut_access','photography']
    c=places[0].cuts[0];c.light_note='검증한 빛 관찰';c.light_evidence=c.photography.model_copy(update={'label':'빛 관찰 기록'})
    sources=card(places)['sources'];assert len(sources)==2 and sources[1]['kinds']==['light']

def test_diagram_uses_reviewed_composition_not_text_inference(places):
    c=places[0].cuts[0];c.framing='가로 인물사진이라는 문구만 수정'
    assert card(places)['visual']['composition']=={'subject':'architecture','orientation':'portrait','subject_x':0.5}
    c.visual.composition=None
    assert card([places[0]]) is None

def test_private_candidate_never_leaks_into_metadata(places,tmp_path,monkeypatch):
    html=tmp_path/'entry.html';html.write_text('<html><head><title>default</title></head></html>')
    app=FastAPI();register_spa_routes(app,html)
    monkeypatch.setattr(g,'load_places',lambda:places)
    monkeypatch.setattr(g,'catalog_records',lambda:{p.place_id:{'lat':37.571,'lng':126.97} for p in places})
    with TestClient(app) as client:
        r=client.get('/today-shot?cut=test-cut-a&date=2026-11-25')
        assert places[0].cuts[0].title in r.text and 'date=2026-11-25' in r.text and 'noindex' in r.headers['x-robots-tag']
        assert 'rel="canonical" href="https://photospot.litaandd.com/today-shot"' in r.text
        places[0].cuts[0].status='candidate'
        r=client.get('/today-shot?cut=test-cut-a');assert places[0].cuts[0].title not in r.text
