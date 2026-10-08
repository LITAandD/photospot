from datetime import date
import json

import pytest
from PIL import Image, ImageDraw

from api.catalog_scoring import explanation, catalog_card
from pipeline import place_catalog as catalog, catalog_visitors as visitors, catalog_visuals as visuals


def metric(profile, attrs, key, **kwargs):
    score = explanation(profile, {'attributes': attrs, 'method': 'reviewed photo'}, **kwargs)
    return next(m for m in score['metrics'] if m['key'] == key)


@pytest.mark.parametrize('body,form', [('wave', 'curved'), ('natural', 'linear'), ('straight', 'volumetric')])
def test_body_matches_requested_shapes_not_previous_texture_or_category(body, form):
    for observed in ['curved', 'linear', 'volumetric']:
        assert metric({'body_type': body}, {'form': observed}, 'body_type.form')['points'] == (30 if observed == form else 0)
    assert metric({'body_type': body}, {'form': 'organic'}, 'body_type.form')['status'] == 'pending'
    assert metric({'body_type': body}, {'texture': 'soft'}, 'body_type.form')['status'] == 'pending'
    assert catalog_card({'body_type': body}).good_backgrounds


@pytest.mark.parametrize('height', [150, 169, 170, 171, 190, None])
@pytest.mark.parametrize('gender', ['female', 'male', 'undisclosed'])
def test_height_never_changes_place_fit(height, gender):
    for place in [{'category': 'cafe'}, {'category': 'park'}]:
        baseline = explanation({'mbti': 'ENTJ'}, None, place)
        actual = explanation({'mbti': 'ENTJ', 'height_cm': height, 'gender': gender}, None, place)
        assert actual == baseline
        assert not any(m['key'].startswith('height') for m in actual['metrics'])
    assert explanation({'height_cm': height}, None, {'category': 'cafe'})['score'] is None


@pytest.mark.parametrize('season,temp', [('spring_warm','warm'),('autumn_warm','warm'),('summer_cool','cool'),('winter_cool','cool')])
def test_color_cast_is_combined_once_and_neutral_is_neutral(season,temp):
    p={'pc_season':season}
    assert metric(p,{'color_temp':temp},'pc_season.color_temp')['points']==28
    assert metric(p,{'color_temp':'neutral'},'pc_season.color_temp')['points']==14
    opposite='cool' if temp=='warm' else 'warm'
    assert metric(p,{'color_temp':opposite},'pc_season.color_temp')['points']==0
    assert 'pc_season.lighting' not in {m['key'] for m in explanation(p,None)['metrics']}


@pytest.fixture
def visitor_db(tmp_path,monkeypatch):
    path=tmp_path/'catalog.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB',str(path))
    catalog.import_response('seoul',{'elements':[
        {'type':'node','id':n,'lat':37.57,'lon':126.97+n*.01,'tags':{'name':f'Cafe {n}','amenity':'cafe'}} for n in range(1,6)]})
    with catalog.connect() as c: ids=[r[0] for r in c.execute('select id from places order by row_id')]
    return ids


def records(pid, count, months=tuple(f'2025-{m:02d}' for m in range(1,13))):
    return [{'place_id':pid,'month':m,'visitors':count,'source_url':'https://example.org/public-admissions',
             'source_label':'Public admissions test fixture','published_at':'2026-10-01','count_basis':'admissions'} for m in months]


def test_global_rank_ties_zero_counts_and_missing_months(visitor_db):
    ids=visitor_db
    visitors.import_records(records(ids[0],100)+records(ids[1],100)+records(ids[2],0)+records(ids[3],500,('2025-11','2025-12')),as_of=date(2026,10,7))
    context, ranked=visitors.rankings(as_of=date(2026,10,7))
    assert context['catalog_count']==5 and context['measured_count']==3
    assert ranked[ids[0]]['rank']==ranked[ids[1]]['rank']==1
    assert ranked[ids[0]]['percentile']==.75
    assert ranked[ids[2]]['rank']==3 and ranked[ids[2]]['visitors']==0
    assert ids[3] not in ranked and ids[4] not in ranked  # missing != zero
    for mbti, expected in [('ENTJ',7.5),('INTJ',2.5)]:
        m=metric({'mbti':mbti},{},'mbti_ei.crowd_level',visitors=ranked[ids[0]])
        assert m['points']==expected and '1,200명' in m['note']
    assert metric({'mbti':'INTJ'},{'crowd_level':'quiet'},'mbti_ei.crowd_level',visitors=context)['status']=='pending'
    assert visitors.rankings(as_of=date(2026,11,1))[1][ids[0]]['visitors'] == 1200  # fixed 2025 reference year


def test_single_place_is_not_invented_into_high_or_low_traffic(visitor_db):
    visitors.import_records(records(visitor_db[0],100),as_of=date(2026,10,7))
    _, ranked=visitors.rankings(as_of=date(2026,10,7))
    assert ranked[visitor_db[0]]['status']=='insufficient'
    assert metric({'mbti':'ENTJ'},{},'mbti_ei.crowd_level',visitors=ranked[visitor_db[0]])['status']=='pending'


@pytest.mark.parametrize('change',[{'visitors':None},{'visitors':-1},{'visitors':1.5},{'visitors':True},
                                  {'count_basis':'reviews'},{'source_url':'http://example.org'},{'published_at':'2026-11-01'},
                                  {'month':'2026-10'},{'place_id':'unmapped'}])
def test_invalid_batch_is_atomic(visitor_db,change):
    batch=records(visitor_db[0],100);batch[2].update(change)
    with pytest.raises((ValueError,TypeError)):
        visitors.import_records(batch,as_of=date(2026,10,7))
    with catalog.connect() as c: assert c.execute('select count(*) from catalog_visitors').fetchone()[0]==0


def test_complete_month_window_handles_year_boundary_and_leap_year():
    assert visitors.recent_months(date(2026,1,5))==['2025-10','2025-11','2025-12']
    assert visitors.recent_months(date(2024,3,1))==['2023-12','2024-01','2024-02']


def test_form_review_is_bound_to_exact_image_and_rejects_non_scene(monkeypatch):
    row={'place_id':'p','photo_url':'https://example.org/a.jpg','source_url':'https://example.org/a',
         'attributes':json.dumps({'form':'linear','color_temp':'warm'}),'method':'photo-geometry-v1'}
    review={**row,'form':'curved','scene_usable':True,'checked_at':'2026-10-07'}
    monkeypatch.setattr(visuals,'REVIEWS',{'p':review})
    assert visuals.reviewed_evidence(row)['attributes']['form']=='curved'
    assert 'form' not in visuals.reviewed_evidence({**row,'photo_url':'https://example.org/b.jpg'})['attributes']
    review['scene_usable']=False
    assert visuals.reviewed_evidence(row) is None


def test_offline_geometry_candidates_distinguish_simple_shapes_and_abstain():
    pytest.importorskip('cv2')
    from pipeline.catalog_geometry import analyze_geometry
    for kind in ['linear','curved','volumetric','blank']:
        im=Image.new('RGB',(640,480),'white');draw=ImageDraw.Draw(im)
        if kind=='linear':
            for x in range(30,610,40): draw.line((x,40,x,430),fill='black',width=3)
        if kind=='curved':
            for x in range(40,580,90):
                for y in range(30,420,90): draw.ellipse((x,y,x+60,y+60),outline='black',width=3)
        if kind=='volumetric': draw.rectangle((150,90,490,390),fill='gray',outline='black',width=4)
        assert analyze_geometry(im)==({} if kind=='blank' else {'form':kind})
