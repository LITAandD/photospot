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
