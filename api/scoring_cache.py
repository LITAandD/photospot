"""요청 간에 재사용하는 장소별 정적 값. 카탈로그 파일(경로·수정 시각·크기)이 바뀌면 전부 비운다.

/preview/evaluate는 후보 수천 곳에 같은 정규식·JSON 파싱을 매 요청 되풀이했다(F005). 프로필·날짜와
무관한 값만 여기 둔다: 공개 사진 목록(catalog_media), 설명문 S/N 판정과 지도 분류 T/F 판정
(scoring_features), 오행 해석(elements_for), 중복 장소 판정용 격자(NearbyIndex).
호출부가 값을 바꿔도 캐시가 오염되지 않게 얕은 복사본을 돌려준다.
"""
import json
import os

from pipeline import place_catalog as catalog
from pipeline.catalog_mbti import description_character, space_nature
from pipeline.place_editorial import resolve_elements

_stores: dict[str, dict] = {}
_version: tuple | None = None


_DEFAULT_DB = str(catalog.DEFAULT_DB)


def catalog_version():
    """현재 카탈로그 파일의 식별자. 파일이 바뀌면(재배포·테스트 DB 갱신·교체) 값이 달라진다.

    장소마다 한 번씩 불리므로 pathlib 없이 stat 한 번으로 끝낸다(약 2µs).
    """
    path = os.environ.get('PLACE_CATALOG_DB') or _DEFAULT_DB
    try:
        st = os.stat(path)
    except OSError:
        return (path, None)
    return (path, st.st_ino, st.st_mtime_ns, st.st_size)


def store(name):
    """이름별 dict. 카탈로그 파일이 바뀌었으면 모든 저장소를 비우고 새로 시작한다."""
    global _version
    version = catalog_version()
    if version != _version:
        _stores.clear()
        _version = version
    return _stores.setdefault(name, {})


def clear():
    global _version
    _stores.clear()
    _version = None


def memo(name, key, compute):
    cache = store(name)
    if key not in cache:
        cache[key] = compute()
    return cache[key]


def _tags_key(place):
    tags = place.get('tags')
    if not tags: return ''
    return tags if isinstance(tags, str) else json.dumps(tags, sort_keys=True, ensure_ascii=False)


def scoring_features(place, descriptions):
    """explanation()의 프로필 무관 부분: (설명문 S/N 값, 그 출처, 지도 T/F 값, 설명, 출처).

    catalog_scoring.explanation()에서 description_character(descriptions)·space_nature(place) 두 호출을
    이 함수 하나로 바꾸면 된다. 설명문은 checked_at<=오늘 필터를 거쳐 들어오므로 (출처 URL, 검토일)
    묶음을, 지도 분류는 분류·태그·출처를 키에 넣어 입력이 다르면 다시 계산한다.
    """
    def compute():
        character, sources = description_character(descriptions)
        return (character, sources, *space_nature(place))
    if not place or not place.get('id'):
        return compute()
    key = (place['id'], place.get('category'), place.get('source_url'), _tags_key(place),
           tuple((d['source_url'], d['checked_at']) for d in descriptions or ()))
    character, sources, nature, note, nature_sources = memo('scoring', key, compute)
    return character, [dict(s) for s in sources], nature, note, [dict(s) for s in nature_sources]


def elements_for(place):
    """pipeline.place_editorial.resolve_elements(place)와 같은 값. 장소당 한 번만 계산한다."""
    if not place.get('id'):
        return resolve_elements(place)
    key = (place['id'], place.get('name'), place.get('lat'), place.get('lng'), place.get('category'),
           place.get('source_url'), _tags_key(place))
    found = memo('elements', key, lambda: resolve_elements(place))
    return {**found, 'elements': list(found['elements']), 'sources': [dict(s) for s in found['sources']]}


def place_elements(place):
    return set(elements_for(place)['elements'])


class NearbyIndex:
    """unique_places()의 같은 이름·접두사 비교 상대를 같은 분류·약 220m 격자의 이웃 칸으로 좁힌다.

    후보 전체를 매번 훑으면 O(n²)라 50km 요청에서 2초가 넘었다. 합치는 거리 상한(reach_m)을 덮는
    이웃 칸만 보므로 빠뜨리는 상대가 없고, 분류(group)가 다른 장소는 애초에 비교하지 않는다.
    """
    LAT_STEP, LNG_STEP = 0.002, 0.0025      # 위도 0.002°≈220m · 경도 0.0025°≈220~230m(북위 33~38°)

    def __init__(self):
        self.cells: dict[tuple, list] = {}

    def _cell(self, place):
        return (int(place['lat'] // self.LAT_STEP), int(place['lng'] // self.LNG_STEP))

    def add(self, group, name, place):
        row, col = self._cell(place)
        self.cells.setdefault((group, row, col), []).append((name, place))

    def near(self, group, place, reach_m):
        """place에서 reach_m 안에 있을 수 있는, 같은 분류로 등록된 (name, place) 항목."""
        row, col = self._cell(place)
        span = int(reach_m // 200) + 1       # 칸 한 변이 200m보다 크므로 span칸이면 reach_m을 덮는다
        for r in range(row - span, row + span + 1):
            for c in range(col - span, col + span + 1):
                yield from self.cells.get((group, r, c), ())
