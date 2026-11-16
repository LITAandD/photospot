import copy
import json
from pathlib import Path
import shutil
import sqlite3

import pytest
from fastapi.testclient import TestClient

from api import photo_likes
from api.catalog_media import cover_thumbnail
from api.preview import app
from pipeline import catalog_visuals, tourism_photos
from pipeline.photo_permissions import TYPE1, TYPE3, allowed
from pipeline.tourism_codes import CAFE, filters, matches_filters
from scripts.export_catalog import export
from scripts.probe_tourism_photos import gallery, tourism


@pytest.mark.parametrize(
    "license_url",
    [
        TYPE3,
        "",
        "https://creativecommons.org/licenses/by-nd/4.0/",
        "https://creativecommons.org/licenses/by-nc/4.0/",
    ],
)
def test_existing_photos_block_analysis_and_stale_results(
    license_url, tmp_path, monkeypatch
):
    db = tmp_path / "test.sqlite3"
    photo = {
        "url": "https://upload.wikimedia.org/a.jpg",
        "original_url": "https://upload.wikimedia.org/full.jpg",
        "source_url": "https://commons.wikimedia.org/wiki/File:A",
        "license_url": TYPE1,
    }
    catalog_visuals.store("p", photo, {"color_temp": "warm"}, "fixture", db)
    blocked = {**photo, "license_url": license_url}
    assert not allowed(blocked, modify=True)
    assert allowed(blocked) == (
        license_url in {TYPE3, "https://creativecommons.org/licenses/by-nd/4.0/"}
    )
    assert cover_thumbnail(blocked) == (
        photo["url"] if "/by-nd/" in license_url else photo["original_url"]
    )
    assert not catalog_visuals.evidence_for(["p"], db, selected_photos={"p": [blocked]})
    with pytest.raises(ValueError):
        catalog_visuals.store("p", blocked, {"color_temp": "cool"}, "fixture", db)
    monkeypatch.setattr(
        catalog_visuals, "read_photo", lambda url: pytest.fail("read blocked photo")
    )
    assert not photo_likes.analyze_photo("p", blocked)
    photo_likes.ensure_evidence("p", blocked)
    assert not photo_likes._reviewed({"p": blocked}, [{"place_id": "p"}])


def test_unreviewed_cdn_image_is_rejected_before_network():
    with pytest.raises(ValueError, match="reviewed manifest"):
        catalog_visuals.read_photo("https://tong.visitkorea.or.kr/cms/resource/0/unknown.jpg")


def test_new_codes_and_matching_without_images():
    class Client:
        def page(self, op, **params):
            if op == "searchKeyword2":
                assert params["arrange"] == "A"
            if op == "detailImage2":
                return [], 0
            return [
                {
                    "contentid": "123",
                    "title": "카페 지점",
                    "mapy": "37.5",
                    "mapx": "127.0",
                }
            ], 1

    assert filters(region=51, district=150, cafe=True) == {
        **CAFE,
        "lDongRegnCd": "51",
        "lDongSignguCd": "150",
    }
    assert not matches_filters({**CAFE, "lclsSystm3": "FD050200"}, CAFE)
    hit = tourism({"name": "카페 지점", "lat": 37.5, "lng": 127.0}, Client())["hits"][0]
    assert hit["common"]["contentid"] == "123" and hit["images"] == []


def test_gallery_title_groups_do_not_confirm_a_branch():
    class Client:
        def page(self, op, **params):
            if op == "gallerySearchList1":
                return [
                    {"galTitle": "다른 장소"},
                    {"galTitle": "경포대"},
                    {"galTitle": "경포대"},
                ], 3
            assert op == "galleryDetailList1" and params["title"] == "경포대"
            return [
                {"galContentId": "1", "galTitle": "경포대", "galPhotographer": "촬영자"}
            ], 1

    rows = gallery({"name": "경포대"}, Client())["hits"]
    assert len(rows) == 2 and len(rows[1]["images"]) == 1 and "approved" not in rows[1]


