from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import json
import logging

import pytest
from pydantic import ValidationError

from api import shot_guides as g
from api.shot_review import fixture_places
from api.observability import JsonFormatter

D = date(2026, 11, 24)


@pytest.fixture
def places(monkeypatch):
    monkeypatch.setattr('api.shot_review.today', lambda: D)
    monkeypatch.setattr(g, 'kst_today', lambda: D)
    return fixture_places('open', D)


def result(p, at='10:00'):
    return g.choose(p, D, time.fromisoformat(at), today=D, now=datetime(2026,11,24,0,tzinfo=ZoneInfo('Asia/Seoul')), selected='test-cut-a')


@pytest.mark.parametrize('days,expected', [(30,'eligible'),(31,'eligible'),(32,'unknown'),(60,'unknown')])
def test_schedule_max_age(places, days, expected):
    s=places[0].place_schedule
    s.source.checked_at=D; s.source.valid_until=D+timedelta(days=days)
    assert g.schedule_status(s,D,time(10),D)[0] == expected


def test_schedule_application_end_is_separate_from_source_freshness(places):
    s=places[0].place_schedule
    s.source.valid_until=D+timedelta(days=10)
    s.applies_until=D-timedelta(days=1)
    assert g.schedule_status(s,D,time(10),D)[0]=='unknown'


def test_outdoor_access_does_not_borrow_indoor_hours(places):
    p=places[0]; p.place_schedule.weekdays[str(D.weekday())]=[]
    assert result([p])['primary'] is None
    p.cuts[0].area='public_outdoor'
    card=result([p])['primary']
    assert card and card['place_hours']==[] and '별개' in card['place_hours_note']
    p.cuts[0].access.weekdays[str(D.weekday())]=[]
    assert result([p])['primary'] is None


@pytest.mark.parametrize('clock', ['00:00','12:00','23:59'])
def test_explicit_all_day(places,clock):
    c=places[0].cuts[0]; c.area='public_outdoor'; c.access.admission_required=False
    c.access.weekdays[str(D.weekday())]=[g.Window(opens='00:00',closes='00:00',all_day=True)]
    assert result(places,clock)['primary']


def test_2359_close_is_not_24_hour_access(places):
    c=places[0].cuts[0]; c.area='public_outdoor'; c.access.admission_required=False
    c.access.weekdays[str(D.weekday())]=[g.Window(opens='00:00',closes='23:59')]
    assert result([places[0]],'23:59')['primary'] is None


def test_date_exception_reason_on_open_and_closed(places):
    s=places[0].cuts[0].access
    s.exceptions[D]=[g.Window(opens='09:00',closes='18:00',last_entry='17:00')]
    s.exception_notes[D]='행사 설치로 조기 통제'
    assert '행사 설치' in result([places[0]])['primary']['availability_note']
    assert '행사 설치' in g.schedule_status(s,D,time(19),D)[1]


def test_unnamed_exception_is_temporary_closure(places):
    s=places[0].cuts[0].access; s.exceptions[D]=[]
    assert '임시 휴무' in g.schedule_status(s,D,time(10),D)[1]


@pytest.mark.parametrize('change', ['orphan_note','weekday','reversed_period','overlap'])
def test_invalid_schedules(places,change):
    s=places[0].place_schedule.model_dump()
    if change=='orphan_note': s['exception_notes']={D:'bad'}
    if change=='weekday': s['weekdays']={'mon':[]}
    if change=='reversed_period': s['applies_until']=s['applies_from']-timedelta(days=1)
    if change=='overlap': s['weekdays']['0']*=2
    with pytest.raises(ValidationError): g.Schedule.model_validate(s)


def test_field_dates_and_pending_verified_rejected(places):
    c=places[0].cuts[0].model_dump(); c['pending']=['missing permission']
    with pytest.raises(ValidationError): g.Cut.model_validate(c)
    f=c['field_review']; f['valid_until']=f['checked_at']-timedelta(days=1)
    with pytest.raises(ValidationError): g.FieldReview.model_validate(f)


