"""Authenticated production access to the same public catalog as the web preview."""
from fastapi import HTTPException
from pipeline import place_catalog as catalog
from pipeline.place_quality import row_exclusion
from .catalog_media import photos_for
from .catalog_models import CatalogQuery
from .catalog_recommendations import recommend
from .schemas import Profile
from pipeline.cafe_photos import display_name


def enabled(request):
    return request.app.state.settings.recommendation_backend == 'catalog'


def evaluate(profile, visit, nearby=True, voter=None, **kwargs):
    body = CatalogQuery(profile=Profile.model_validate(profile), element=profile.get('element'),
                        percents=profile.get('saju_percents'), visit_date=visit, **kwargs)
    return recommend(body, None, nearby, voter=voter)


def detail(profile, visit, place, use_saju=False, voter=None):
    """Score only the requested place; identical to its entry in a nearby evaluation."""
    return evaluate(profile, visit, nearby=False, lat=place['lat'], lng=place['lng'],
                    use_saju=use_saju, place_ids=[place['id']], voter=voter)['places'][place['id']]


def find_many(place_ids) -> dict[str, dict]:
    """Active, displayable catalog places by id in one query (missing ids are omitted)."""
    ids = list(dict.fromkeys(str(p) for p in place_ids))
    out = {}
    if not ids: return out
    with catalog.connect() as conn:
        for start in range(0, len(ids), 400):
            batch = ids[start:start + 400]
            for row in conn.execute(f"SELECT * FROM places WHERE active=1 AND id IN ({','.join('?' * len(batch))})", batch):
                if not row_exclusion(row): out[row['id']] = dict(row)
    return out


def find(place_id):
    row = find_many([place_id]).get(str(place_id))
    if row is None: raise HTTPException(404, '장소를 찾을 수 없어요')
    return row


def find_recommendation(rec_id: int):
    """Catalog recommendation IDs are the persistent catalog row IDs."""
    with catalog.connect() as conn:
        row = conn.execute('SELECT * FROM places WHERE row_id=? AND active=1', (rec_id,)).fetchone()
    if row is None or row_exclusion(row): raise HTTPException(404, '추천 기록을 찾을 수 없어요')
    return dict(row)


def bookmark_rows(ids):
    """Bookmark entries for catalog place ids, in the given order; unknown ids are skipped."""
    places, photos = find_many(ids), photos_for(ids)
    from . import photo_likes
    votes, enabled = photo_likes.snapshot(photos)
    photos = photo_likes.rank(photos, votes, enabled)
    return {pid: {'place_id': pid, 'name': display_name(p), 'address': p['address'],
                  'cover_photo': next(iter(photos.get(pid, [])), None)} for pid, p in places.items()}
