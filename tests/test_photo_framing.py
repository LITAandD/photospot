import pytest

from pipeline import photo_framing
from pipeline.photo_framing import prefer_close_views, thumbnail_rank


@pytest.mark.parametrize('title,description,method', [
    ('File:Cafe_interior.jpg', '', ''),
    ('File:Place.jpg', 'Art Sonje Center front entrance.', ''),
    ('File:서대문 형무소 옥사 내부.jpg', '', ''),
    ('File:카페.jpg', '창가 실내 공간', ''),
    ('File:Garden close-up.jpg', '', ''),
    ('File:Temple courtyard.jpg', '', ''),
    ('File:Place.jpg', '', 'wikidata:P5775'),
])
def test_explicit_nearby_space_cues_are_preferred(title, description, method):
    assert thumbnail_rank(title, description, method) == 0


@pytest.mark.parametrize('title,description', [
    ('File:Aerial view of entrance.jpg', ''),
    ('File:Entrance.jpg', 'The entrance is visible in the distance.'),
    ('File:Village.jpg', 'An overlook of the houses near the entrance.'),
    ('File:파노라마.jpg', '공원 내부 전경'),
    ('File:Portrait at the entrance.jpg', ''),
    ('File:Cafe.jpg', '실내에서 찍은 음식 근접 사진'),
    ('File:Entrance.jpg', '공원의 입구에 있는 간판'),
    ('File:Statue at the entrance (Detail).jpg', ''),
    ('File:Tiles at the palace.jpg', 'Close up of tiles in the courtyard.'),
    ('File:Temple.jpg', 'Interior during a religious ceremony.'),
    ('File:Unknown.jpg', 'The building is inside a library campus.'),
    ('File:Coffee cup close-up.jpg', ''),
    ('File:Place.jpg', 'A long description about the interior: ' + 'history ' * 100),
    ('File:Image001.jpg', ''),
])
def test_far_views_subjects_and_ambiguous_descriptions_are_not_promoted(title, description):
    assert thumbnail_rank(title, description) != 0


def test_close_space_cue_cannot_override_conflicting_interior_photo_metadata():
    assert thumbnail_rank('File:Aerial.jpg', '', 'wikidata:P5775') != 0


def test_only_close_views_move_and_other_photos_keep_source_priority():
    photos = [(2, 'far'), (1, 'unknown'), (0, 'near-a'), (3, 'subject'), (0, 'near-b')]
    assert prefer_close_views(photos) == ['near-a', 'near-b', 'far', 'unknown', 'subject']
    assert prefer_close_views(photos[:2]) == ['far', 'unknown']
    assert prefer_close_views([(2, 'only-far')]) == ['only-far']
    assert prefer_close_views([]) == []


def test_review_is_bound_to_exact_image_and_source(monkeypatch):
    monkeypatch.setattr(photo_framing, 'REVIEWS', {
        ('photo', 'source'): {'framing': 'distant'},
        ('other', 'source'): {'framing': 'close_space'},
    })
    assert thumbnail_rank('Entrance.jpg', photo_url='photo', source_url='source') == 2
    assert thumbnail_rank('Entrance.jpg', photo_url='replacement', source_url='source') == 0
    assert thumbnail_rank('Entrance.jpg', photo_url='photo', source_url='different-source') == 0
    assert thumbnail_rank('Image001.jpg', photo_url='other', source_url='source') == 0


def test_checked_reviews_have_valid_framing_and_provenance():
    assert photo_framing.REVIEWS
    for (photo, source), review in photo_framing.REVIEWS.items():
        assert photo.startswith('https://') and source.startswith('https://commons.wikimedia.org/wiki/File:')
        assert review['framing'] in photo_framing.REVIEW_RANKS
        assert review['checked_at'] and review['notes'] and review['method'] == 'visual-framing-review-v1'
