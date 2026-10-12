from collections import Counter
from pathlib import Path
import shutil

import pytest
from fastapi.encoders import jsonable_encoder

from api import catalog_bridge, catalog_media
from api.preview import PreviewIn, evaluate_response
from pipeline import catalog_photos, catalog_visuals, photo_subjects


COEX = '19ebbf6c-5689-5663-8c51-67031d748215'
AQUARIUM = 'e16ad092-e44c-549c-b25f-bba9cc766926'


@pytest.fixture
def catalog_db(tmp_path, monkeypatch):
    path = tmp_path / 'places.sqlite3'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'catalog/places.sqlite3', path)
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    return path


def test_reviewed_venue_requires_exact_approved_photo_but_allows_incidental_visitors():
    review = next(p for p in photo_subjects.REVIEWS['places'] if p['place_id'] == COEX)
    photos = {p['file_title']: p for p in review['photos']}
    for title in ['File:Coexfile06.jpg', 'File:COEX cafe show 2022.jpg']:
        space = photos[title]  # People are visible, but the corridor/lobby is the subject.
        assert photo_subjects.recommended_photo(COEX, space['photo_url'], space['source_url'])
        assert not photo_subjects.recommended_photo(COEX, 'https://example.org/replacement.jpg', space['source_url'])
        assert not photo_subjects.recommended_photo(COEX, space['photo_url'], 'https://example.org/other-source')
    person = photos['File:151216 서울 캐릭터 라이선싱 페어 동우 1.jpg']
    assert not photo_subjects.recommended_photo(COEX, person['photo_url'], person['source_url'])
    assert not photo_subjects.recommended_photo(AQUARIUM, person['photo_url'], person['source_url'])
    assert photo_subjects.recommended_photo(AQUARIUM, 'unreviewed-photo', 'source')


def test_checked_subject_reviews_have_unique_assets_and_provenance():
    for place in photo_subjects.REVIEWS['places']:
        assert place['policy'] == 'reviewed_spaces_only'
        assert place['method'] == 'visual-space-subject-review-v1'
        assert place['checked_at'] and place['place_name'] and place['source_category'].startswith('https://')
        assert len({(p['photo_url'], p['source_url']) for p in place['photos']}) == len(place['photos'])
        for photo in place['photos']:
            assert photo['subject'] in {'space', 'person', 'performance', 'other', 'unverified'}
            assert photo['notes'] and photo['photo_url'].startswith('https://')
            assert photo['source_url'].startswith('https://commons.wikimedia.org/wiki/File:')
    coex = next(p for p in photo_subjects.REVIEWS['places'] if p['place_id'] == COEX)
    assert Counter(p['subject'] for p in coex['photos']) == {
        'space': 18, 'person': 13, 'performance': 53, 'other': 10, 'unverified': 4}


@pytest.mark.parametrize('allow_brand', [False, True])
def test_coex_feed_gallery_counts_and_bookmarks_share_only_space_photos(catalog_db, monkeypatch, allow_brand):
    monkeypatch.setenv('ALLOW_OFFICIAL_BRAND_PHOTOS', '1' if allow_brand else '0')
    def no_download(*args, **kwargs):
        raise AssertionError('Public requests must apply offline reviews without downloads')
    monkeypatch.setattr(catalog_photos.PublicClient, 'get', no_download)
    monkeypatch.setattr(catalog_visuals, 'read_photo', no_download)
    photos = catalog_media.photos_for([COEX])[COEX]
    approved = photo_subjects.SPACE_PHOTOS[COEX]
    assert {(p['url'], p['source_url']) for p in photos} == approved
    assert len(photos) == catalog_media.photo_counts_for([COEX])[COEX] == catalog_photos.photo_counts_for([COEX])[COEX] == 18
    assert photos[0]['title'] == 'Ko-wiki-10th-L1070071.JPG'  # Close entrance, not a portrait.
    assert catalog_bridge.bookmark_rows([COEX])[COEX]['cover_photo'] == photos[0]
    result = jsonable_encoder(evaluate_response(PreviewIn(visit_date='2026-10-13', lat=37.512, lng=127.059,
                                                         place_ids=[COEX], include_gallery=True)))
    detail = result['places'][COEX]
    item = next(p for p in result['recommendations']['items'] if p['place_id'] == COEX)
    assert detail['photos'] == photos and item['cover_photo'] == photos[0]
    assert detail['discovery']['photo_count'] == item['discovery']['photo_count'] == 18


