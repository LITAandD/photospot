"""Smoke test the default member API of the locally built CI image, using the isolated CI database."""
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main():
    base = 'http://127.0.0.1:8092/v1'
    auth = Request(base + '/auth/google', data=b'{"token":"dev:kto-docker-smoke"}',
                   headers={'Content-Type': 'application/json'})
    with urlopen(auth, timeout=15) as response:
        token = json.load(response)['access_token']
    records = json.loads(Path('deploy/data/reviewed_tourism_photos.json').read_text(encoding='utf-8'))
    for name in ('경포대', '제주성지'):
        record = next(row for row in records if row['place']['name'] == name)
        place, photo = record['place'], record['photo']
        query = urlencode(dict(lat=place['lat'], lng=place['lng'], radius_m=500, limit=50))
        request = Request(f'{base}/recommendations?{query}', headers={'Authorization': f'Bearer {token}'})
        with urlopen(request, timeout=30) as response:
            item = next(i for i in json.load(response)['items'] if i['place_id'] == place['id'])
        cover = item['cover_photo']
        assert cover['url'] == photo['url'] and cover['license_url'] == photo['license_url']
        assert cover['attribution'] == photo['credit']
        print(f'{name} · HTTP 200 · reviewed cover and attribution verified')


if __name__ == '__main__':
    main()
