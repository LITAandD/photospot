"""Separate visitable spaces from exhibits and map fixtures.

OSM's artwork/monument tags describe objects as well as buildings. They are
not sufficient evidence for recommending an independent destination:
https://wiki.openstreetmap.org/wiki/Tag:tourism%3Dartwork
https://wiki.openstreetmap.org/wiki/Tag:historic%3Dmonument
Keep raw facts; ambiguous records wait for review instead of becoming places.
"""
from __future__ import annotations

import json
import re
from . import dining_curation
from .dining_curation import category_override, excluded_starbucks

RULE_VERSION = "2026-10-08.1"

# Reviewed 2026-10-07: the public Place page explicitly says that this is now
# rental-only, with no ordinary cafe opening hours. Keep its facts/photos,
# but do not offer it as a walk-in destination or resurrect it on OSM refresh.
REVIEWED_UNAVAILABLE = {
    "https://www.openstreetmap.org/node/7237249685": (
        "서울리즘", "rental_only_no_regular_visits", "https://pcmap.place.naver.com/place/1932681801"),
}

# ID + name prevents an exception being transferred to an unrelated renamed POI.
# Sources establish these entries as spaces despite generic OSM object tags.
REVIEWED_SPACES = {
    "https://www.openstreetmap.org/node/10129601125": (
        "페로탕", "gallery", "https://www.perrotin.com/en/locations"),
    "https://www.openstreetmap.org/node/10129601219": (
        "Thaddaeus Ropac", "gallery", "https://ropac.net/contact/"),
    "https://www.openstreetmap.org/node/10014434017": (
        "PACE", "gallery", "https://www.pacegallery.com/galleries/seoul/"),
    "https://www.openstreetmap.org/node/10129600819": (
        "Tang Contemporary Art", "gallery", "https://www.tangcontemporary.com/contact-cn"),
    "https://www.openstreetmap.org/way/1209070324": (
        "현충관", "heritage", "https://www.mpva.go.kr/jjnc/contents.do?key=1683"),
    "https://www.openstreetmap.org/node/13833498701": (
        "광통교", "heritage", "https://www.sisul.or.kr/open_content/cheonggye/enjoy/guide.jsp?bridge=gwangtong"),
}

OBJECT_NAME = re.compile(
    r"(?:혼천의|앙부일구|측우기|자격루|해시계|모래시계|천상열차분야지도|"
    r"동상|흉상|석상|조각상|소녀상|성모상|마리아상|사자상|천마상|송골매상|지사상|"
    r"조형물|조각|기념비|기념물|기념탑|추념탑|추모비|위령탑|현양탑|찬송비|의거비|"
    r"표지석|비석|머리돌|하마비|명언비|건축비|장서비|태실비|유래비|비문|"
    r"동종|장승|타임캡슐|운동기구|시계탑|기념식수|벽화|표지목|記念碑)\s*\d*$|"
    r"(?:^|\s)(?:statue|sculpture|plaque|bust|memorial stone|map tile)(?:\s|$)|"
    r"(?:스탬프|stamp\s+(?:desk|deck|box)|PostBox)", re.IGNORECASE)
EXACT_OBJECTS = {"종", "Bell", "Mirror", "항공기", "문인석", "무인석", "석마", "석양", "석호",
                 "망주석", "혼유석", "장명등", "호상", "형제의 상", "하마비와 탕병피각"}
NON_PLACE_AMENITIES = {"post_box", "bench", "clock", "vending_machine", "parking"}
OBJECT_HISTORIC = {"aircraft", "locomotive", "tank", "vehicle", "boundary_stone", "milestone"}
HERITAGE_SITES = {"castle", "palace", "ruins", "archaeological_site", "city_gate", "citywalls",
                  "building", "manor", "heritage_building", "monastery", "fort", "church", "tomb"}


