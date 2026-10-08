from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from api.catalog_scoring import explanation, WEIGHTS
from api.catalog_bridge import evaluate as authenticated_evaluate
from api.preview import evaluate, PreviewIn
from pipeline import place_catalog as catalog, catalog_photos as photos, catalog_visuals as visuals
from scripts.export_catalog import export

PROFILE = dict(gender='female', height_cm=170, pc_season='spring_warm', pc_subtone='light', body_type='wave', mbti='INFP')

def test_single_metric_uses_full_basis_and_unknowns_remain_distinct_from_mismatches():
    place = {'category': 'cafe'}
    partial = explanation({'height_cm': 160}, None, place)
    complete_profile = explanation({**PROFILE, 'height_cm': 160}, None, place)
    assert partial['score'] == complete_profile['score'] == 10.9  # 10/92, never 10/10.
    assert partial['evaluated_weight'] == complete_profile['evaluated_weight'] == 10
    assert partial['total_weight'] == complete_profile['total_weight'] == 92
    for result, status in [(partial, 'missing_input'), (complete_profile, 'pending')]:
        unknown = [m for m in result['metrics'] if m['key'] != 'height_band.setting']
        assert all(m['points'] is None and m['status'] == status for m in unknown)
    mismatch = explanation({'height_cm': 180}, None, place)
    assert mismatch['score'] == 0 and mismatch['evaluated_weight'] == 10
    assert explanation({}, None, place)['score'] is None


def test_complete_evidence_can_reach_full_score_and_missing_evidence_never_inflates_it():
    profile = {**PROFILE, 'height_cm': 160, 'pc_subtone': 'true'}
    evidence = {'attributes': {'color_temp': 'warm', 'brightness': 'bright_soft', 'saturation': 'mid',
                              'form': 'curved', 'setting': 'indoor', 'place_character': 'concept', 'photo_mood': 'emotional'}}
    visitors = dict(status='ranked', percentile=0, period_start='2026-07', period_end='2026-09',
                    visitors=100, measured_count=2, rank=2)
    full = explanation(profile, evidence, visitors=visitors)
    assert full['score'] == 100 and full['evaluated_weight'] == 92
    assert len([m for m in full['metrics'] if m['status'] == 'scored']) == 8
    without_visitors = explanation(profile, evidence)
    assert without_visitors['score'] == 95.7 and without_visitors['evaluated_weight'] == 88
    body_only = explanation({'body_type': 'wave'}, {'attributes': {'form': 'curved'}})
    assert body_only['score'] == 32.6


def test_score_filter_uses_overall_score_instead_of_single_metric_percent(catalog_db):
    query = dict(visit_date=date(2026,10,8), profile={'height_cm':160})
    response = evaluate(PreviewIn(**query))
    assert all(i.fit_score == 10.9 for i in response['recommendations'].items)
    assert evaluate(PreviewIn(**query,min_fit=50))['recommendations'].items == []
    assert evaluate(PreviewIn(**query,min_fit=10))['recommendations'].items
    assert all(response['places'][i.place_id].scoring.score == 10.9 for i in response['recommendations'].items)

def test_plus_filters_apply_before_result_limit_and_never_invent_scores(catalog_db):
    catalog.import_response('seoul', {'elements':[{'type':'node','id':n,'lat':37.5796,'lon':126.977,'tags':{'name':f'Cafe {n}','amenity':'cafe'}} for n in (1,2,3)]})
    original=authenticated_evaluate(PROFILE,date(2026,10,7),limit=50)['recommendations'].items
    assert len(original)==3
    photographed=authenticated_evaluate(PROFILE,date(2026,10,7),photo_only=True,limit=50)['recommendations'].items
    assert len(photographed)==2 and all(item.cover_photo for item in photographed)
    minimum=max(item.fit_score for item in photographed)
    result=authenticated_evaluate(PROFILE,date(2026,10,7),min_fit=int(minimum),limit=50)['recommendations'].items
    assert result and all(item.fit_score is not None and item.fit_score>=int(minimum) for item in result)

def test_observed_attributes_and_weights_control_score_without_fabricating_unknowns():
    evidence = {'attributes': {'color_temp':'warm','brightness':'bright_soft','saturation':'muted','form':'curved','texture':'soft','scale':'compact','photo_mood':'emotional'},
                'source_url':'https://commons.wikimedia.org/wiki/File:A.jpg','method':'test fixture'}
    first = explanation(PROFILE, evidence)
    second = explanation({**PROFILE,'pc_season':'winter_cool','body_type':'straight','mbti':'ENTJ'}, evidence)
    assert first['score'] != second['score']
    scored = [m for m in first['metrics'] if m['status']=='scored']
    assert first['score'] == round(max(0, min(100, 100*sum(m['points'] for m in scored)/first['total_weight'])),1)
    assert first['evaluated_weight'] == sum(m['weight'] for m in scored)
    assert sum(w['weight'] for w in WEIGHTS if w['dimension']!='element') == first['total_weight'] == 92
    assert next(m for m in first['metrics'] if m['key']=='mbti_ei.crowd_level')['status']=='pending'
    assert explanation(PROFILE, None)['score'] is None
    assert explanation({}, evidence)['score'] is None

