"""Persist public OSM place facts and media references in SQLite. No profiles or sample tags.

Refresh is explicit, serial and bounded; app searches never call public Overpass.
Data attribution/license: https://www.openstreetmap.org/copyright (ODbL).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sqlite3
import urllib.parse
import urllib.request
import uuid
from .place_categories import GROUPS, CATEGORIES
from . import place_quality

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "storage" / "places.sqlite3"
REGIONS = {"seoul": (37.5796, 126.977, 18000), "busan": (35.1587, 129.1604, 18000),
           "jeju": (33.4996, 126.5312, 20000), "gangneung": (37.7519, 128.8761, 15000)}
ENDPOINT = "https://overpass-api.de/api/interpreter"
SOURCE_LABEL = "© OpenStreetMap contributors"
LICENSE_URL = "https://www.openstreetmap.org/copyright"


def db_path():
    return Path(os.environ.get("PLACE_CATALOG_DB", str(DEFAULT_DB)))


@contextmanager
def connect(path=None):
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS places (
            row_id INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, osm_type TEXT NOT NULL, osm_id INTEGER NOT NULL,
            name TEXT NOT NULL, category TEXT NOT NULL, lat REAL NOT NULL, lng REAL NOT NULL,
            address TEXT, opening_hours TEXT, source_url TEXT NOT NULL, tags TEXT NOT NULL,
            fetched_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, UNIQUE(osm_type, osm_id));
        CREATE INDEX IF NOT EXISTS place_coordinates ON places(active, lat, lng);
        CREATE TABLE IF NOT EXISTS imports (
            region TEXT PRIMARY KEY, lat REAL NOT NULL, lng REAL NOT NULL, radius_m INTEGER NOT NULL,
            fetched_at TEXT NOT NULL, source_updated_at TEXT, count INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS region_places (
            region TEXT NOT NULL, place_id TEXT NOT NULL, PRIMARY KEY(region, place_id));
    """)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def category(tags, name=None, source_url=""):
    name = name if name is not None else tags.get("name:ko", tags.get("name", ""))
    if place_quality.exclusion_reason(name, tags, source_url): return None
    correction = place_quality.corrected_category(name, tags, source_url)
    if correction: return correction
    if tags.get("historic") in place_quality.HERITAGE_SITES | {"yes", "reconstruction", "ship", "monument", "memorial"}: return "heritage"
    if tags.get("tourism") == "attraction": return "attraction"
    return None


def normalize(element, fetched_at, *, category_override=None):
    tags = element.get("tags") or {}
    name = (tags.get("name:ko") or tags.get("name") or "").strip()
    source_url = f"https://www.openstreetmap.org/{element.get('type')}/{element.get('id')}"
    kind = category_override or category(tags, name, source_url)
    if kind is not None and kind not in CATEGORIES: raise ValueError('Unknown curated category')
    if not name or not kind or place_quality.exclusion_reason(name, tags, source_url):
        return None
    point = element.get("center") or element
    try:
        lat, lng = float(point["lat"]), float(point["lon"])
        osm_id, osm_type = int(element["id"]), element["type"]
    except (KeyError, TypeError, ValueError): return None
    if not (33 <= lat <= 39 and 124 <= lng <= 132 and osm_id > 0 and osm_type in {"node", "way", "relation"}):
        return None
    address = tags.get("addr:full") or " ".join(str(tags.get(k, "")) for k in
              ("addr:city", "addr:district", "addr:suburb", "addr:street", "addr:housenumber")).strip()
    # Store only place facts; omit mapper IDs, phone numbers and unrelated tags.
    allowed = {"amenity", "tourism", "historic", "leisure", "natural", "waterway", "landuse", "building", "material", "outdoor_seating",
               "image", "wikimedia_commons", "wikidata", "wikipedia", "artwork_type", "memorial", "monument",
               "access", "disused", "abandoned", "demolished", "information", "indoor"}
    return {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://www.openstreetmap.org/{osm_type}/{osm_id}")),
            "osm_type": osm_type, "osm_id": osm_id, "name": name[:300], "category": kind, "lat": lat, "lng": lng,
            "address": address or None, "opening_hours": tags.get("opening_hours"),
            "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
            "tags": json.dumps({k: v for k, v in tags.items() if k in allowed}, ensure_ascii=False), "fetched_at": fetched_at}


def import_response(region, raw, path=None, scope="all"):
    if scope not in {"all", "spaces"}: raise ValueError("Unknown scope")
    if raw.get("remark") or not isinstance(raw.get("elements"), list):
        raise ValueError("Overpass returned an incomplete response; existing catalog retained")
    now = datetime.now(timezone.utc).isoformat()
    records = {p["id"]: p for e in raw["elements"] if (p := normalize(e, now))}
    if not records:
        raise ValueError("No valid places returned; existing catalog retained")
    lat, lng, radius = REGIONS[region]
    # Supplemental imports replace only their own membership, preserving the existing catalog.
    batch = region if scope == "all" else f"{region}:spaces"
    with connect(path) as conn:
        if scope == "all":
            conn.execute("DELETE FROM region_places WHERE region=?", (f"{region}:spaces",))
            conn.execute("DELETE FROM imports WHERE region=?", (f"{region}:spaces",))
        conn.execute("DELETE FROM region_places WHERE region=?", (batch,))
        for p in records.values():
            conn.execute("""INSERT INTO places (id, osm_type, osm_id, name, category, lat, lng, address, opening_hours, source_url, tags, fetched_at)
                VALUES (:id,:osm_type,:osm_id,:name,:category,:lat,:lng,:address,:opening_hours,:source_url,:tags,:fetched_at)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, category=excluded.category, lat=excluded.lat, lng=excluded.lng,
                address=excluded.address, opening_hours=excluded.opening_hours, tags=excluded.tags, fetched_at=excluded.fetched_at, active=1""", p)
            conn.execute("INSERT INTO region_places VALUES (?,?)", (batch, p["id"]))
        conn.execute("UPDATE places SET active=0 WHERE id NOT IN (SELECT place_id FROM region_places)")
        place_quality.reconcile(conn)
        conn.execute("""INSERT OR REPLACE INTO imports VALUES (?,?,?,?,?,?,?)""",
                     (batch, lat, lng, radius, now, raw.get("osm3s", {}).get("timestamp_osm_base"), len(records)))
    return len(records)


