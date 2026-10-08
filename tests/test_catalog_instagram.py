import json
import sqlite3
from datetime import date

import pytest

from pipeline import catalog_instagram as instagram, dining_curation, place_catalog as catalog
from api.preview import PreviewIn, evaluate
from scripts.export_catalog import export


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / 'places.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    dining_curation.apply(path)
    return path


@pytest.mark.parametrize('url', [
    'http://www.instagram.com/p/ABCDE123/', 'https://instagram.com.evil.test/p/ABCDE123/',
    'https://www.instagram.com@evil.test/p/ABCDE123/', 'https://user@www.instagram.com/p/ABCDE123/',
    'https://www.instagram.com:443/p/ABCDE123/', 'https://www.instagram.com/cafe/',
    'https://www.instagram.com/stories/cafe/123456/', 'javascript:alert(1)', None,
])
def test_only_public_post_url_shapes_are_accepted(url):
    with pytest.raises(ValueError):
        instagram.canonical_post(url)


def test_post_normalization():
    assert instagram.canonical_post('https://instagram.com/cafe/reel/ABCDE123?utm_source=ig#caption') == 'https://www.instagram.com/reel/ABCDE123/'


def test_import_is_idempotent_and_withdraws_removed_references(db, tmp_path):
    assert instagram.posts_for(['missing'], db) == {}
    expected = {'places': 5, 'posts': 6}
    assert instagram.apply(db) == instagram.apply(db) == expected
    manifest = json.loads(instagram.MANIFEST.read_text(encoding='utf-8'))
    manifest['posts'] = manifest['posts'][:1]
    subset = tmp_path / 'subset.json'
    subset.write_text(json.dumps(manifest), encoding='utf-8')
    assert instagram.apply(db, subset) == {'places': 1, 'posts': 1}
    with catalog.connect(db) as conn:
        pid = conn.execute('SELECT place_id FROM catalog_instagram').fetchone()[0]
        assert len(instagram.posts_for([pid], db)[pid]) == 1
        conn.execute('UPDATE places SET active=0 WHERE id=?', (pid,))
    assert not instagram.posts_for([pid], db)


def test_invalid_branch_or_post_rolls_back_the_whole_import(db, tmp_path):
    instagram.apply(db)
    manifest = json.loads(instagram.MANIFEST.read_text(encoding='utf-8'))
    bad = tmp_path / 'bad.json'
    manifest['posts'][-1]['place_name'] = '다른 지점'
    bad.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='Unmatched dining branch'):
        instagram.apply(db, bad)
    with catalog.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM catalog_instagram').fetchone()[0] == 6
    manifest['posts'][-1] = manifest['posts'][0]  # duplicate primary key, fails after DELETE
    bad.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(sqlite3.IntegrityError):
        instagram.apply(db, bad)
    with catalog.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM catalog_instagram').fetchone()[0] == 6


def test_preview_exposes_posts_without_changing_photo_evidence_or_ranking(db):
    body = PreviewIn(visit_date=date.today(), lat=37.579, lng=126.987, radius_m=50000,
                     place_group='cafe', profile={'height_cm': 160})
    before = evaluate(body)
    instagram.apply(db)
    after = evaluate(body)
    assert [i.place_id for i in before['recommendations'].items] == [i.place_id for i in after['recommendations'].items]
    assert any(i.instagram_post_count for i in after['recommendations'].items)
    for old, new in zip(before['recommendations'].items, after['recommendations'].items):
        assert old.scoring == new.scoring
        assert old.cover_photo == new.cover_photo
        detail = after['places'][new.place_id]
        assert len(detail.instagram_posts) == new.instagram_post_count
        assert detail.photos == before['places'][new.place_id].photos
    assert not any(p.photos for p in after['places'].values())


def test_export_contains_public_references_but_no_private_tables(db, tmp_path):
    instagram.apply(db)
    with catalog.connect(db) as conn:
        conn.execute('CREATE TABLE private_accounts(secret TEXT)')
        conn.execute("INSERT INTO private_accounts VALUES ('test-only')")
    dest = tmp_path / 'public.sqlite3'
    export(dest)
    with sqlite3.connect(dest) as conn:
        assert conn.execute('SELECT count(*) FROM catalog_instagram').fetchone()[0] == 6
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='private_accounts'").fetchone()
