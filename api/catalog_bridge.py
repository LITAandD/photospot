"""Authenticated production access to the same public catalog as the web preview."""
from fastapi import HTTPException
from pipeline import place_catalog as catalog
from pipeline.place_quality import row_exclusion
from pipeline.catalog_photos import photos_for
from .catalog_models import CatalogQuery
from .catalog_recommendations import recommend
from .schemas import Profile
from pipeline.cafe_photos import display_name


def enabled(request):
    return request.app.state.settings.recommendation_backend == 'catalog'


def evaluate(profile, visit, **kwargs):
    body = CatalogQuery(profile=Profile.model_validate(profile), element=profile.get('element'),
                        percents=profile.get('saju_percents'), visit_date=visit, **kwargs)
    return recommend(body, None)


def find(place_id):
    with catalog.connect() as conn:
        row = conn.execute('SELECT * FROM places WHERE id=? AND active=1', (str(place_id),)).fetchone()
    if row is None or row_exclusion(row): raise HTTPException(404, '장소를 찾을 수 없어요')
    return dict(row)


def bookmarks(conn, user_id):
    with conn.cursor() as cur:
        cur.execute('SELECT place_id::text FROM catalog_bookmarks WHERE user_id=%s ORDER BY created_at DESC LIMIT 500', (user_id,))
        ids = [r[0] for r in cur.fetchall()]
    photos = photos_for(ids)
    rows = []
    for pid in ids:
        try: p = find(pid)
        except HTTPException: continue
        rows.append({'place_id':pid, 'name':display_name(p), 'address':p['address'], 'cover_photo':next(iter(photos.get(pid, [])),None)})
    return rows
