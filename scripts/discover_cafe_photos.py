"""Collect public Commons cafe metadata for branch review, without attaching it."""
import argparse
from collections import deque
import json

from pipeline.catalog_photos import PublicClient, COMMONS, chunks, plain, reusable_image
from pipeline.place_catalog import ROOT, connect, distance_m


def discover():
    client = PublicClient()
    queue = deque([('Category:Cafés in South Korea', 0)])
    visited, files = set(), set()
    while queue:
        category, depth = queue.popleft()
        if category in visited: continue
        visited.add(category)
        continuation = {}
        while True:
            raw = client.get(COMMONS, {'action':'query','format':'json','list':'categorymembers',
                'cmtitle':category,'cmlimit':500,'maxlag':5, **continuation})
            for item in raw.get('query', {}).get('categorymembers', []):
                if item['ns'] == 6: files.add(item['title'])
                if item['ns'] == 14 and depth < 4: queue.append((item['title'], depth + 1))
            continuation = raw.get('continue')
            if not continuation: break
        print(f'Categories {len(visited)}; files {len(files)}; remaining {len(queue)}', flush=True)
    pages = []
    for index, batch in enumerate(chunks(sorted(files), 40), 1):
        raw = client.get(COMMONS, {'action':'query','format':'json','prop':'imageinfo|coordinates',
            'titles':'|'.join(batch),'iiprop':'url|size|mime|extmetadata','iiurlwidth':960,'maxlag':5})
        pages.extend(raw.get('query', {}).get('pages', {}).values())
        print(f'Metadata batch {index}; photos {len(pages)}', flush=True)
    output = ROOT / 'artifacts/cafe-photo-discovery.json'
    output.write_text(json.dumps(pages, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {len(pages)} candidate pages', flush=True)


def report():
    pages = json.loads((ROOT / 'artifacts/cafe-photo-discovery.json').read_text(encoding='utf-8'))
    with connect() as conn:
        cafes = [dict(r) for r in conn.execute("SELECT * FROM places WHERE active=1 AND category='cafe'")]
    results=[]
    for page in pages:
        photo = reusable_image(page)
        if not photo: continue
        info = page['imageinfo'][0]
        meta = {k:plain(v.get('value')) for k,v in info.get('extmetadata',{}).items()}
        nearest = []
        try:
            lat, lng = float(meta['GPSLatitude']), float(meta['GPSLongitude'])
            nearest = sorted((distance_m(lat,lng,c), c['id'], c['name'], c['address']) for c in cafes)[:3]
            if nearest[0][0] > 2000: continue
        except (KeyError, ValueError): lat, lng = None, None
        results.append({'title':page['title'],'description':meta.get('ImageDescription'),
                        'lat':lat,'lng':lng,'nearest':nearest,'license':photo['license']})
    (ROOT/'artifacts/cafe-photo-candidates.json').write_text(json.dumps(results, ensure_ascii=False, indent=2),encoding='utf-8')
    print(f'{len(results)} reusable candidates', flush=True)


def search():
    client = PublicClient()
    output = ROOT / 'artifacts/cafe-photo-discovery.json'
    pages = {p['title']: p for p in json.loads(output.read_text(encoding='utf-8'))} if output.exists() else {}
    queries = ['cafe Seoul', 'coffee Seoul', '카페 서울', 'cafe Busan',
               'coffee Busan', 'cafe Jeju', 'cafe Gangneung']
    for query in queries:
        continuation = {}
        for batch in range(2):
            raw = client.get(COMMONS, {'action':'query','format':'json','generator':'search',
                'gsrsearch':query,'gsrnamespace':6,'gsrlimit':50,'prop':'imageinfo',
                'iiprop':'url|size|mime|extmetadata','iiurlwidth':960,'maxlag':5, **continuation})
            pages.update({p['title']:p for p in raw.get('query',{}).get('pages',{}).values()})
            output.write_text(json.dumps(list(pages.values()),ensure_ascii=False),encoding='utf-8')
            print(f'Search {query}: batch {batch+1}, cumulative {len(pages)} files',flush=True)
            continuation = raw.get('continue')
            if not continuation: break


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-only', action='store_true')
    parser.add_argument('--search', action='store_true')
    args = parser.parse_args()
    if args.search: search()
    elif not args.report_only: discover()
    report()