def test_reimport_and_unknown_photo_cannot_restore_hidden_portraits(catalog_db):
    with catalog_photos.catalog.connect(catalog_db) as conn:
        person = dict(conn.execute("SELECT * FROM catalog_photos WHERE place_id=? AND file_title LIKE '%동우 1.jpg'", (COEX,)).fetchone())
        original_count = conn.execute('SELECT count(*) FROM catalog_photos WHERE place_id=?', (COEX,)).fetchone()[0]
    catalog_photos.store_photos([person], catalog_db)  # A regular refresh of an excluded image.
    unknown = {**person, 'file_title': 'File:New venue category photo.jpg', 'url': person['url'] + '&version=new'}
    catalog_photos.store_photos([unknown], catalog_db)
    assert len(catalog_photos.photos_for([COEX], catalog_db)[COEX]) == 18
    with catalog_photos.catalog.connect(catalog_db) as conn:
        # Exclusion is reversible and retains original source/licence records.
        assert conn.execute('SELECT count(*) FROM catalog_photos WHERE place_id=?', (COEX,)).fetchone()[0] == original_count + 1
    aquarium_before = catalog_photos.photo_counts_for([AQUARIUM], catalog_db)[AQUARIUM]
    catalog_photos.store_photos([{**person, 'place_id': AQUARIUM}], catalog_db)
    assert catalog_photos.photo_counts_for([AQUARIUM], catalog_db)[AQUARIUM] == aquarium_before
    catalog_visuals.store(COEX, person, {'color_temp': 'warm'}, 'test-photo-color', catalog_db)
    assert COEX not in catalog_visuals.evidence_for([COEX], catalog_db)


def test_portrait_only_gallery_has_no_cover_fallback_or_photo_count(catalog_db):
    with catalog_photos.catalog.connect(catalog_db) as conn:
        for url, source in photo_subjects.SPACE_PHOTOS[COEX]:
            conn.execute('DELETE FROM catalog_photos WHERE place_id=? AND url=? AND source_url=?', (COEX, url, source))
    assert not catalog_photos.photos_for([COEX], catalog_db).get(COEX)
    assert not catalog_photos.photo_counts_for([COEX], catalog_db).get(COEX)
    assert catalog_bridge.bookmark_rows([COEX])[COEX]['cover_photo'] is None


def test_partial_reviews_exclude_portraits_across_every_linked_place(catalog_db):
    reviews = photo_subjects.REVIEWS['photos']
    affected = {p['place_id'] for photo in reviews for p in photo['places']}
    galleries = catalog_photos.photos_for(affected, catalog_db)
    counts = catalog_photos.photo_counts_for(affected, catalog_db)
    bookmarks = catalog_bridge.bookmark_rows(affected)
    assert affected and COEX not in affected
    for pid in affected:
        photos = galleries.get(pid, [])
        assert counts.get(pid, 0) == len(photos)
        assert bookmarks[pid]['cover_photo'] == (photos[0] if photos else None)
        assert all(photo_subjects.source_key(p['source_url']) not in photo_subjects.PEOPLE_SOURCES for p in photos)
    for photo in reviews:
        assert photo['method'] in {'visual-space-subject-review-v1', 'source-description-subject-review-v1'}
        if photo['method'] == 'source-description-subject-review-v1':
            assert photo['source_description'] and photo['file_title']
        assert photo['subject'] in {'person', 'performance'}
        assert photo['checked_at'] and photo['notes'] and photo['places']
        for pid in affected:
            assert not photo_subjects.recommended_photo(pid, photo['photo_url'], photo['source_url'])


def test_blocked_commons_asset_stays_blocked_after_thumbnail_refresh():
    from urllib.parse import quote, unquote
    person = photo_subjects.REVIEWS['photos'][0]
    source = person['source_url']
    title = unquote(source.split('/wiki/File:')[1]).replace('_', ' ')
    variant = 'https://commons.wikimedia.org/wiki/File:' + quote(title) + '?uselang=ko'
    assert not photo_subjects.recommended_photo(AQUARIUM, 'https://example.org/new-size.jpg', variant)
    assert not photo_subjects.recommended_photo(AQUARIUM, person['photo_url'], 'changed-source')
    # A different file, even one whose name starts with the blocked title, is not a match.
    assert photo_subjects.recommended_photo(AQUARIUM, 'other-photo', source + '.different.jpg')


