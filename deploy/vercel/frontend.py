"""Known SPA deep links are real routes; unknown paths retain HTTP 404."""
from functools import lru_cache
from datetime import date
from html import escape as html_escape
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response

SPA_ROUTES = (
    '/home', '/saju', '/result', '/saved', '/settings', '/support', '/privacy',
    '/login', '/accounts', '/admin', '/feedback', '/feedback/{rec_id}', '/place/{place_id}',
    '/diagnosis/personal-color', '/diagnosis/body-type', '/onboarding/basic',
    '/onboarding/style', '/onboarding/traits', '/oauth/naver',
)
# Public pages worth indexing; account, admin and OAuth screens are excluded in robots.txt.
PUBLIC_ROUTES = ('/', '/browse?city=seoul', '/browse?city=busan', '/browse?city=gangneung', '/browse?city=jeju', '/privacy',
                 # app/dist/policies/*.html: JS 없는 정적 문서라 SPA_ROUTES가 아니라 사이트맵에만 넣는다.
                 '/policies/privacy.html', '/policies/terms.html', '/policies/location-terms.html', '/policies/account-deletion.html', '/policies/visitor-photos.html')
ROBOTS = 'User-agent: *\nDisallow: /admin\nDisallow: /accounts\nDisallow: /oauth/\nSitemap: {base}/sitemap.xml\n'


def public_base_url():
    return os.environ.get('PUBLIC_BASE_URL', 'https://photospot.litaandd.com').rstrip('/')


def dated_url(canonical, value):
    try:
        if date.fromisoformat(value).isoformat() == value:
            return canonical + ('&' if '?' in canonical else '?') + 'date=' + value
    except ValueError:
        pass
    return canonical


def page_meta(html, canonical, share, title, description):
    """Escape catalog text; replacement functions keep backslashes literal."""
    values = [(r'<title>.*?</title>', f'<title>{html_escape(title)}</title>'),
              (r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{html_escape(canonical)}">')]
    for attr, key, value in [('property', 'og:url', share), ('property', 'og:title', title),
                             ('name', 'twitter:title', title), ('name', 'description', description),
                             ('property', 'og:description', description), ('name', 'twitter:description', description)]:
        values.append((f'<meta {attr}="{key}" content="[^"]*">', f'<meta {attr}="{key}" content="{html_escape(value)}">'))
    for pattern, replacement in values:
        if re.search(pattern, html, flags=re.S):
            html = re.sub(pattern, lambda _: replacement, html, count=1, flags=re.S)
        elif '</head>' in html:
            html = html.replace('</head>', replacement + '</head>', 1)
    return html


def register_spa_routes(app, entry_file: Path):
    def entry():
        if not entry_file.is_file():
            raise HTTPException(503, '웹 화면을 준비하고 있어요. 잠시 후 다시 확인해 주세요.')
        return FileResponse(entry_file, media_type='text/html')

    for path in SPA_ROUTES:
        app.add_api_route(path, entry, methods=['GET', 'HEAD'], include_in_schema=False)

    def public_list(city: str = '', date_param: str = Query('', alias='date')):
        from api.public_place_info import ORIGINS
        if not entry_file.is_file():
            raise HTTPException(503, '웹 화면을 준비하고 있어요.')
        origin = ORIGINS.get(city)
        canonical = public_base_url() + '/browse' + (f'?city={city}' if origin else '')
        title = f"{origin['label']} 둘러보기 · 포토스팟" if origin else '둘러보기 · 포토스팟'
        return Response(page_meta(entry_file.read_text(encoding='utf-8'), canonical,
            dated_url(canonical, date_param) if origin else canonical, title,
            '개인정보 입력 없이 공간 사진과 확인된 방문 정보를 살펴보세요.'), media_type='text/html')

    app.add_api_route('/browse', public_list, methods=['GET', 'HEAD'], include_in_schema=False)

    def public_detail(place_id: str, city: str = '', date_param: str = Query('', alias='date')):
        from api.catalog_bridge import find_many
        from api.public_place_info import browse_city, ORIGINS
        if not entry_file.is_file():
            raise HTTPException(503, '웹 화면을 준비하고 있어요.')
        place = find_many([place_id]).get(place_id)
        html = entry_file.read_text(encoding='utf-8')
        actual_city = browse_city(place) if place else None
        if place and not city and actual_city:
            canonical = f'{public_base_url()}/browse/{place_id}?city={actual_city}'
            return RedirectResponse(dated_url(canonical, date_param), status_code=302)
        if not place or not city or actual_city != city:
            html = re.sub(r'<link rel="canonical" href="[^"]*">', '<meta name="robots" content="noindex">', html)
            return Response(html, status_code=404, media_type='text/html')
        canonical = f'{public_base_url()}/browse/{place_id}?city={city}'
        title = f"{place['name']} · {ORIGINS[city]['label']} · 포토스팟"
        description = place.get('address') or f"{place['name']}의 공간 사진과 확인된 방문 정보를 살펴보세요."
        html = page_meta(html, canonical, dated_url(canonical, date_param), title, description)
        return Response(html, media_type='text/html')

    app.add_api_route('/browse/{place_id}', public_detail, methods=['GET', 'HEAD'], include_in_schema=False)


def places_with_photos():
    """Active, displayable catalog places that have at least one reusable photo."""
    from api.catalog_bridge import find_many
    from api.catalog_media import photo_counts_for
    from pipeline import place_catalog as catalog
    with catalog.connect() as conn:
        ids = [row[0] for row in conn.execute('SELECT id FROM places WHERE active=1 ORDER BY id')]
    photographed = [pid for pid, count in photo_counts_for(ids).items() if count]
    from api.public_place_info import browse_city
    return {pid: city for pid, place in sorted(find_many(photographed).items()) if (city := browse_city(place))}


@lru_cache(maxsize=4)
def sitemap_xml(base, catalog_key):
    from pipeline import place_catalog as catalog
    lastmod = (catalog.metadata()['fetched_at'] or '')[:10]
    urls = [base + route for route in PUBLIC_ROUTES] + [
        f'{base}/browse/{pid}?city={city}' for pid, city in places_with_photos().items()]
    entries = ''.join(f'<url><loc>{escape(url)}</loc>' + (f'<lastmod>{lastmod}</lastmod>' if lastmod else '') + '</url>\n'
                      for url in urls)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + entries + '</urlset>\n'


def catalog_key():
    from pipeline import place_catalog as catalog
    path = Path(catalog.db_path())
    return str(path), path.stat().st_mtime_ns if path.exists() else 0


def register_seo_routes(app):
    """robots.txt and a sitemap of public pages plus photographed places (cached per catalog file)."""
    def robots():
        return PlainTextResponse(ROBOTS.format(base=public_base_url()))

    def sitemap():
        return Response(sitemap_xml(public_base_url(), catalog_key()), media_type='application/xml')

    app.add_api_route('/robots.txt', robots, methods=['GET', 'HEAD'], include_in_schema=False)
    app.add_api_route('/sitemap.xml', sitemap, methods=['GET', 'HEAD'], include_in_schema=False)
