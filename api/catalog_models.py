"""Shared catalog request used by authenticated API and local preview."""
from datetime import date
from pydantic import BaseModel, Field
from . import schemas as S


class CatalogQuery(BaseModel):
    profile: S.Profile = Field(default_factory=S.Profile)
    element: S.Element | None = None
    percents: dict[S.Element, float] | None = None
    visit_date: date
    use_saju: bool = False
    lat: float = Field(37.5796, ge=33, le=39)
    lng: float = Field(126.977, ge=124, le=132)
    radius_m: int = Field(5000, ge=500, le=50000)
    time_slot: S.TimeSlot | None = None
    place_group: S.PlaceGroup = 'all'
    place_ids: list[str] = Field(default_factory=list, max_length=500)
    limit: int = Field(30, ge=1, le=50)
    photo_only: bool = False
    min_fit: int = Field(0, ge=0, le=100)
