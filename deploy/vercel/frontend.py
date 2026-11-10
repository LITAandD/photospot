"""Known SPA deep links are real routes; unknown paths retain HTTP 404."""
from functools import lru_cache
import os
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response

SPA_ROUTES = (
    '/home', '/saju', '/result', '/saved', '/settings', '/support', '/privacy',
    '/login', '/accounts', '/admin', '/feedback', '/feedback/{rec_id}', '/place/{place_id}',
    '/diagnosis/personal-color', '/diagnosis/body-type', '/onboarding/basic',
    '/onboarding/style', '/onboarding/traits', '/oauth/naver',
)
# Public pages worth indexing; account, admin and OAuth screens are excluded in robots.txt.
PUBLIC_ROUTES = ('/', '/home', '/saju', '/support', '/privacy',
                 # app/dist/policies/*.html: JS 없는 정적 문서라 SPA_ROUTES가 아니라 사이트맵에만 넣는다.
                 '/policies/privacy.html', '/policies/terms.html', '/policies/location-terms.html', '/policies/account-deletion.html')
ROBOTS = 'User-agent: *\nDisallow: /admin\nDisallow: /accounts\nDisallow: /oauth/\nSitemap: {base}/sitemap.xml\n'


def public_base_url():
    return os.environ.get('PUBLIC_BASE_URL', 'https://photospot.litaandd.com').rstrip('/')


def register_spa_routes(app, entry_file: Path):
    def entry():
        if not entry_file.is_file():
            raise HTTPException(503, '웹 화면을 준비하고 있어요. 잠시 후 다시 확인해 주세요.')
        return FileResponse(entry_file, media_type='text/html')

    for path in SPA_ROUTES:
        app.add_api_route(path, entry, methods=['GET', 'HEAD'], include_in_schema=False)


def places_with_photos():
    """Active, displayable catalog places that have at least one reusable photo."""
    from api.catalog_bridge import find_many
    from api.catalog_media import photo_counts_for
    from pipeline import place_catalog as catalog
    with catalog.connect() as conn:
        ids = [row[0] for row in conn.execute('SELECT id FROM places WHERE active=1 ORDER BY id')]
    photographed = [pid for pid, count in photo_counts_for(ids).items() if count]
    return sorted(find_many(photographed))


@lru_cache(maxsize=4)
def sitemap_xml(base, catalog_key):
    from pipeline import place_catalog as catalog
    lastmod = (catalog.metadata()['fetched_at'] or '')[:10]
    urls = [base + route for route in PUBLIC_ROUTES] + [f'{base}/place/{pid}' for pid in places_with_photos()]
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
