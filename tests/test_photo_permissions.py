import pytest

from api.catalog_media import cover_thumbnail
from api.catalog_scoring import explanation
from api import photo_likes
from pipeline import catalog_visuals
from pipeline.photo_permissions import allowed, TYPE3


@pytest.mark.parametrize('path', ['by-nd/4.0/', 'BY-ND/4.0/', 'By-Nd/3.0/deed.ko'])
def test_no_derivatives_is_case_insensitive(path, tmp_path, monkeypatch):
    photo = {'license_url': 'https://creativecommons.org/licenses/' + path,
             'url': 'https://upload.wikimedia.org/photo.jpg', 'source_url': 'https://commons.wikimedia.org/wiki/File:Photo'}
    assert allowed(photo) and not allowed(photo, modify=True)
    monkeypatch.setattr(catalog_visuals, 'read_photo', lambda _: pytest.fail('Restricted photo fetched'))
    assert not photo_likes.analyze_photo('place', photo)
    with pytest.raises(ValueError, match='license'):
        catalog_visuals.store('place', photo, {'color_temp': 'warm'}, 'test', tmp_path / 'copy.sqlite3')


@pytest.mark.parametrize('url', [
    'https://creativecommons.org/licenses/by/9.9/',
    'https://creativecommons.org/licenses/by-sa/0.0/',
    'https://creativecommons.org.evil.test/licenses/by/4.0/',
    'https://creativecommons.org/licenses/by/4.0/?permission=yes', '',
])
def test_unknown_license_cannot_enable_display_or_processing(url):
    photo = {'license_url': url, 'license': 'CC BY', 'url': 'https://upload.wikimedia.org/a.jpg', 'original_url': 'original'}
    assert not allowed(photo) and not allowed(photo, modify=True)
    assert cover_thumbnail(photo) == 'original'


@pytest.mark.parametrize('url', [TYPE3, 'https://creativecommons.org/licenses/BY-ND/4.0/', ''])
def test_license_reason_is_distinct_from_visual_review(url, tmp_path):
    diag = {}
    evidence = catalog_visuals.evidence_for(['p'], tmp_path / 'copy.sqlite3',
        selected_photos={'p': [{'license_url': url}]}, diagnostics=diag)
    assert evidence == {} and diag == {'p': 'license_restricted'}
    result = explanation({'pc_season': 'winter_cool'}, None, photo_status=diag['p'])
    assert result['score'] is None
    assert result['metrics'][0]['evidence_status'] == 'license_restricted'
    assert '이용 조건' in result['metrics'][0]['note']


@pytest.mark.parametrize('version', ['1.0', '2.0', '2.5', '3.0', '4.0'])
def test_supported_attribution_licenses_remain_usable(version):
    assert allowed({'license_url': f'https://creativecommons.org/licenses/by-sa/{version}/'}, modify=True)
