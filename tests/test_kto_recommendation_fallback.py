import copy
import json
import logging

from fastapi.testclient import TestClient
import pytest

from api.preview import app
from pipeline import tourism_photos as kto
from tests.photo_review_fixture import kto_catalog  # noqa: F401


@pytest.mark.parametrize('damage', ['missing', 'unreadable', 'invalid-json', 'wrong-shape', 'one-invalid', 'duplicate', 'bad-rights'])
def test_only_unverifiable_covers_disappear(kto_catalog, caplog, damage):
    _, path, original, covers, _ = kto_catalog
    target = original[0]
    if damage == 'missing':
        path.unlink()
    elif damage == 'unreadable':
        path.unlink()
        path.mkdir()
    elif damage == 'invalid-json':
        path.write_bytes(b'{')
    elif damage == 'wrong-shape':
        path.write_bytes(b'{}')
    else:
        rows = copy.deepcopy(original)
        if damage == 'one-invalid':
            rows[0] = None
        elif damage == 'duplicate':
            rows.append(copy.deepcopy(target))
        else:
            rows[0]['review']['permissions']['crop'] = False
        path.write_text(json.dumps(rows), encoding='utf-8')
    partial = damage in {'one-invalid', 'duplicate', 'bad-rights'}
    with caplog.at_level(logging.WARNING, logger=kto.__name__), TestClient(app, raise_server_exceptions=False) as client:
        for city, expected in covers.items():
            response = client.get(f'/preview/browse?city={city}&visit_date=2026-11-22')
            assert response.status_code == 200
            items = response.json()['items']
            assert {item['place_id'] for item in items} == set(expected)
            actual = {item['cover_photo']['url'] for item in items if item['cover_photo']}
            assert actual == {url for url in expected.values() if 'tong.visitkorea.or.kr' not in url or
                              (partial and url != target['photo']['url'])}
        kto.reviewed_records()
    assert len([r for r in caplog.records if r.name == kto.__name__]) == 1


def test_duplicate_input_is_rejected_before_fetch_or_write(kto_catalog):
    path, _, records, _, _ = kto_catalog
    before = path.read_bytes()
    with pytest.raises(ValueError, match='Duplicate review'):
        kto.apply(path, [records[0], records[0]], lambda _: pytest.fail('Unexpected download'))
    assert path.read_bytes() == before
