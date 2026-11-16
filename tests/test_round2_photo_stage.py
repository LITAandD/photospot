import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from scripts import stage_round2_photos as review


@pytest.fixture
def catalog_copy(tmp_path, monkeypatch):
    source = review.ROOT / "catalog/places.sqlite3"
    (tmp_path / "catalog").mkdir()
    protected = tmp_path / "catalog/places.sqlite3"
    shutil.copyfile(source, protected)
    (tmp_path / "artifacts").mkdir()
    target = tmp_path / "artifacts/review.sqlite3"
    shutil.copyfile(source, target)
    # Keep the empty-target scenario reproducible if these photos are later approved.
    targets = json.loads(review.MANIFEST.read_text(encoding="utf8"))
    with sqlite3.connect(target) as conn:
        conn.executemany(
            "DELETE FROM catalog_photos WHERE place_id=?",
            [(p["place"]["id"],) for p in targets],
        )
    monkeypatch.setattr(review, "ROOT", tmp_path)
    return target


def test_stage_is_idempotent_and_preserves_all_prior_rows(catalog_copy):
    def existing():
        with sqlite3.connect(catalog_copy) as conn:
            return set(conn.execute("SELECT * FROM catalog_photos"))

    before = existing()
    assert review.stage(catalog_copy) == {"added": 9, "occupied": 0, "unchanged": 0}
    after = existing()
    assert before <= after
    assert len(after - before) == 9
    assert review.stage(catalog_copy) == {"added": 0, "occupied": 0, "unchanged": 9}
    assert existing() == after


def test_occupied_place_and_protected_catalog(catalog_copy):
    first = json.loads(review.MANIFEST.read_text(encoding="utf8"))[0]["place"]["id"]
    with sqlite3.connect(catalog_copy) as conn:
        original_row = conn.execute("SELECT * FROM catalog_photos LIMIT 1").fetchone()
        columns = [r[1] for r in conn.execute("PRAGMA table_info(catalog_photos)")]
        row = dict(zip(columns, original_row))
        row["place_id"] = first
        conn.execute(
            f"INSERT INTO catalog_photos VALUES ({','.join('?' for _ in columns)})",
            tuple(row.values()),
        )
    assert review.stage(catalog_copy) == {"added": 8, "occupied": 1, "unchanged": 0}
    with sqlite3.connect(catalog_copy) as conn:
        assert conn.execute(
            "SELECT * FROM catalog_photos WHERE place_id=?", (first,)
        ).fetchall() == [tuple(row.values())]
    with pytest.raises(ValueError, match="local catalog copy"):
        review.stage(review.ROOT / "catalog/places.sqlite3")


@pytest.mark.parametrize("issue", ["site", "rights"])
def test_later_failure_rolls_back_earlier_places(catalog_copy, monkeypatch, issue):
    data = json.loads(review.MANIFEST.read_text(encoding="utf8"))
    if issue == "site":
        data[-1]["place"]["lat"] += 0.01
    else:
        data[-1]["permissions"]["crop"] = False
    broken = Path(catalog_copy).with_suffix(".json")
    broken.write_text(json.dumps(data), encoding="utf8")
    monkeypatch.setattr(review, "MANIFEST", broken)
    with pytest.raises(ValueError):
        review.stage(catalog_copy)
    with sqlite3.connect(catalog_copy) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM catalog_photos WHERE place_id=?",
                (data[0]["place"]["id"],),
            ).fetchone()[0]
            == 0
        )
