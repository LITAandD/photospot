# Representative photo backfill review, 2026-11-13

## Scope and verified baseline
- Active places: 10,022. Public API reusable photos available: 198. Missing: **9,824**, not 9,842.
- Production SQLite snapshot and hosting are unchanged. No API keys, payment, database credentials, main push, merge or deployment used.
- Missing category counts: cafe 4,389; park 2,105; cultural venue 1,005; scenic 853; museum 355; waterfront 274; gallery 230; attraction 216; heritage 160; viewpoint 157; theme park 61; event venue 19.

## Safe staged additions
The separate `storage/photo-fill-reviewed.sqlite3` contains only two additive, visually reviewed photos beyond the production snapshot. `artifacts/reviewed_additions.json` contains complete provenance rows.
1. 살곶이다리（전곡교）: Cultural Heritage Administration photograph, exact Wikidata P18 link, KOGL Type 1. Bridge subject verified visually.
2. 허준박물관: KTO Jeon Hyeongjun photograph, exact Wikidata P18 link, KOGL Type 1. Building entrance/sign verified visually; official Gangseo page confirms the same 2005 building/address. Photo was taken in 2009, not 2026.
Public API result on reviewed copy: 200 places with photos, 9,822 missing. These are **not live**.

## Pipeline fix, not a blanket permission grant
`pipeline/catalog_photos.py` now recognizes only the exact individual-file KOGL Type 1 label plus `https://www.kogl.or.kr/info/licenseType1.do` (HTTP is canonicalized). Attribution and file source remain mandatory. Types 2/3/4, unknown labels, lookalike hosts remain rejected.
Five regression cases added. Related photo tests: **38 passed**, 2 dependency deprecation warnings.
Official brand images remain hidden; no owner-permission switch enabled. No name-only photo searching or guessed licenses.

## Rejected/held candidates
- 기장향교: elevated/bird-view overview, held under existing preference for ground-level place views.
- 가회민화박물관: historical 2011 exterior; current official directions specify a basement at 북촌로 52. Not approved as current representative image.
- 초전섬유퀼트박물관: exhibition-object-centered interior, current display verification pending.
- 허준박물관 02/03: extra gallery photos not needed for this representative-only patch; not staged.
- Additional refreshed OSM reference to 보신각 found. Original image visually matches the pavilion and carries CC BY-SA 3.0, but the app-selected 960px thumbnail returned HTTP 403; held until thumbnail serving is fixed/verified, not counted as ready.
Do not deploy the exploratory `storage/photo-fill-work.sqlite3`: it intentionally contains unreviewed investigation candidates. Use only the reviewed copy/manifest.

## Coverage limitation / next work
Refreshing existing OSM references across Seoul, Busan, Jeju and Gangneung completed. Existing Commons/Wikidata references do not cover most missing places; category albums contain events, people, aerial photos and historical views and cannot be bulk-approved.
TourAPI requires an unavailable service key. Existing old TourAPI integration writes PostGIS scenes rather than current SQLite places, so an adapter and identity matching are needed. Photo-specific reuse conditions must be retained. Do not treat the dataset's general license as permission for every image. Only Type 1 approved here; Type 3 requires separate no-modification handling and is not enabled.
To complete thousands safely: authorized TourAPI access plus adapter and per-file license/provenance validation; owner-authorized place uploads; explicit missing-photo state where no valid photo exists. Never substitute generic scenery or another branch's image.

## Verification sources
- https://www.kogl.or.kr/info/licenseType1.do
- https://commons.wikimedia.org/wiki/File:Heojun_Museum_01.jpg
- https://commons.wikimedia.org/wiki/File:서울_살곶이_다리.jpg
- https://www.gangseo.seoul.kr/munhwa/mh040100
- https://www.gahoemuseum.org/오시는길/

## Reproduce the reviewed copy from this PR (no live deployment)
The binary production snapshot is deliberately not changed by this draft. The two exact rows are versioned as `deploy/data/reviewed_place_photos_20261113.json`.

```sh
cp catalog/places.sqlite3 /tmp/photospot-reviewed.sqlite3
python -m scripts.apply_reviewed_photos_20261113 --database /tmp/photospot-reviewed.sqlite3
```
The command adds only missing identical-key rows, rejects conflicts, and is idempotent. Inspect the resulting copy, then follow the existing snapshot export and deployment process after operator review. Do not run an unrestricted category import as a substitute for this reviewed manifest.
