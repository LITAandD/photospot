import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.schemas import PoseReference
from pipeline import pose_reference


def test_reviews_are_valid_and_bound_to_exact_image_and_source():
    rows = json.loads((Path(__file__).parents[1] / 'pipeline/data/pose_reference_reviews.json').read_text(encoding='utf-8'))
    assert len(rows) == len(pose_reference.REVIEWS)
    for row in rows:
        reference = pose_reference.reference_for(row['photo_url'], row['source_url'])
        assert PoseReference.model_validate(reference).height_ratio == pytest.approx(row['foot_y'] - row['head_y'], abs=1e-6)
        assert row['notes'] and row['checked_at'] and row['method'] == 'visible-person-proportion-review-v1'
        assert pose_reference.reference_for('replacement-photo', row['source_url']) is None
        assert pose_reference.reference_for(row['photo_url'], 'different-source') is None


@pytest.mark.parametrize('height,foot', [(0, 0.8), (0.9, 0.5), (0.2, 1.1), (float('nan'), 0.5)])
def test_invalid_reference_bounds_are_rejected(height, foot):
    with pytest.raises(ValidationError):
        PoseReference(height_ratio=height, foot_y=foot)


def test_catalog_fixture_serves_reviewed_person_without_network(tmp_path, monkeypatch):
    from scripts.load_catalog_fixture import main
    from pipeline.catalog_photos import photos_for, PublicClient
    from api.preview import PreviewIn, evaluate

    monkeypatch.setenv('PLACE_CATALOG_DB', str(tmp_path / 'ci.sqlite3'))
    monkeypatch.setattr(PublicClient, 'get', lambda *args, **kwargs: pytest.fail('No request-time photo analysis'))
    main()
    pid = 'eea36a6f-7c1c-5298-abcd-3264abbe671a'
    photos = photos_for([pid])[pid]
    assert photos[0]['pose_reference']['height_ratio'] == pytest.approx(172 / 640, abs=2e-6)
    assert photos[0]['pose_reference']['foot_y'] == pytest.approx(425 / 640, abs=1e-6)
    result = evaluate(PreviewIn(visit_date='2026-10-12', place_ids=[pid]))
    detail = result['places'][pid]
    cover = next(item.cover_photo for item in result['recommendations'].items if item.place_id == pid)
    assert cover.pose_reference == detail.photos[0].pose_reference
    assert cover.pose_reference.height_ratio == pytest.approx(172 / 640, abs=2e-6)
    assert any(photo['pose_reference'] is None for photo in photos[1:])
