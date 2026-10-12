"""Catalog requests: the public preview query and the authenticated query (adds Plus filters)."""
from datetime import date
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import schemas as S

PlaceId = Annotated[str, Field(max_length=64)]


class PreviewQuery(BaseModel):
    # Older web clients may still send removed keys (e.g. photo_only, min_fit): ignore them.
    model_config = ConfigDict(extra='ignore')
    profile: S.Profile = Field(default_factory=S.Profile)
    element: S.Element | None = None
    percents: dict[S.Element, float] | None = None
    visit_date: date
    use_saju: bool = False
    lat: float = Field(37.5796, ge=33, le=39)
    lng: float = Field(126.977, ge=124, le=132)
    # The web app offers 1–50 km; larger areas are refused rather than scanned.
    radius_m: int = Field(5000, ge=500, le=50000)
    time_slot: S.TimeSlot | None = None
    place_group: S.PlaceGroup = 'all'
    # Detail pages send one id; the browser-only bookmark list sends its saved ids.
    place_ids: list[PlaceId] = Field(default_factory=list, max_length=100)
    limit: int = Field(30, ge=1, le=50)
    include_gallery: bool = False

    @model_validator(mode='after')
    def one_gallery(self):
        if self.include_gallery and len(self.place_ids) != 1:
            raise ValueError('Gallery requests require exactly one place')
        return self


class CatalogQuery(PreviewQuery):
    place_ids: list[PlaceId] = Field(default_factory=list, max_length=500)
    photo_only: bool = False
    min_fit: int = Field(0, ge=0, le=100)