def space_category(tags):
    """Explicit space tags take priority over incidental historic/artwork tags."""
    if tags.get("amenity") in {"festival_grounds", "event_ground"} or tags.get("leisure") == "festival_grounds" or tags.get("landuse") == "fairground": return "festival_site"
    if tags.get("amenity") in {"conference_centre", "exhibition_centre"}: return "event_venue"
    if tags.get("amenity") in {"theatre", "arts_centre", "music_venue"}: return "cultural_venue"
    if tags.get("amenity") == "cafe": return "cafe"
    if tags.get("shop") == "bakery": return "bakery"
    if tags.get("amenity") == "restaurant": return "restaurant"
    if tags.get("tourism") == "theme_park": return "theme_park"
    if tags.get("natural") in {"peak", "cave_entrance", "rock", "stone", "cliff"} or tags.get("waterway") == "waterfall": return "scenic"
    if tags.get("tourism") in {"museum", "gallery"}: return tags["tourism"]
    if tags.get("natural") in {"beach", "water"}: return "waterfront"
    if tags.get("leisure") in {"park", "garden"} or tags.get("landuse") == "forest": return "park"
    if tags.get("tourism") == "viewpoint": return "viewpoint"
    if tags.get("tourism") in {"zoo", "aquarium"}: return "attraction"
    return None


def clean_name(name):
    # Museum building numbers and exhibit '(replica)' suffixes do not alter type.
    return re.sub(r"\s*\([^()]*\)\s*$", "", name).strip().rstrip(".")


def corrected_category(name, tags, source_url=""):
    curated = category_override(name, source_url)
    if curated: return curated
    explicit = space_category(tags)
    if explicit: return explicit
    reviewed = REVIEWED_SPACES.get(source_url)
    if reviewed and reviewed[0] == name: return reviewed[1]
    # Interpret facility names only when the source has conflicting generic tags.
    if tags.get("tourism") != "artwork" and tags.get("historic") not in {"monument", "memorial", "yes"}:
        return None
    label = clean_name(name)
    if re.search(r"(?:박물관|미술관|기념관|전시관|보존관)$|\bmuseum(?:\s+of\s+.+)?$", label, re.I): return "museum"
    if re.search(r"(?:갤러리|화랑)$|\b(?:gallery|galeria de arte|artcube)$", label, re.I): return "gallery"
    if tags.get("tourism") != "artwork" and label.endswith("공원"): return "park"
    if label.endswith(("벽화거리", "벽화마을")): return "attraction"
    return None


def exclusion_reason(name, tags, source_url=""):
    if excluded_starbucks(name, tags, source_url): return "starbucks_not_architecture_selection"
    reviewed = REVIEWED_UNAVAILABLE.get(source_url)
    if reviewed and reviewed[0] == name: return reviewed[1]
    if tags.get("access") in {"private", "no"} or "미개방" in name:
        return "not_publicly_accessible"
    if any(tags.get(k) in {"yes", "true"} for k in ("disused", "abandoned", "demolished")):
        return "closed_or_removed"
    # A museum containing statues, or a cafe named after an object, is a space.
    if corrected_category(name, tags, source_url): return None
    if tags.get("amenity") in NON_PLACE_AMENITIES or tags.get("information") in {"board", "map"}:
        return "map_fixture"
    label = clean_name(name)
    if label in EXACT_OBJECTS or OBJECT_NAME.search(label): return "individual_object"
    historic = set(filter(None, tags.get("historic", "").split(";")))
    if historic & OBJECT_HISTORIC: return "individual_object"
    if tags.get("tourism") == "artwork": return "artwork_without_venue"
    if historic and (re.search(r"(?:아파트|독신자숙소|교수님댁)$", label) or label == "부영벽산파라빌"):
        return "residence_mistagged_as_heritage"
    if historic & {"monument", "memorial"}:
        # Gates, pavilions, ruins and memorial halls remain destinations.
        if tags.get("building") not in {None, "no"}: return None
        if re.search(r"(?:문|가옥|터|유배지|교회|선교관|광장|센터|사이언스홀)$", label): return None
        return "monument_needs_place_review"
    if historic and not historic & (HERITAGE_SITES | {"yes", "reconstruction", "ship"}):
        return "unsupported_historic_type"
    return None


