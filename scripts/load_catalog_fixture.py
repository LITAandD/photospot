"""CI-only, network-free place import. Never overwrites the user's live catalog."""
import json
import os
from pathlib import Path
from pipeline.place_catalog import DEFAULT_DB, ROOT, import_response
from pipeline.catalog_photos import store_photos


def main():
    target = os.environ.get("PLACE_CATALOG_DB")
    if not target or Path(target).resolve() == DEFAULT_DB.resolve():
        raise SystemExit("Set PLACE_CATALOG_DB to a separate CI database, not storage/places.sqlite3")
    raw = json.loads((ROOT / "tests/fixtures/osm_catalog.json").read_text(encoding="utf-8"))
    print("CI records:", import_response("seoul", raw, target))
    photos = json.loads((ROOT / 'tests/fixtures/commons_photos.json').read_text(encoding='utf-8'))['records']
    store_photos(photos, target)
    from pipeline.catalog_visuals import store
    for photo in photos:
        store(photo['place_id'], photo, {'color_temp':'cool','brightness':'bright_soft','saturation':'muted'},
              'CI test fixture attributes; not production observations', target)
    print('CI photo records:', len(photos))


if __name__ == "__main__": main()
