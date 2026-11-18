from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from time import sleep
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest

from api import crowding as c
from api.preview import app

CODE = 'POI009'
PID = '7f590a31-602f-5277-8534-ea1f7d86bc7c'
MUSEUM = 'bfcbd539-f1c5-5dff-97ad-a2fd0d8d8bec'
NOW = datetime(2026, 11, 16, 13, 46, tzinfo=c.KST)
SITE = ('11', '11140', '테스트 관광지')


def seoul(age=30, **overrides):
    row = dict(AREA_CD=CODE, AREA_NM='광화문·덕수궁', AREA_CONGEST_LVL='약간 붐빔', REPLACE_YN='N',
               PPLTN_TIME=(NOW - timedelta(minutes=age)).strftime('%Y-%m-%d %H:%M'))
    return {'RESULT': {'RESULT.CODE': 'INFO-000'}, 'SeoulRtd.citydata_ppltn': [{**row, **overrides}]}


@pytest.mark.parametrize('minutes', [0, 25, 30, 31, 39])
@pytest.mark.parametrize('level', c.LEVELS)
def test_official_level_and_actual_kst_observation(minutes, level):
    value = c.observation(seoul(minutes, AREA_CONGEST_LVL=level), CODE, NOW)
    assert value['level'] == level
    observed = NOW - timedelta(minutes=minutes)
    assert value['observed_at'] == observed.isoformat()
    assert value['expires_at'] == (observed + c.FRESHNESS).isoformat()


@pytest.mark.parametrize('payload', [seoul(40), seoul(180), seoul(-5), seoul(REPLACE_YN='Y'), seoul(REPLACE_YN=None),
                                    seoul(AREA_CD='POI008'), seoul(AREA_NM='경복궁'), seoul(AREA_CONGEST_LVL=''),
                                    seoul(PPLTN_TIME=None), {}, {'RESULT': {'RESULT.CODE': 'ERROR-500'}},
                                    {'RESULT': {'RESULT.CODE': 'INFO-000'}, 'SeoulRtd.citydata_ppltn': []}])
def test_missing_substitutes_and_expired_observations_are_hidden(payload):
    assert c.observation(payload, CODE, NOW) is None


def day(date_string, rate, site=SITE):
    return dict(zip(('areaCd', 'signguCd', 'tAtsNm'), site), baseYmd=date_string, cnctrRate=rate)


def kto(items):
    return {'response': {'header': {'resultCode': '0000'}, 'body': {'items': {'item': items}}}}


def test_forecast_same_site_only_kst_horizon_gaps_and_conflicts():
    data = kto([day('20261115', '2'), day('20261116', '18'), day('20261117', 50, ('11', 'other', SITE[2])),
                day('20261118', 0, ('11', SITE[1], '옆 관광지')), day('20261119', 'NaN'),
                day('20261120', 50), day('20261120', 55), day('20261121', 101), day('20261215', 0),
                day('20261216', 77), day('20261116', 18), None])
    assert c.forecast_days(data, SITE, NOW.date()) == [{'date': '2026-11-16', 'index': 18}, {'date': '2026-12-15', 'index': 0}]
    assert c.forecast_days(kto(day('20261116', 100)), SITE, NOW.date()) == [{'date': '2026-11-16', 'index': 100}]
    truncated = kto([day('20261116', 50)])
    truncated['response']['body']['totalCount'] = 109
    for invalid in [truncated, {}, {'response': {'header': {'resultCode': '03'}, 'body': data['response']['body']}}]:
        assert c.forecast_days(invalid, SITE, date(2026, 11, 16)) == []


def test_shared_reads_coalesce_and_expire(monkeypatch):
    clock, calls = [10], []
    monkeypatch.setattr(c, 'monotonic', lambda: clock[0])
    cache = c.SharedReads()

    def read():
        calls.append(1)
        sleep(.01)
        return {'row': 1}
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda _: cache.get(CODE, read, 300), range(5)))
    assert len(calls) == 1
    clock[0] += 300
    assert cache.get(CODE, read, 300)[0] == {'row': 1}
    assert len(calls) == 2


def test_detail_routes_independent_exact_places_and_canonical_cache(monkeypatch):
    with TestClient(app) as client:
        base = '/preview/crowding'
        monkeypatch.setattr(c, 'find_many', lambda ids: {pid: c.PLACES[pid] for pid in ids})
        monkeypatch.setattr(c, 'reads', c.SharedReads())
        calls = []
        ts = datetime.now(c.KST).replace(second=0, microsecond=0)
        def read(url):
            calls.append(url)
            if url.startswith('https:'):
                return kto(day(ts.strftime('%Y%m%d'), '25'))
            return seoul(PPLTN_TIME=(ts - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M'))
        monkeypatch.setattr(c, 'read_json', read)
        monkeypatch.setenv('PHOTOSPOT_SEOUL_PUBLIC_SAMPLE', '1')
        monkeypatch.setenv('KTO_CONCENTRATION_SERVICE_KEY', 'fixture-only')
        place = c.PLACES[PID]
        site = c.ForecastSite(place['name'], place['lat'], place['lng'], SITE)
        monkeypatch.setattr(c, 'FORECAST_SITES', {PID: site})
        for pid in [PID, MUSEUM]:
            sources = client.get(f'{base}/places/{pid}').json()
            assert sources == {'area': CODE, 'forecast': pid == PID}
            r = client.get(f'{base}/areas/{sources["area"]}')
            assert r.json()['observed_at'].endswith('+09:00') and r.headers['cache-control'] == 'no-store'
            assert r.headers['vercel-cdn-cache-control'].startswith('public, s-maxage=')
        assert len(calls) == 1 and '/sample/' in calls[0] and 'fixture-only' not in calls[0]
        assert client.get(f'{base}/places/{PID}/forecast').json() == [{'date': ts.date().isoformat(), 'index': 25}]
        assert client.get(f'{base}/places/{MUSEUM}/forecast').json() == []
        assert client.get(f'{base}/areas/POI008').json() is None
        assert client.get(f'{base}/places/{uuid4()}').json() == {'area': None, 'forecast': False}
        monkeypatch.delenv('PHOTOSPOT_SEOUL_PUBLIC_SAMPLE')
        assert client.get(f'{base}/places/{PID}').json() == {'area': None, 'forecast': True}
        assert client.get(f'{base}/areas/{CODE}').json() is None
        monkeypatch.setattr(c, 'PLACES', {})
        monkeypatch.setattr(c, 'find_many', lambda ids: {PID: place})
        assert c.place_sources(UUID(PID)) == {'area': None, 'forecast': True}
        monkeypatch.setattr(c, 'find_many', lambda ids: {PID: {**place, 'lat': 37.0}})
        assert c.place_sources(UUID(PID)) == {'area': None, 'forecast': False}
        assert client.get(f'{base}/places/{PID}/forecast').json() == []