def row_exclusion(row):
    return exclusion_reason(row["name"], json.loads(row["tags"]), row["source_url"])


# --- 추천 목록 전용 제외 (카탈로그 행은 유지: 상세·북마크 조회 가능) -----------------
# 2026-11-09 카탈로그(활성 10,022곳) 기준 매칭 수: 어린이공원 411 · 근린공원 208 · 소공원 41 ·
# 놀이터 77 · 쉼터 71 · 체육/운동 84 · 화장실 2 · 주차장 4 · 법인명 48 · 아파트 단지 31.
# 사진이 있는 곳(문래근린공원·손기정체육공원 등)은 제외하지 않는다.
PLAYGROUND_NAME = re.compile(
    r"어린이\s*공원|소공원|근린\s*공원|놀이터|쉼터|(?:^|\d)호\s*공원|마을\s*마당$|쌈지마당$|어울마당$|^마당$|^공원$|^(?:소|근린|어린이)?공원\s*\d*$")
SPORTS_NAME = re.compile(
    r"체육|운동장|운동시설|운동기구|테니스|배드민턴|게이트볼|축구장|야구장|농구장|풋살|족구|인라인|볼링|헬스장|수영장|골프")
FIXTURE_NAME = re.compile(r"화장실|주차(?:장|공원|타워|빌딩)?(?:$|\W)|유수지|배수지|정류장|지하도|육교|변전소|정화조|쓰레기")
CORPORATE_NAME = re.compile(r"\(주\)|㈜|주식회사|\(사\)|\(재\)|사단법인|재단법인|\(유\)|유한회사")
APARTMENT_NAME = re.compile(r"아파트|APT\b|\d+\s*단지|빌라|오피스텔|주공\s*\d+|주공아파트|휴먼시아|푸르지오|래미안|자이\b|e편한세상|아이파크|더샵|힐스테이트", re.I)
VENUE_WORD = re.compile(r"수목원|정원|갤러리|화랑|미술관|박물관|전시관|아트홀|극장|시네마|공연장|호텔|홀$|카페|베이커리")
DINING = {"cafe", "bakery", "restaurant"}
# 브랜드 매장은 기본 추천에서 제외하고, dining_curation 허용목록(스타벅스 특수 매장 등)만 남긴다.
# brand:wikidata는 현재 카탈로그에 없지만 수집 규칙에 포함돼 있어 확인된 ID(스타벅스)만 둔다.
CHAIN_WIKIDATA = {"Q37158"}
CHAIN_NAME = re.compile(
    r"이디야|ediya|투썸|twosome|컴포즈|compose|빽다방|paik'?s|공차|gong\s*cha|할리스|hollys|커피빈|coffee\s*bean|탐앤탐스|tom\s*n\s*toms|"
    r"메가\s*(?:mgc\s*)?커피|mega\s*(?:mgc\s*)?coffee|엔제리너스|앤젤인어스|angel-?in-?us|파스쿠찌|pascucci|카페\s*베네|caff[eè]\s*bene|"
    r"더\s*벤티|the\s*venti|매머드|mammoth|설빙|sulbing|폴\s*바셋|paul\s*bassett|던킨|dunkin|파리\s*바게뜨|paris\s*baguette|뚜레쥬르|"
    r"tous\s*les\s*jours|배스킨|baskin|요거프레소|드롭탑|droptop|커피나무|셀렉토|토프레소|달\.?콤|dal\.?komm|커피스미스|coffeesmith|"
    r"스타\s*벅스|star\s*bucks|텐퍼센트|10%\s*coffee|하삼동|감성커피|더\s*리터|the\s*liter|쥬씨|juicy|요아정|커피베이|coffee\s*bay|"
    r"커피에반하다|만랩|이삭토스트|크리스피|krispy|블루샥|blue\s*shark|카페\s*봄봄|bombom|나뚜루|natuur|스무디킹|smoothie\s*king|쟈뎅|jardin|"
    r"맥도날드|mcdonald|롯데리아|lotteria|버거킹|burger\s*king|서브웨이|subway|파스텔커피|카페베즐리|아티제|artisee|카페\s*띠아모|"
    r"빈스빈스|coffeenie|커피니|가배도|카페\s*마마스|투썸플레이스", re.I)


