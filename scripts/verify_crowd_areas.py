"""Audit the reviewed pilot against the official OA-21778 WGS84 ZIP (offline only).

Run as python -m scripts.verify_crowd_areas ZIP. Install pyshp and shapely in
the review environment. The command only reads the ZIP and the bundled catalog.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sqlite3
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SHA256 = 'fda69cd2ee3812103931cfd0ef1a0146336f06a23b6e1c2e4f9e0653620262ac'


def verify(archive):
    import shapefile
    from shapely.geometry import Point, shape

    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError('경계 파일이 변경됐습니다. 새 자료로 후보 전체를 다시 검토해 주세요.')
    with ZipFile(archive) as z:
        def part(ext):
            name, = [n for n in z.namelist() if n.endswith('.' + ext)]
            return z.read(name)
        assert b'GCS_WGS_1984' in part('prj')
        with shapefile.Reader(**{ext: io.BytesIO(part(ext)) for ext in ('shp', 'shx', 'dbf')}) as reader:
            zones = [(r.record['AREA_CD'], r.record['AREA_NM'], shape(r.shape.__geo_interface__))
                     for r in reader.iterShapeRecords()]
    assert len(zones) == 121
    places = json.loads((ROOT / 'api/crowd_places.json').read_text('utf-8'))
    catalog = sqlite3.connect((ROOT / 'catalog/places.sqlite3').as_uri() + '?mode=ro', uri=True)
    try:
        for row in places:
            actual = catalog.execute('SELECT name, lat, lng FROM places WHERE active AND id=?', (row['place_id'],)).fetchone()
            assert actual == (row['name'], row['lat'], row['lng']), row['name']
            point = Point(row['lng'], row['lat'])
            matches = [(code, name, geom) for code, name, geom in zones if geom.covers(point)]
            expected = (None, None)
            if len(matches) == 1 and matches[0][2].contains(point):
                expected = matches[0][:2]
            print(row['name'], [(code, name) for code, name, _ in matches])
            assert expected == (row['area_code'], row['area_name']), row['name']
    finally:
        catalog.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    verify(parser.parse_args().archive)
