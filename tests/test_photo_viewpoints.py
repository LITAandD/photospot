import shutil
from pathlib import Path
from urllib.parse import quote, unquote

import pytest
from fastapi import HTTPException

from api import catalog_bridge, catalog_media, photo_likes, photo_like_routes
from pipeline import catalog_photos, catalog_visuals, photo_subjects
from pipeline.photo_identity import photo_id
from pipeline.photo_viewpoints import REVIEWS, bird_view


@pytest.mark.parametrize('caption', [
    'Aerial view of a courtyard', 'Seoul_Aerial_Shot_01.jpg',
    "Bird's-eye view of the park", 'Bird eye view', 'Bird view', 'Bird’s eye view',
    'Birds-eye view of the beach', 'Drone photograph of the coast',
    'Overhead view of the mall', 'Top-down view of a courtyard', 'View from above',
    'View from the helicopter', 'From the view of a helicopter.',
    '항공 사진', '드론 촬영', '조감뷰', '조감도', '부감 사진', '버드 아이 뷰',
    'View from Busan Tower', 'Seoul City Core from N-Seoul Tower',
    'Seoul Olympic Park seen from the Lotte World Tower observation deck',
])
def test_explicit_bird_view_metadata_is_excluded(caption):
    assert bird_view(title=caption)
    assert bird_view(description=caption)
    assert bird_view(source_url='https://commons.wikimedia.org/wiki/File:' + quote(caption.replace(' ', '_')))


@pytest.mark.parametrize('title,description', [
    ('Gwangan bridge panorama', 'View from the beach.'),
    ('View of the skyline', 'Photographed at street level.'),
    ('전경.jpg', '공원 입구에서 본 풍경'),
    ('Bird in a park.jpg', 'Bird eye and feathers'),
    ('Helicopter.jpg', 'Aircraft on display in the museum.'),
    ('Aerial ropeway entrance', 'The ticket counter at ground level.'),
    ('Drone show.jpg', 'A drone show above the park.'),
    ('Tower.jpg', 'The inside of the observation deck.'),
    ('View from the base of Lotte World Tower', ''),
    ('View from near N Seoul Tower', ''),
    ('Cheonggyecheon with skyscrapers', 'Cheonggyecheon seen from Gwanggyo bridge in Seoul. '
     'Some skyscrapers can be seen in the background; from left to right: Signature Tower and Mirae Asset Center.'),
    ('Courtyard', 'This photo shows the entrance. ' + 'History of the space. ' * 30 + 'An aerial view was used in a 1950 map.'),
])
def test_eye_level_and_unrelated_words_are_not_bird_views(title, description):
    assert not bird_view(title=title, description=description)


def test_reviewed_asset_cannot_return_with_new_size_or_different_venue():
    review = next(r for r in REVIEWS if r['source_url'].startswith('https://commons.wikimedia.org/wiki/File:'))
    name = unquote(review['source_url'].split('/wiki/File:')[1]).replace('_', ' ')
    source = 'https://commons.wikimedia.org/wiki/File:' + quote(name) + '?uselang=ko'
    assert bird_view('https://example.com/new-thumbnail.jpg', source, 'Interior entrance')
    assert not photo_subjects.recommended_photo('different-place', 'new-size', source)
    assert bird_view(review['photo_url'], 'https://example.com/new-source')
    assert not bird_view('new-file', review['source_url'] + '.different.jpg')
    assert not bird_view('https://example.com/interior.jpg?label=aerial_view', 'source')


def test_shared_blog_does_not_block_other_photos():
    review = next(r for r in REVIEWS if 'blog.naver.com' in r['source_url'])
    assert bird_view(review['photo_url'], review['source_url'])
    assert not bird_view('https://example.com/eye-level.jpg', review['source_url'])


@pytest.mark.parametrize('query', ['', '?type=w966', '?type=w773&tracking=refresh'])
def test_naver_thumbnail_refresh_cannot_restore_reviewed_image(query):
    review = next(r for r in REVIEWS if 'postfiles.pstatic.net' in r['photo_url'])
    path = review['photo_url'].split('?')[0]
    assert bird_view(path + query, review['source_url'])
    assert bird_view(path + query, 'https://example.com/another-place', 'Interior')
    assert not bird_view(path + '.different.jpg' + query, review['source_url'])
    assert not bird_view(path.replace('postfiles.pstatic.net', 'example.com') + query, review['source_url'])


