"""Small synthetic catalog, independent of production names and top-12 composition."""
from datetime import date
import hashlib
from io import BytesIO
import json

from PIL import Image
import pytest

from api.public_place_info import ORIGINS
from pipeline import place_catalog as catalog, catalog_photos as photos, tourism_photos as kto
from tests.test_catalog_photos import image_page


@pytest.fixture
def kto_catalog(tmp_path, monkeypatch):
    path = tmp_path / 'test.sqlite3'
    manifest = tmp_path / 'reviews.json'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    monkeypatch.setattr(kto, 'MANIFEST', manifest)
    monkeypatch.setattr(kto, 'today', lambda: date(2026, 11, 18))
    image = BytesIO()
    Image.new('RGB', (120, 100), 'white').save(image, 'JPEG')
    raw = image.getvalue()
    records, covers = [], {}
    for city_index, city in enumerate(('gangneung', 'jeju')):
        origin = ORIGINS[city]
        catalog.import_response(city, {'elements': [
            {'type': 'node', 'id': 100 + city_index * 10 + n,
             'lat': origin['lat'] + n * .001, 'lon': origin['lng'],
             'tags': {'name': f'Fixture {city} {n}', 'tourism': 'museum', 'addr:street': 'Fixture Road'}}
            for n in range(3)]}, path)
        places = catalog.search(origin['lat'], origin['lng'], 5000, path=path)
        covers[city] = {}
        for n, place in enumerate(places):
            pid = place['id']
            if n == 2:
                photo = photos.reusable_image(image_page())
                photos.store_photos([{**photo, 'place_id': pid, 'match_method': 'reviewed:branch',
                                      'match_ref': 'fixture', 'priority': 1}], path)
                covers[city][pid] = photo['url']
                continue
            key = str(1000 + city_index * 10 + n)
            url = f'https://tong.visitkorea.or.kr/cms/resource/0/{key}.jpg'
            record = dict(provider='kor', provider_id=key,
                place={field: place[field] for field in kto.PLACE_FIELDS},
                provider_place=dict(contentid=key, title=place['name'], addr1='Fixture Road',
                                    mapy=place['lat'], mapx=place['lng']),
                photo=dict(url=url, provider_original=url, provider_id=key, sha256=hashlib.sha256(raw).hexdigest(),
                           width=120, height=100, title='Synthetic spatial fixture', credit='Fixture provider',
                           license_url=kto.TYPE1, license_code='Type1', operation='detailImage2'),
                review=dict(status='approved', checked_at='2026-11-18', subject='ground_level_space',
                            third_party_cleared=True, permissions={k: True for k in
                            ('display', 'store', 'resize', 'crop', 'color_analysis', 'form_analysis')},
                            **{k: 'Synthetic test evidence' for k in ('reviewer', 'match_evidence',
                            'rights_evidence', 'subject_review', 'credit_basis')}))
            records.append(record)
            covers[city][pid] = url
            row = kto.public_row(record, place)
            with catalog.connect(path) as conn:
                photos.initialize(conn)
                conn.execute(f"INSERT INTO catalog_photos ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
    manifest.write_text(json.dumps(records), encoding='utf-8')
    kto.reviewed_records.cache_clear()
    try:
        yield path, manifest, records, covers, raw
    finally:
        kto.reviewed_records.cache_clear()
