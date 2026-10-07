# Public place snapshot for CI

`osm_catalog.json` is a small subset of the real Seoul catalog fetched on 2026-10-06 via Overpass. It is used only for deterministic CI UI tests, never as an application fallback.

© OpenStreetMap contributors. Data is available under the [Open Database License](https://www.openstreetmap.org/copyright). Object IDs link to the original OpenStreetMap records; coordinates for ways/relations are their Overpass bounding-box centres. Only place facts are included, not mapper identities or personal contact details.

`commons_photos.json` contains real Commons metadata for the linked Seodaemun Prison History Hall images. Each record retains its author, license URL, original file page, and the OSM/Wikidata association. No image pixels are bundled. `photo_smoke.py` verifies real remote images locally; CI's explicit `--offline-images` option substitutes a test raster response in the test browser only. That response is never stored in the place catalog or used as an app fallback.