def test_field_pin_is_private_and_independent(places):
    c=places[0].cuts[0]; c.field_review.record_ref='internal-person-private-record'
    raw=json.dumps(result([places[0]]),ensure_ascii=False)
    assert 'internal-person' not in raw and 'record_ref' not in raw and 'evidence' not in result([places[0]])['primary']['pin']
    c.field_review.independent_measurement=False
    assert result([places[0]])['primary'] is None


@pytest.mark.parametrize('change',['no_accuracy','field_url','official_no_source'])
def test_pin_provenance_validation(places,change):
    p=places[0].cuts[0].pin.model_dump()
    if change=='no_accuracy': p['accuracy_m']=None
    if change=='field_url': p['evidence']=places[0].place_schedule.source.model_dump()
    if change=='official_no_source': p['method']='official_shooting_marker'
    with pytest.raises(ValidationError): g.Pin.model_validate(p)


def test_pin_distance_and_documented_overlap(places):
    p=places[0]; c=p.cuts[0]; origin={'lat':c.pin.lat,'lng':c.pin.lng}
    assert g.pin_location_issue(p,c,origin)
    c.field_review.catalog_overlap_reviewed=True
    assert g.pin_location_issue(p,c,origin) is None
    c.pin.lat+=0.01
    assert g.pin_location_issue(p,c,origin)
    c.pin.lat-=0.0099
    assert g.pin_location_issue(p,c,origin) is None
    assert g.choose([p],D,time(10),today=D,catalog_places={})['primary'] is None


@pytest.mark.parametrize('kind,expected',[('suspended','일시 중단'),('prohibited','촬영이 제한')])
def test_hard_restriction_precedes_closure_and_missing_field(places,kind,expected):
    c=places[0].cuts[0]; c.field_review=None
    places[0].place_schedule.weekdays[str(D.weekday())]=[]
    if kind=='suspended': c.status='suspended'
    else: c.photography_allowed=False
    assert expected in result([places[0]])['replacement_reason']


@pytest.mark.parametrize('clock',['11:45','12:30'])
def test_next_entry_window(places,clock):
    s=places[0].place_schedule
    s.weekdays[str(D.weekday())]=[g.Window(opens='09:00',closes='12:00',last_entry='11:30'),g.Window(opens='13:00',closes='18:00',last_entry='17:00')]
    assert '13:00' in g.schedule_status(s,D,time.fromisoformat(clock),D)[1]


def test_cli_loc_and_log_do_not_include_input(tmp_path,monkeypatch,capsys,caplog):
    raw={'version':1,'places':[g.load_places()[0].model_dump(mode='json')]}
    raw['places'][0]['cuts'][0]['photography_alowed']='PRIVATE-VALUE'
    path=tmp_path/'bad.json';path.write_text(json.dumps(raw),encoding='utf8')
    assert g.main(['check','--path',str(path)])==1
    assert capsys.readouterr().out.strip()=='places.0.cuts.0.photography_alowed extra_forbidden'
    monkeypatch.setattr(g,'DATA',path)
    with caplog.at_level(logging.ERROR), pytest.raises(Exception): g.load_places()
    record=next(r for r in caplog.records if 'shot_guides_invalid' in r.getMessage())
    output=JsonFormatter().format(record)
    assert 'photography_alowed' in output and 'PRIVATE-VALUE' not in output


def test_current_cli_and_verified_copy_pass(places,tmp_path,monkeypatch,capsys):
    assert g.main(['check'])==0
    active=g.catalog_records(); p=places[0]; p.place_id=next(iter(active))
    origin={'lat':p.cuts[0].pin.lat-0.0001,'lng':p.cuts[0].pin.lng}
    monkeypatch.setattr(g,'catalog_records',lambda path=None:{p.place_id:origin})
    f=tmp_path/'verified.json'; f.write_text(json.dumps({'version':1,'places':[p.model_dump(mode='json')]}),encoding='utf8')
    assert g.main(['check','--path',str(f)])==0
    assert 'ready' in capsys.readouterr().out