def is_franchise(name, tags):
    if tags.get("brand:wikidata") in CHAIN_WIKIDATA: return True
    text = " ".join([name, *(str(tags.get(k, "")) for k in ("brand", "brand:en", "name:en"))])
    return bool(CHAIN_NAME.search(text))


def low_value_reason(name, tags, category):
    """OSM 노드 중 포토스팟으로 볼 근거가 없는 동네 시설 이름 패턴. 사진·큐레이션이 있으면 호출측에서 무시한다."""
    label = clean_name(name) or name
    if category in DINING: return None  # 상호는 자유 표기('커피내리는 버스정류장')라 이름 규칙을 적용하지 않는다.
    if tags.get("amenity") in NON_PLACE_AMENITIES or tags.get("amenity") in {"toilets", "parking_space"}: return "fixture"
    if FIXTURE_NAME.search(label): return "fixture"
    if category != "museum" and (SPORTS_NAME.search(label) or tags.get("leisure") in {"pitch", "sports_centre", "track", "fitness_station", "playground", "dog_park"}):
        return "sports_facility"
    if category in {"park", "waterfront", "viewpoint", "attraction", "scenic"} and PLAYGROUND_NAME.search(label):
        return "neighbourhood_park"
    if category in {"park", "waterfront"} and APARTMENT_NAME.search(label):
        return "apartment_complex"
    # 법인명만 남은 등록(삼성물산(주)·(주)제일기획 등). 수목원·갤러리·극장처럼 시설 종류가 보이면 유지.
    if CORPORATE_NAME.search(name) and not VENUE_WORD.search(label):  # clean_name strips a trailing '(주)'
        return "corporate_name"
    return None


def recommendation_exclusion(place, *, photographed=False, curated=False):
    """추천 목록에서 숨길 이유. 사진·큐레이션 근거가 있는 장소는 이름 패턴만으로 제외하지 않는다."""
    tags = place.get("tags") or {}
    if isinstance(tags, str): tags = json.loads(tags)
    name, category = place["name"], place.get("category")
    # dining_curation.json에 있는 지점(큐레이션 매장·starbucks_keep)은 허용목록이다.
    allowlisted = curated or place.get("source_url") in dining_curation.entries()
    if category in DINING and is_franchise(name, tags) and not allowlisted:
        return "franchise_chain"
    if photographed or curated:
        return None
    return low_value_reason(name, tags, category)


def reconcile(conn, *, apply=True):
    """Deactivate invalid entries without deleting facts, photos or memberships.

    Also used after imports so overlapping region memberships cannot resurrect
    excluded records. Never reactivates previously closed/removed places.
    """
    changes = []
    for row in conn.execute("SELECT * FROM places WHERE active=1").fetchall():
        tags = json.loads(row["tags"])
        reason = exclusion_reason(row["name"], tags, row["source_url"])
        correction = corrected_category(row["name"], tags, row["source_url"])
        if reason:
            if apply: conn.execute("UPDATE places SET active=0 WHERE id=?", (row["id"],))
        elif correction and correction != row["category"]:
            if apply: conn.execute("UPDATE places SET category=? WHERE id=?", (correction, row["id"]))
        else:
            continue
        changes.append({"id": row["id"], "name": row["name"], "source_url": row["source_url"],
                        "previous_category": row["category"], "category": correction or row["category"],
                        "action": "exclude" if reason else "reclassify", "reason": reason or "venue_category",
                        "tags": tags,
                        "review_source": (REVIEWED_UNAVAILABLE.get(row["source_url"]) or REVIEWED_SPACES.get(row["source_url"], (None, None, None)))[2]})
    return changes
