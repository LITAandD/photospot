"""Export only allowlisted public catalog tables into the deployable snapshot."""
from pathlib import Path
import sqlite3
from pipeline import place_catalog

PUBLIC_TABLES = {'places', 'region_places', 'imports', 'catalog_photos', 'photo_imports', 'catalog_visuals', 'cafe_popularity', 'catalog_visitors', 'catalog_annual_visitors', 'catalog_descriptions', 'catalog_instagram'}

def export(destination=None):
    destination = Path(destination or place_catalog.ROOT / 'catalog' / 'places.sqlite3')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with place_catalog.connect() as source, sqlite3.connect(destination) as target:
        target_tables = {r[0] for r in target.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if target_tables - PUBLIC_TABLES - {'sqlite_sequence'}:
            raise ValueError('Destination contains non-catalog tables')
        for name, sql in source.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"):
            if name not in PUBLIC_TABLES: continue
            target.execute('DROP TABLE IF EXISTS "' + name + '"')
            target.execute(sql)
            rows = source.execute('SELECT * FROM "' + name + '"').fetchall()
            if rows: target.executemany('INSERT INTO "' + name + '" VALUES (' + ','.join('?' for _ in rows[0]) + ')', rows)
        if not target.execute('SELECT count(*) FROM places WHERE active=1').fetchone()[0]:
            raise ValueError('Cannot publish an empty catalog')
        target.commit()
        assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    print('Public catalog exported: ' + str(destination))

if __name__ == '__main__': export()
