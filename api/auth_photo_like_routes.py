"""Account-authenticated catalog photo likes (not imported by the public preview)."""
from uuid import UUID
from fastapi import APIRouter, Depends
from .auth import CurrentUser, current_user
from .photo_like_routes import LikeIn, LikeOut, change_like

router = APIRouter(prefix='/v1')


@router.post('/places/{place_id}/photo-likes', response_model=LikeOut, tags=['recommend'])
def account_like(place_id: UUID, body: LikeIn, user: CurrentUser = Depends(current_user)):
    # current_user releases its DB connection before returning.
    return change_like(str(place_id), body, 'account:' + str(user.id))
