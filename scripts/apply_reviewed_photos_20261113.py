"""Apply only the two reviewed photo rows to an explicitly chosen catalog copy.

Does not fetch photos, change source references, overwrite existing photo rows,
export the production snapshot, or deploy. See deploy/PHOTO_FILL_REVIEW_20261113.md.
"""
import argparse
import json
from pathlib import Path
import sqlite3

MANIFEST = Path(__file__).resolve().parents[1] / 'deploy/data/reviewed_place_photos_20261113.json'


def apply(database):
    rows = json.loads(MANIFEST.read_text(encoding='utf-8'))
    # mode=rw rejects a typo/missing database instead of creating one.
    with sqlite3.connect(Path(database).resolve().as_uri() + '?mode=rw', uri=True) as conn:
        inserted = 0
        for row in rows:
            if not conn.execute('SELECT 1 FROM places WHERE id=? AND active=1', (row['place_id'],)).fetchone():
                raise ValueError(f"Missing active reviewed place: {row['place_id']}")
            columns = list(row)
            current = conn.execute(
                f"SELECT {','.join(columns)} FROM catalog_photos WHERE place_id=? AND file_title=?",
                (row['place_id'], row['file_title']),
            ).fetchone()
            if current is not None:
                if tuple(row.values()) != current:
                    raise ValueError('Existing photo differs; manual review required, no overwrite performed')
                continue
            conn.execute(f"INSERT INTO catalog_photos ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", list(row.values()))
            inserted += 1
    return inserted


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, help='Path to an existing catalog COPY')
    args = parser.parse_args()
    print(f'Added {apply(args.database)} reviewed photo rows; no export or deployment performed.')