@pytest.fixture
def catalog_db(tmp_path, monkeypatch):
    path = tmp_path / 'places.sqlite3'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'catalog/places.sqlite3', path)
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    return path


def test_feed_gallery_bookmarks_counts_and_like_ranking_use_filtered_photos(catalog_db):
    ids = list({place['place_id'] for review in REVIEWS for place in review['places']})
    photos = catalog_media.photos_for(ids)
    counts = catalog_photos.photo_counts_for(ids, catalog_db)
    # Even a million historical likes cannot bring a rejected asset back.
    votes = {(place['place_id'], photo_id({'url': review['photo_url'], 'source_url': review['source_url']})):
             {'like_count': 1_000_000, 'liked': True} for review in REVIEWS for place in review['places']}
    ranked = photo_likes.rank(photos, votes, True)
    bookmarks = catalog_bridge.bookmark_rows(ids)
    for pid in ids:
        gallery = photos.get(pid, [])
        assert counts.get(pid, 0) == len(gallery)
        assert all(not bird_view(p['url'], p['source_url'], p['title']) for p in ranked.get(pid, []))
        cover = bookmarks[pid]['cover_photo']
        assert (cover['url'] if cover else None) == (gallery[0]['url'] if gallery else None)
    for review in REVIEWS:
        assert review['checked_at'] and review['notes'] and review['places']
        assert review['viewpoint'] == 'bird_view' and review['method'] == 'visual-viewpoint-review-v1'
        assert not any(p['url'] == review['photo_url'] for group in photos.values() for p in group)


def test_only_bird_views_have_no_fallback_or_scoring_evidence_or_likes(catalog_db, monkeypatch):
    pid = 'b37247e2-4c03-559b-bd1d-e303b51354aa'  # 문화비축기지: only a reviewed aerial photo.
    review = next(r for r in REVIEWS if any(p['place_id'] == pid for p in r['places']))
    assert not catalog_media.photos_for([pid]).get(pid)
    assert catalog_photos.photo_counts_for([pid], catalog_db).get(pid, 0) == 0
    assert catalog_bridge.bookmark_rows([pid])[pid]['cover_photo'] is None
    photo = {'url': review['photo_url'], 'source_url': review['source_url']}
    catalog_visuals.store(pid, photo, {'color_temp': 'warm'}, 'old-photo-analysis', catalog_db)
    assert pid not in catalog_visuals.evidence_for([pid], catalog_db)
    monkeypatch.setattr(photo_likes, 'set_like', lambda *args: pytest.fail('Excluded photos must never write votes'))
    with pytest.raises(HTTPException) as error:
        photo_like_routes.change_like(pid, photo_like_routes.LikeIn(photo_id=photo_id(photo), liked=True), 'viewer')
    assert error.value.status_code == 404


def test_new_import_metadata_and_official_gallery_share_the_same_filter(catalog_db, monkeypatch):
    pid = 'b37247e2-4c03-559b-bd1d-e303b51354aa'
    with catalog_photos.catalog.connect(catalog_db) as conn:
        conn.execute('UPDATE catalog_photos SET url=?,source_url=?,file_title=?,description=? WHERE place_id=?',
                     ('https://example.com/new.jpg', 'https://example.com/new', 'New photo.jpg', 'Drone shot of the park.', pid))
    assert not catalog_photos.photos_for([pid], catalog_db).get(pid)
    assert not catalog_photos.photo_counts_for([pid], catalog_db).get(pid)
    from pipeline import place_editorial
    monkeypatch.setattr(place_editorial, 'official_photos_for', lambda ids: {pid: [
        {'url': 'https://example.com/aerial.jpg', 'source_url': 'https://example.com/gallery', 'title': '항공 촬영'},
        {'url': 'https://example.com/entrance.jpg', 'source_url': 'https://example.com/gallery', 'title': '입구'},
    ]})
    assert [p['title'] for p in catalog_photos.photos_for([pid], catalog_db)[pid]] == ['입구']
    assert catalog_photos.photo_counts_for([pid], catalog_db)[pid] == 1
