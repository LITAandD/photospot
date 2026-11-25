"""Apply the approved round-two manifest only to an explicitly created local catalog copy."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from pipeline.photo_permissions import allowed
from pipeline.place_editorial import official_photos_for

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy/photo-round2/approved.json"


def stage(copy_path: Path):
    path = copy_path.resolve(strict=True)
    if not path.is_relative_to((ROOT / "artifacts").resolve()) or path.samefile(
        ROOT / "catalog/places.sqlite3"
    ):
        raise ValueError("Supply a local catalog copy in artifacts/")
    approved = json.loads(MANIFEST.read_text(encoding="utf8"))
    counts = {"added": 0, "unchanged": 0, "occupied": 0}
    with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        for photo in approved:
            branch = photo["place"]
            pid = branch["id"]
            place = conn.execute(
                "SELECT * FROM places WHERE id=? AND active=1", (pid,)
            ).fetchone()
            if not place or any(
                place[k] != branch[k]
                for k in ("name", "address", "source_url", "lat", "lng")
            ):
                raise ValueError(f"Catalog identity changed for {pid}")
            if not all(
                photo["permissions"].get(k) is True
                for k in (
                    "app_display",
                    "web_display",
                    "storage",
                    "resize",
                    "crop",
                    "color_analysis",
                    "form_analysis",
                )
            ) or not allowed(photo, modify=True):
                raise ValueError(f"Incomplete permission for {pid}")
            row = dict(
                place_id=pid,
                file_title=photo["file_id"],
                url=photo["app_url"],
                original_url=photo["original"],
                source_url=photo["source"],
                license=photo["license"],
                license_url=photo["license_url"],
                attribution=photo["credit"],
                description=photo["space_review"],
                width=photo["app_size"][0],
                height=photo["app_size"][1],
                match_method="reviewed:branch",
                match_ref=json.dumps(
                    {
                        "place": pid,
                        "source": branch["source_url"],
                        "sha256": photo["app_sha256"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                priority=10,
                fetched_at=photo["verified_at"],
            )
            old = conn.execute(
                "SELECT * FROM catalog_photos WHERE place_id=? AND file_title=?",
                (pid, row["file_title"]),
            ).fetchone()
            if old:
                if dict(old) != row:
                    raise ValueError(f"Reviewed file changed for {pid}")
                counts["unchanged"] += 1
                continue
            if (
                official_photos_for([pid]).get(pid)
                or conn.execute(
                    "SELECT 1 FROM catalog_photos WHERE place_id=? OR original_url=? OR url=?",
                    (pid, row["original_url"], row["url"]),
                ).fetchone()
            ):
                counts["occupied"] += 1
                continue
            conn.execute(
                f"INSERT INTO catalog_photos ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                tuple(row.values()),
            )
            counts["added"] += 1
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("copy", type=Path)
    print(stage(parser.parse_args().copy))
