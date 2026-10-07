"""Add explicitly reviewed landmarks without replacing regional catalog imports."""
from datetime import datetime, timezone
import json

from . import place_catalog as catalog
from .catalog_photos import initialize, store_photos
from .place_editorial import editorial


def sync(path=None):
    data, now = editorial(), datetime.now(timezone.utc).isoformat()
    records = []
    with catalog.connect(path) as conn:
        initialize(conn)
        for entry in data.get('landmarks', []):
            p = catalog.normalize(entry['element'], now, category_override=entry['category'])
            if p is None: raise ValueError('Invalid curated landmark')
            assert entry['classification_source'] in data['sources']
            conn.execute('''INSERT INTO places (id,osm_type,osm_id,name,category,lat,lng,address,opening_hours,source_url,tags,fetched_at)
                VALUES (:id,:osm_type,:osm_id,:name,:category,:lat,:lng,:address,:opening_hours,:source_url,:tags,:fetched_at)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,category=excluded.category,lat=excluded.lat,lng=excluded.lng,
                tags=excluded.tags,fetched_at=excluded.fetched_at,active=1''', p)
            region = entry['region'] + ':curated'
            conn.execute('INSERT OR IGNORE INTO region_places VALUES (?,?)', (region,p['id']))
            lat,lng,radius = catalog.REGIONS[entry['region']]
            count = conn.execute('SELECT count(*) FROM region_places WHERE region=?', (region,)).fetchone()[0]
            conn.execute('INSERT OR REPLACE INTO imports VALUES (?,?,?,?,?,?,?)', (region,lat,lng,radius,now,None,count))
            records.append(p)
        # Reuse already verified file metadata. A fresh catalog can obtain these via --link.
        copies = []
        ids = {p['id'] for p in records}
        for entry in data.get('commons_photos', []):
            if entry['place_id'] not in ids: continue
            for title in entry['files']:
                row = conn.execute('SELECT * FROM catalog_photos WHERE file_title=? LIMIT 1', (title,)).fetchone()
                if row: copies.append({**dict(row),'place_id':entry['place_id'],'match_method':'curated:commons','match_ref':title,'priority':5})
    store_photos(copies, path)
    return {'landmarks': len(records), 'photo_links': len(copies)}


if __name__ == '__main__':
    print(json.dumps(sync()))
