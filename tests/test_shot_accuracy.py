from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import json
import pytest
from api import shot_guides as g
from api.shot_review import fixture_places
from scripts import check_data_freshness as fresh
from tests.test_shot_guides import DAY

@pytest.fixture
def places(monkeypatch):
    monkeypatch.setattr('api.shot_review.today',lambda:DAY)
    monkeypatch.setattr(g,'kst_today',lambda:DAY)
    return fixture_places('open',DAY)

@pytest.mark.parametrize('arrival,hour,expected',[(None,17,False),(time(10),15,False),(None,8,True),(time(10),8,True),(time(15,30),15,True)])
def test_current_day_elapsed_time(places,arrival,hour,expected):
    now=datetime(2026,11,24,hour,30,59,tzinfo=ZoneInfo('Asia/Seoul'))
    r=g.choose(places,DAY,arrival,today=DAY,now=now)
    assert bool(r['primary']) is expected
    if not expected: assert any('지난' in e['reason'] or '지났' in e['reason'] for e in r['excluded'])

def test_future_day_does_not_use_current_clock(places):
    assert g.choose(places,DAY+timedelta(days=1),time(10),today=DAY,now=datetime(2026,11,24,23,tzinfo=ZoneInfo('Asia/Seoul')))['primary']

def test_goal_counts_before_filter_and_exclusion_code(places):
    r=g.choose(places,DAY,goal='landscape',today=DAY,now=datetime(2026,11,24,8,tzinfo=ZoneInfo('Asia/Seoul')))
    assert r['goal_counts']=={'portrait':2,'architecture':2,'landscape':0}
    assert {e['code'] for e in r['excluded']}=={'purpose'}
    places[0].cuts[0].status='candidate'
    assert g.choose(places,DAY,today=DAY,now=datetime(2026,11,24,8,tzinfo=ZoneInfo('Asia/Seoul')))['goal_counts']['portrait']==1

@pytest.mark.parametrize('active,days,expired',[(True,3,0),(False,3,1)])
def test_verified_shot_freshness_alert(places,monkeypatch,tmp_path,active,days,expired):
    p=places[0]; c=p.cuts[0]
    for obj in [p.place_schedule,c.access]:
        obj.source.checked_at=DAY;obj.source.valid_until=DAY+timedelta(days=20)
        obj.applies_from=DAY;obj.applies_until=DAY+timedelta(days=20)
    c.photography.checked_at=DAY;c.photography.valid_until=DAY+timedelta(days=20)
    c.field_review.checked_at=DAY;c.field_review.valid_until=DAY+timedelta(days=days)
    c.light_evidence=c.photography.model_copy(update={'checked_at':DAY-timedelta(days=2),'valid_until':DAY-timedelta(days=1)})
    (tmp_path/'shot_guides.json').write_text(json.dumps({'version':1,'places':[p.model_dump(mode='json')]}),encoding='utf8')
    monkeypatch.setattr(g,'catalog_records',lambda:{p.place_id:{'lat':37.571,'lng':126.97}} if active else {})
    row=next(r for r in fresh.report(DAY,tmp_path) if r['source']=='shot_guides')
    assert row['entries']==1 and row['expired']==expired
    assert fresh.main(['--data-dir',str(tmp_path),'--today',str(DAY),'--source','shot_guides','--fail-within','7'])==1

def test_current_candidates_are_not_expiry_alerts():
    assert next(r for r in fresh.report(DAY) if r['source']=='shot_guides')['entries']==0
