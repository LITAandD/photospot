"""촬영 시각(EXIF) → 시간대·계절."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from PIL import Image

from .config import SUN_TIMES

_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 36867
_DATETIME = 306


def exif_datetime(img: Image.Image) -> datetime | None:
    exif = img.getexif()
    raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL) or exif.get(_DATETIME)
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")   # 시간대 정보 없음 → KST로 간주
    except ValueError:
        return None


def _hm(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def slot_from_datetime(dt: datetime) -> str:
    rise, sset = (_hm(v) for v in SUN_TIMES[dt.month])
    base = dt.replace(second=0, microsecond=0)
    sunrise = datetime.combine(base.date(), rise)
    sunset = datetime.combine(base.date(), sset)
    if base >= sunset + timedelta(minutes=20) or base < sunrise:
        return "night"
    if base >= sunset - timedelta(minutes=75):
        return "golden_hour"
    if base < datetime.combine(base.date(), time(10, 30)):
        return "morning"
    return "midday"


def season_from_month(month: int) -> str:
    return {3: "spring", 4: "spring", 5: "spring", 6: "summer", 7: "summer", 8: "summer",
            9: "autumn", 10: "autumn", 11: "autumn"}.get(month, "winter")


# AI가 찾은 계절 요소 → 장면 계절
SEASONAL_FEATURE_SEASON = {
    "cherry_blossom": "spring", "spring_flowers": "spring",
    "autumn_leaves": "autumn", "silver_grass": "autumn", "snow": "winter",
}