def test_export_and_public_preview_require_the_reviewed_record(tmp_path, monkeypatch):
    from pipeline.catalog_photos import photos_for

    source = tmp_path / "source.sqlite3"
    shutil.copyfile(
        Path(__file__).resolve().parents[1] / "catalog/places.sqlite3", source
    )
    monkeypatch.setenv("PLACE_CATALOG_DB", str(source))
    record = json.loads(tourism_photos.MANIFEST.read_text(encoding="utf8"))[0]
    pid = record["place"]["id"]
    with sqlite3.connect(source) as conn:
        conn.row_factory = sqlite3.Row
        place = conn.execute("SELECT * FROM places WHERE id=?", (pid,)).fetchone()
        public = tourism_photos.public_row(record, place)

        def insert(row):
            conn.execute(
                f"INSERT INTO catalog_photos ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                tuple(row.values()),
            )

        staged = conn.execute("SELECT * FROM catalog_photos WHERE place_id=? AND file_title=?",
                              (pid, public["file_title"])).fetchone()
        assert staged and dict(staged) == public
        insert(
            {
                **public,
                "file_title": "unreviewed",
                "url": public["url"] + "?different",
                "match_ref": "{}",
            }
        )
        insert(
            {
                **public,
                "file_title": "unknown",
                "match_method": "accidental-direct-link",
                "license_url": "",
            }
        )
    assert [p["url"] for p in photos_for([pid], source)[pid]] == [public["url"]]
    out = tmp_path / "public.sqlite3"
    export(out, manifest=False)
    with sqlite3.connect(out) as conn:
        assert conn.execute(
            "SELECT file_title FROM catalog_photos WHERE place_id=?", (pid,)
        ).fetchall() == [(public["file_title"],)]
    monkeypatch.setenv("PLACE_CATALOG_DB", str(out))
    with TestClient(app) as client:
        response = client.get(
            f"/preview/browse/{pid}",
            params={"city": "gangneung", "visit_date": "2026-11-16"},
        )
        assert response.status_code == 200
        photo = response.json()["cover_photo"]
        assert (
            photo["url"],
            photo["attribution"],
            photo["source_url"],
            photo["license_url"],
        ) == tuple(
            public[k] for k in ("url", "attribution", "source_url", "license_url")
        )
    assert (
        tourism_photos.apply(
            source, [record], lambda _: pytest.fail("duplicate fetched")
        )["unchanged"]
        == 1
    )
    changed = copy.deepcopy(record)
    changed["photo"]["credit"] = "다른 표기"
    with pytest.raises(ValueError):
        tourism_photos.apply(source, [changed], lambda _: b"")
    with sqlite3.connect(source) as conn:
        conn.execute(
            "UPDATE catalog_photos SET file_title='prior' WHERE file_title=?",
            (public["file_title"],),
        )
    assert (
        tourism_photos.apply(
            source, [record], lambda _: pytest.fail("existing cover fetched")
        )["existing_cover"]
        == 1
    )


def test_postgres_queue_and_historical_aggregation_filter_existing_licenses():
    # Execute the actual queue SQL against equivalent rows; PostgreSQL-only ::text is removed for SQLite.
    from contextlib import contextmanager
    from pipeline.db import fetch_pending_photos, load_spot_results

    conn = sqlite3.connect(":memory:")
    conn.executescript("""CREATE TABLE photos(id,spot_id,source,storage_path,license,analyzed_at,created_at,time_slot,season,labels);
        CREATE TABLE external_media(spot_id,media_id,labels);
        INSERT INTO photos VALUES ('ok','s','tourapi','1','kogl_type1',NULL,1,NULL,NULL,NULL),
        ('nd','s','tourapi','3','kogl_type3',NULL,2,NULL,NULL,NULL),
        ('unknown','s','tourapi','x',NULL,NULL,3,NULL,NULL,NULL);""")

    class Adapter:
        @contextmanager
        def cursor(self):
            yield self

        def execute(self, sql, params):
            self.result = conn.execute(
                sql.replace("::text", "").replace("%s", "?"), params
            )

        def fetchall(self):
            return self.result.fetchall()

    for force in (False, True):
        assert [x["id"] for x in fetch_pending_photos(Adapter(), "s", force)] == ["ok"]
    conn.execute(
        "UPDATE photos SET analyzed_at='before', labels='old result' WHERE id!='ok'"
    )
    assert load_spot_results(Adapter(), "s") == []


def test_commons_rollout_preserves_occupied_places_and_checks_branch(tmp_path):
    from scripts.apply_reviewed_photos_20261113 import MANIFEST, apply

    db = tmp_path / "catalog.sqlite3"
    shutil.copyfile(Path(__file__).resolve().parents[1] / "catalog/places.sqlite3", db)
    first, second = json.loads(MANIFEST.read_text(encoding="utf8"))
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE catalog_photos SET file_title='prior', url='https://example.org/prior' WHERE place_id=?",
                     (first["place_id"],))
        conn.execute("DELETE FROM catalog_photos WHERE place_id=?", (second["place_id"],))
    assert apply(db) == 1
    assert apply(db) == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT file_title, url FROM catalog_photos WHERE place_id=?", (first["place_id"],)).fetchall() == [
            ("prior", "https://example.org/prior")]
        conn.execute("UPDATE places SET tags='{}' WHERE id=?", (second["place_id"],))
    with pytest.raises(ValueError, match="Wikidata identity"):
        apply(db)