def test_shared_source_page_does_not_hide_other_space_photos(monkeypatch):
    source = 'https://example.org/venue-gallery'
    monkeypatch.setattr(photo_subjects, 'PEOPLE_URLS', {'https://example.org/portrait.jpg'})
    assert photo_subjects.source_key(source) is None
    assert photo_subjects.source_key('https://[invalid') is None
    assert not photo_subjects.recommended_photo(AQUARIUM, 'https://example.org/portrait.jpg', source)
    assert photo_subjects.recommended_photo(AQUARIUM, 'https://example.org/interior.jpg', source)


def test_partial_review_preserves_incidental_visitors_and_sculptures(catalog_db):
    with catalog_photos.catalog.connect(catalog_db) as conn:
        examples = conn.execute("""SELECT place_id,url,source_url FROM catalog_photos
            WHERE file_title IN ('File:National Museum Korea Pompeii 02 (15947040626).jpg',
                                 'File:National Palace Museum 20170303 04 (33179754076).jpg',
                                 'File:National Museum Korea Special Exhibition 15 (15390680862).jpg',
                                 'File:Scene of man painting, Unhyeongung palace.jpg',
                                 'File:Unhyeongung palace scene.jpg')""").fetchall()
    assert len(examples) == 5
    for row in examples:
        assert photo_subjects.recommended_photo(row['place_id'], row['url'], row['source_url'])


def test_partial_portrait_only_venue_has_no_cover_or_visual_evidence(catalog_db):
    person = photo_subjects.REVIEWS['photos'][0]
    pid = person['places'][0]['place_id']
    with catalog_photos.catalog.connect(catalog_db) as conn:
        conn.execute('DELETE FROM catalog_photos WHERE place_id=? AND url<>?', (pid, person['photo_url']))
    assert not catalog_photos.photos_for([pid], catalog_db).get(pid)
    assert not catalog_photos.photo_counts_for([pid], catalog_db).get(pid)
    assert catalog_bridge.bookmark_rows([pid])[pid]['cover_photo'] is None
    catalog_visuals.store(pid, {'url': person['photo_url'], 'source_url': person['source_url']},
                          {'color_temp': 'warm'}, 'test-photo-color', catalog_db)
    assert pid not in catalog_visuals.evidence_for([pid], catalog_db)


def test_preview_replaces_yongsan_portrait_cover_and_keeps_gallery_counts(catalog_db):
    pid = 'a5c720d7-51f9-5710-bd24-4a678a7a318a'
    portrait = next(p for p in photo_subjects.REVIEWS['photos']
                    if p['file_title'] == 'File:HanSongi-photo by HunkinElvis2.JPG')
    result = jsonable_encoder(evaluate_response(PreviewIn(visit_date='2026-10-13', lat=37.523, lng=126.983,
                                                         place_ids=[pid], include_gallery=True)))
    photos = result['places'][pid]['photos']
    item = next(p for p in result['recommendations']['items'] if p['place_id'] == pid)
    assert all(p['url'] != portrait['photo_url'] for p in photos)
    assert item['cover_photo'] == (photos[0] if photos else None)
    assert result['places'][pid]['discovery']['photo_count'] == item['discovery']['photo_count'] == len(photos)


def test_replacement_cover_skips_consecutive_portraits(catalog_db):
    expected = {
        '세종문화회관': 'Sejong Center and MOFA along Sejong-daero in 2020.jpg',
        '세종문화회관 대극장': 'Sejong Center and MOFA along Sejong-daero in 2020.jpg',
        '홍난파 가옥': "Hong Nanpa's house.JPG",
    }
    with catalog_photos.catalog.connect(catalog_db) as conn:
        places = conn.execute('SELECT id,name FROM places WHERE name IN (?,?,?)', tuple(expected)).fetchall()
    assert len(places) == 3
    for pid, name in places:
        photos = catalog_photos.photos_for([pid], catalog_db)[pid]
        assert photos[0]['title'] == expected[name]
        assert catalog_bridge.bookmark_rows([pid])[pid]['cover_photo'] == photos[0]