def query_for(region, scope="all"):
    if scope not in {"all", "spaces"}: raise ValueError("Unknown scope")
    lat, lng, radius = REGIONS[region]
    # Bounding-box lookup avoids expensive around geometry checks on coastal ways.
    dy, dx = radius / 111000, radius / (111000 * math.cos(math.radians(lat)))
    area = f"({lat-dy:.6f},{lng-dx:.6f},{lat+dy:.6f},{lng+dx:.6f})"
    selectors = ['["amenity"="cafe"]', '["tourism"~"^(museum|gallery|viewpoint|attraction|artwork|zoo|aquarium)$"]',
                 '["leisure"~"^(park|garden)$"]', '["natural"~"^(beach|water)$"]',
                 '["historic"~"^(castle|palace|monument|ruins|archaeological_site)$"]']
    spaces = ['["amenity"~"^(festival_grounds|event_ground|conference_centre|exhibition_centre|theatre|arts_centre|music_venue)$"]',
              '["leisure"="festival_grounds"]', '["landuse"="fairground"]', '["tourism"="theme_park"]',
              '["natural"~"^(peak|cave_entrance|rock|stone|cliff)$"]', '["waterway"="waterfall"]']
    selectors = spaces if scope == "spaces" else selectors + spaces
    return "[out:json][timeout:35];(" + "".join(f'nwr{selector}["name"]{area};' for selector in selectors) + ");out center tags;"


def fetch_region(region, endpoint=ENDPOINT, scope="all"):
    req = urllib.request.Request(endpoint, data=urllib.parse.urlencode({"data": query_for(region, scope)}).encode(),
          headers={"User-Agent": "PhotoSpot/1.0 local-place-catalog", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as response:
        data = response.read(15 * 1024 * 1024 + 1)
    if len(data) > 15 * 1024 * 1024:
        raise ValueError("Response exceeds the import size limit")
    return json.loads(data)


def metadata(path=None):
    with connect(path) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM imports ORDER BY region")]
        count = conn.execute("SELECT count(*) FROM places WHERE active=1").fetchone()[0]
        counts = {r["category"]: r["n"] for r in conn.execute("SELECT category,count(*) n FROM places WHERE active=1 GROUP BY category")}
    return {"provider": "openstreetmap", "label": SOURCE_LABEL, "license_url": LICENSE_URL, "count": count,
            "fetched_at": max((r["fetched_at"] for r in rows), default=None), "regions": sorted({r["region"].split(':')[0] for r in rows}),
            "group_counts": {key: sum(counts.get(c, 0) for c in categories) for key, categories in GROUPS.items()}}


def distance_m(lat, lng, row):
    a, b = math.radians(lat), math.radians(row["lat"])
    h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(row["lng"]-lng)/2)**2
    return round(6371000 * 2 * math.asin(min(1, math.sqrt(h))))


def search(lat, lng, radius_m, ids=(), path=None):
    with connect(path) as conn:
        # Korea latitude range: conservative bbox, followed by exact haversine.
        delta_lat, delta_lng = radius_m / 110000, radius_m / 85000
        rows = conn.execute("SELECT * FROM places WHERE active=1 AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                            (lat-delta_lat, lat+delta_lat, lng-delta_lng, lng+delta_lng)).fetchall()
        result = {r["id"]: {**dict(r), "distance_m": distance_m(lat, lng, r)} for r in rows
                  if distance_m(lat, lng, r) <= radius_m and not place_quality.row_exclusion(r)}
        if ids:
            for r in conn.execute(f"SELECT * FROM places WHERE id IN ({','.join('?' for _ in ids)})", list(ids)):
                if place_quality.row_exclusion(r): continue
                result.setdefault(r["id"], {**dict(r), "distance_m": distance_m(lat, lng, r)})
    from .official_cafe_photos import enrich_places
    return enrich_places(list(result.values()), path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regions", default=",".join(REGIONS))
    ap.add_argument("--endpoint", default=ENDPOINT)
    ap.add_argument("--scope", choices=["all", "spaces"], default="all", help="spaces adds new travel/event categories without replacing the previous full import")
    args = ap.parse_args()
    selected = args.regions.split(",")
    if any(r not in REGIONS for r in selected): ap.error("Unknown region")
    for region in selected:
        raw = fetch_region(region, args.endpoint, args.scope)
        print(f"{region}: {import_response(region, raw, scope=args.scope)} places imported", flush=True)
    print(json.dumps(metadata(), ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
