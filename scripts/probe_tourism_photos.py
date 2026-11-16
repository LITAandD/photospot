"""Compare the same existing catalog places using the two KTO services, without DB writes.

Private metadata only. Run with TOURAPI_KEY in the collector process environment.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import unquote

from pipeline.official_cafe_photos import road_address
from pipeline.place_catalog import distance_m
from pipeline.tourapi import (
    BASE_URL,
    TourApiError,
    _get,
    build_url,
    decode_response,
    items_of,
)
from pipeline.tourism_codes import filters, matches_filters

SAMPLE = (
    Path(__file__).resolve().parents[1] / "deploy/data/tourism_photo_sample_24.json"
)
GALLERY = "https://apis.data.go.kr/B551011/PhotoGalleryService1"
PLACE_KEYS = (
    "contentid",
    "title",
    "addr1",
    "addr2",
    "mapx",
    "mapy",
    "contenttypeid",
    "lDongRegnCd",
    "lDongSignguCd",
    "lclsSystm1",
    "lclsSystm2",
    "lclsSystm3",
    "firstimage",
    "firstimage2",
    "cpyrhtDivCd",
)
IMAGE_KEYS = (
    "contentid",
    "originimgurl",
    "smallimageurl",
    "serialnum",
    "imgname",
    "cpyrhtDivCd",
)
GALLERY_KEYS = (
    "galContentId",
    "galTitle",
    "galPhotographyLocation",
    "galPhotographyMonth",
    "galPhotographer",
    "galWebImageUrl",
    "galSearchKeyword",
    "galContentTypeId",
)


def pick(row, fields):
    return {key: row[key] for key in fields if key in row}


def normalized(value):
    return "".join(c for c in (value or "").casefold() if c.isalnum())


def nearby(place, hit):
    try:
        return round(distance_m(float(hit["mapy"]), float(hit["mapx"]), place), 1)
    except (ValueError, KeyError, TypeError):
        return None


class Client:
    def __init__(self, key, service, budget):
        self.key = unquote(key)
        self.service = service
        self.budget = budget
        self.calls = Counter()

    def page(self, op, page=1, size=50, **params):
        if self.calls.total() >= self.budget:
            raise ValueError("budget")
        self.calls[op] += 1
        url = build_url(op, self.key, numOfRows=size, pageNo=page, **params)
        if self.service == "gallery":
            url = url.replace(BASE_URL + "/", GALLERY + "/", 1)
        time.sleep(0.18)
        data = decode_response(_get(url), op)
        items = items_of(data)
        return items, int(
            data.get("response", {}).get("body", {}).get("totalCount") or len(items)
        )


def tourism(place, client):
    params = filters(
        region=place.get("legal_region"),
        district=place.get("legal_district"),
        cafe=place.get("sample_group") == "cafe",
    )
    hits, total = client.page(
        "searchKeyword2", keyword=place["name"], arrange="A", **params
    )
    rows = []
    for hit in hits:
        distance = nearby(place, hit)
        cid = str(hit.get("contentid") or "")
        row = {**pick(hit, PLACE_KEYS), "distance_m": distance, "images": []}
        catalog_addr, provider_addr = (
            road_address(place.get("address")),
            road_address(hit.get("addr1")),
        )
        row["name_matches"] = normalized(hit.get("title")) == normalized(place["name"])
        row["address_matches"] = (
            (catalog_addr == provider_addr) if catalog_addr and provider_addr else None
        )
        rows.append(row)
        if not matches_filters(hit, params) or row["address_matches"] is False:
            row["detail_error"] = "classification_or_address_conflict"
            continue
        # Name-only and nearby/adjacent hits remain in the review file, never accepted.
        if distance is None or distance > 1500 or not cid.isdigit():
            continue
        common, _ = client.page("detailCommon2", contentId=cid, size=1)
        if len(common) != 1 or str(common[0].get("contentid")) != cid:
            row["detail_error"] = "identity_mismatch"
            continue
        row["common"] = pick(common[0], PLACE_KEYS)
        row["common_fields"] = sorted(common[0])
        images, count = client.page("detailImage2", contentId=cid, imageYN="Y")
        row.update(
            images=[
                pick(i, IMAGE_KEYS) for i in images if str(i.get("contentid")) == cid
            ],
            mismatched_image_rows=sum(str(i.get("contentid")) != cid for i in images),
            images_total=count,
            image_fields=sorted({k for image in images for k in image}),
        )
    return {"hits": rows, "total": total, "truncated": total > len(hits)}


def gallery(place, client):
    groups, total = client.page(
        "gallerySearchList1", keyword=place["name"], arrange="B"
    )
    rows = []
    for title in dict.fromkeys(g.get("galTitle") for g in groups if g.get("galTitle")):
        # Titles are group keys, not place IDs. Retain other groups for review, without fanning out.
        row = {"title": title, "images": []}
        rows.append(row)
        if normalized(place["name"]) not in normalized(title):
            continue
        images, count = client.page("galleryDetailList1", title=title)
        row.update(
            images=[
                pick(i, GALLERY_KEYS) for i in images if i.get("galTitle") == title
            ],
            mismatched_image_rows=sum(i.get("galTitle") != title for i in images),
            images_total=count,
            image_fields=sorted({k for image in images for k in image}),
        )
    return {"hits": rows, "total": total, "truncated": total > len(groups)}


def compare(sample, key, output, budget=240, source_filter="both"):
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "sample": len(sample),
        "sources": {},
    }
    for source, probe in [("gallery", gallery), ("kor", tourism)]:
        if source_filter not in ("both", source):
            continue
        client = Client(key, source, budget)
        batch = {"rows": [], "calls": {}, "error": None}
        result["sources"][source] = batch
        try:
            if source == "kor":
                batch["cafe_control"] = []
                for name, region, district in [
                    ("346커피스토리", 51, 150),
                    ("에오마르", 50, None),
                ]:
                    for group in ("unfiltered", "cafe", "korean_food"):
                        params = filters(
                            region=region, district=district, cafe=group == "cafe"
                        )
                        if group == "korean_food":
                            params.update(lclsSystm1="FD", lclsSystm2="FD01")
                        items, total = client.page(
                            "searchKeyword2", keyword=name, arrange="A", **params
                        )
                        batch["cafe_control"].append(
                            {
                                "name": name,
                                "group": group,
                                "filters": params,
                                "total": total,
                                "consistent": all(
                                    matches_filters(i, params) for i in items
                                ),
                                "hits": [pick(i, PLACE_KEYS) for i in items],
                            }
                        )
            for p in sample:
                batch["rows"].append({"place_id": p["id"], **probe(p, client)})
        except (TourApiError, HTTPError, OSError, ValueError) as err:
            # Raw URLs, error bodies and exception messages can contain serviceKey.
            batch["error"] = {
                "kind": type(err).__name__,
                "code": str(getattr(err, "code", ""))[:5],
            }
        batch["calls"] = dict(client.calls)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8"
        )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Private report outside version control",
    )
    p.add_argument("--source", choices=("kor", "gallery", "both"), default="both")
    p.add_argument("--sample", type=Path, default=SAMPLE)
    p.add_argument("--budget", type=int, default=240, help="HTTP attempts per service")
    args = p.parse_args()
    if not 1 <= args.budget <= 800:
        p.error("Set a call budget from 1 to 800 within the remaining quota")
    key = os.environ.get("TOURAPI_KEY")
    if not key:
        p.error("Set TOURAPI_KEY in the server process")
    data = json.loads(args.sample.read_text(encoding="utf8"))
    places = data["sample"] if isinstance(data, dict) else data
    if not 1 <= len(places) <= 200 or len(set(p["id"] for p in places)) != len(places):
        p.error("Expected 1–200 unique catalog places")
    r = compare(places, key, args.output, args.budget, args.source)
    print(
        {s: (len(b["rows"]), b["calls"], b["error"]) for s, b in r["sources"].items()}
    )
    if any(batch["error"] for batch in r["sources"].values()):
        raise SystemExit(2)
