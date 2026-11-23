"""Promote individually reviewed KTO records onto existing places in a catalog copy."""

import argparse
from contextlib import closing
from datetime import date
from functools import lru_cache
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from .photo_permissions import TYPE1
from .catalog_visitors import today

METHOD = "reviewed:kto"
log = logging.getLogger(__name__)
SOURCES = {
    "kor": "https://www.data.go.kr/data/15101578/openapi.do",
    "gallery": "https://www.data.go.kr/data/15101914/openapi.do",
}
MANIFEST = (
    Path(__file__).resolve().parents[1] / "deploy/data/reviewed_tourism_photos.json"
)
PLACE_FIELDS = ("id", "name", "source_url", "address", "lat", "lng")


def media_url(url):
    return bool(
        re.fullmatch(
            r"https://tong\.visitkorea\.or\.kr/cms/resource/[0-9]+/[\w.-]+\.(?:jpg|jpeg|png)",
            url or "",
            re.I,
        )
    )


def public_row(record, place):
    """Derive every public column from the reviewed image & pinned branch."""
    identity, image = record["place"], record["photo"]
    if any(identity[k] != place[k] for k in PLACE_FIELDS) or not place["active"]:
        raise ValueError("Catalog branch changed")
    provider, review = record["provider"], record["review"]
    if (
        provider not in SOURCES
        or review["status"] != "approved"
        or image["license_url"] != TYPE1
    ):
        raise ValueError("Only approved Type 1 photos can enter this catalog")
    if not media_url(image["url"]) or not re.fullmatch(
        r"[a-f0-9]{64}", image["sha256"]
    ):
        raise ValueError("Missing reviewed KTO image identity")
    if (
        not re.fullmatch(r"[\w-]+", image["provider_id"])
        or not str(record["provider_id"]).isdigit()
    ):
        raise ValueError("Missing provider ID")
    if not all(
        isinstance(review[k], str) and review[k].strip()
        for k in (
            "reviewer",
            "match_evidence",
            "rights_evidence",
            "subject_review",
            "credit_basis",
        )
    ):
        raise ValueError("Incomplete photo review")
    if (
        date.fromisoformat(review["checked_at"]) > today()
        or review["subject"] != "ground_level_space"
        or review["third_party_cleared"] is not True
        or image["width"] < 100
        or image["height"] < 100
        or not image["title"].strip()
        or not image["credit"].strip()
        or not all(
            review["permissions"].get(k) is True
            for k in (
                "display",
                "store",
                "resize",
                "crop",
                "color_analysis",
                "form_analysis",
            )
        )
    ):
        raise ValueError("Unverified rights, subject or media")
    if provider == "kor":
        hit = record["provider_place"]
        if (
            str(hit["contentid"]) != str(record["provider_id"])
            or not hit.get("title")
            or not hit.get("addr1")
            or not (33 <= float(hit["mapy"]) <= 39 and 124 <= float(hit["mapx"]) <= 132)
            or image["provider_original"].replace("http:", "https:", 1) != image["url"]
        ):
            raise ValueError("Unverified provider branch or original")
    if provider == "kor" and (
        image["operation"] not in ("detailCommon2", "detailImage2")
        or image["license_code"] != "Type1"
    ):
        raise ValueError("Missing image-specific KorService2 license")
    if provider == "gallery" and (
        image["operation"] != "galleryDetailList1" or not image.get("photographer")
    ):
        raise ValueError("Missing Photo Gallery detail/credit")
    return dict(
        place_id=place["id"],
        file_title=f"KTO:{provider}:{record['provider_id']}:{image['provider_id']}",
        url=image["url"],
        original_url=image["url"],
        source_url=SOURCES[provider],
        license="공공누리 제1유형",
        license_url=TYPE1,
        attribution=image["credit"],
        description=image["title"],
        width=image["width"],
        height=image["height"],
        match_method=METHOD,
        match_ref=json.dumps(record, ensure_ascii=False, sort_keys=True),
        priority=90,
        fetched_at=review["checked_at"],
    )