@pytest.fixture
def catalog_db(tmp_path,monkeypatch):
    path=tmp_path/'public.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB',str(path))
    catalog.import_response('seoul',{'elements':[
        {'type':'node','id':n,'lat':37.5796,'lon':126.977,'tags':{'name':f'Cafe {n}','amenity':'cafe'}} for n in (1,2)]})
    rows=catalog.search(37.5796,126.977,1000)
    from tests.test_catalog_photos import image_page
    for row,temp in zip(rows,['warm','cool']):
        photo=photos.reusable_image(image_page())
        photos.store_photos([{**photo,'place_id':row['id'],'match_method':'reviewed:branch','match_ref':'test','priority':1}],path)
        visuals.store(row['id'],photo,{'color_temp':temp,'form':'curved'},'test fixture',path)
    return path,rows

def test_preview_and_authenticated_catalog_share_scores_photos_and_detail(catalog_db):
    _,rows=catalog_db
    preview=evaluate(PreviewIn(profile=PROFILE,visit_date=date(2026,10,7),limit=2))
    native=authenticated_evaluate({**PROFILE,'element':None,'saju_percents':None},date(2026,10,7),limit=2)
    assert native['recommendations']==preview['recommendations']
    assert native['places']==preview['places']
    items=native['recommendations'].items
    assert items[0].fit_score != items[1].fit_score
    assert all(native['places'][i.place_id].scoring==i.scoring and i.cover_photo for i in items)
    detail=authenticated_evaluate(PROFILE,date(2026,10,7),place_ids=[rows[1]['id']])['places'][rows[1]['id']]
    assert detail.photos and detail.scoring.evaluated_weight>0

def test_removed_photo_invalidates_analysis_and_export_preserves_public_data(catalog_db,tmp_path,monkeypatch):
    path,rows=catalog_db
    with catalog.connect() as conn:
        conn.execute('CREATE TABLE private_test(secret TEXT)')
        conn.execute("INSERT INTO private_test VALUES ('must-not-export')")
    target=tmp_path/'export.sqlite3'
    export(target)
    with catalog.connect(target) as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='private_test'").fetchone()
    monkeypatch.setenv('PLACE_CATALOG_DB',str(target))
    assert len(visuals.evidence_for(r['id'] for r in rows))==2
    with catalog.connect() as conn: conn.execute('DELETE FROM catalog_photos WHERE place_id=?',(rows[0]['id'],))
    assert rows[0]['id'] not in visuals.evidence_for([rows[0]['id']])

def test_authenticated_http_routes_return_shared_catalog_and_persist_bookmarks(catalog_db,monkeypatch):
    from api.main import create_app
    from api.config import Settings
    from api.auth import current_user, CurrentUser
    from api.db import get_conn
    from api import routes
    saved=set()
    class Conn:
        def cursor(self): return self
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,sql,args):
            if sql.startswith('INSERT INTO catalog_bookmarks'): saved.add(str(args[1]))
            if sql.startswith('DELETE FROM catalog_bookmarks'): saved.discard(str(args[1]))
        def fetchall(self): return [(p,) for p in saved]
    app=create_app(Settings(recommendation_backend='catalog'))
    app.dependency_overrides[current_user]=lambda:SimpleNamespace(id='user',is_admin=False)
    app.dependency_overrides[get_conn]=lambda:Conn()
    monkeypatch.setattr(routes,'_profile',lambda *_:PROFILE)
    client=TestClient(app)
    result=client.get('/v1/recommendations',params={'lat':37.5796,'lng':126.977,'date':'2026-10-07','limit':2})
    assert result.status_code==200
    item=result.json()['items'][0]
    pid=item['place_id']
    detail=client.get('/v1/places/'+pid,params={'date':'2026-10-07'})
    assert detail.status_code==200 and detail.json()['scoring']==item['scoring']
    assert client.put('/v1/me/bookmarks/'+pid).status_code==204
    assert client.get('/v1/me/bookmarks').json()[0]['place_id']==pid
    assert client.delete('/v1/me/bookmarks/'+pid).status_code==204 and not saved
    assert client.get('/v1/places/00000000-0000-0000-0000-000000000000').status_code==404