def is_tourism_row(row):
    return row["match_method"] == METHOD or any(
        urlsplit(row[k]).hostname == "tong.visitkorea.or.kr"
        for k in ("url", "original_url")
    )


@lru_cache(maxsize=1)
def reviewed_records():
    try:
        rows = json.loads(MANIFEST.read_text(encoding="utf8"))
    except (OSError, ValueError) as exc:
        log.warning("KTO review manifest unavailable (%s); unverified KTO photos excluded", type(exc).__name__)
        return {}
    if not isinstance(rows, list):
        log.warning("KTO review manifest must be a list; unverified KTO photos excluded")
        return {}
    records = {}
    invalid = duplicates = 0
    for row in rows:
        try:
            pid, url = row["place"]["id"], row["photo"]["url"]
            public_row(row, {**row["place"], "active": True})
        except (TypeError, KeyError, ValueError, AttributeError, IndexError):
            invalid += 1
            continue
        if isinstance(pid, str) and isinstance(url, str):
            key = (pid, url)
            # Ambiguous duplicate reviews must not grant rights to either record.
            duplicates += key in records
            records[key] = None if key in records else row
        else:
            invalid += 1
    if invalid or duplicates:
        log.warning("KTO review manifest excluded invalid=%s duplicate=%s records", invalid, duplicates)
    return {key: row for key, row in records.items() if row is not None}


def verified(row, place):
    try:
        record = reviewed_records().get((row["place_id"], row["url"]))
        if record is None:
            return False
        expected = public_row(record, place)
        return all(row[k] == value for k, value in expected.items())
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return False


def apply(database, records, read_image):
    from PIL import Image
    from .place_catalog import DEFAULT_DB
    from .place_editorial import official_photos_for

    database = Path(database).resolve()

    if database in {
        (MANIFEST.parents[2] / "catalog/places.sqlite3").resolve(),
        Path(DEFAULT_DB).resolve(),
    }:
        raise ValueError("Pass a catalog copy")
    records = list(records)
    seen = set()
    for record in records:
        key = (record["place"]["id"], record["photo"]["url"])
        if key in seen:
            raise ValueError("Duplicate review")
        seen.add(key)
    counts = {"added": 0, "unchanged": 0, "existing_cover": 0}
    with (
        closing(sqlite3.connect(database.as_uri() + "?mode=rw", uri=True)) as conn,
        conn,
    ):
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        for record in records:
            pid = record["place"]["id"]
            place = conn.execute("SELECT * FROM places WHERE id=?", (pid,)).fetchone()
            if not place:
                raise ValueError("Unknown catalog place")
            row = public_row(record, place)
            existing = conn.execute(
                "SELECT * FROM catalog_photos WHERE place_id=? AND file_title=?",
                (pid, row["file_title"]),
            ).fetchone()
            if existing:
                if dict(existing) != row:
                    raise ValueError(
                        "Existing photo changed; review replacement separately"
                    )
                counts["unchanged"] += 1
                continue
            if conn.execute(
                "SELECT 1 FROM catalog_photos WHERE place_id=? OR original_url=?",
                (pid, row["original_url"]),
            ).fetchone() or official_photos_for([pid]).get(pid):
                counts["existing_cover"] += 1
                continue
            raw = read_image(row["url"])
            if hashlib.sha256(raw).hexdigest() != record["photo"]["sha256"]:
                raise ValueError("Image bytes changed since review")
            with Image.open(BytesIO(raw)) as image:
                if image.size != (row["width"], row["height"]):
                    raise ValueError("Image size changed")
                image.verify()
            conn.execute(
                f"INSERT INTO catalog_photos ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                tuple(row.values()),
            )
            counts["added"] += 1
    return counts


if __name__ == "__main__":
    from .catalog_visuals import read_photo

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    print(
        apply(
            args.database,
            json.loads(MANIFEST.read_text(encoding="utf8")),
            lambda url: read_photo(url, use_cache=False),
        )
    )
