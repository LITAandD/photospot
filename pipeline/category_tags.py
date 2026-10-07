"""TourAPI 분류 코드 → 초기 장면 태그 (사진 분석 전 '콜드 스타트').

정확도는 낮지만(신뢰도 0.3) 가져온 즉시 추천 대상이 되고, 파이프라인이 사진을 분석하면 자동 태그를 덮어쓴다.
소분류(cat3) 규칙이 있으면 그것을, 없으면 중분류(cat2), 대분류(cat1) 순으로 적용한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Baseline:
    category: str                       # places.category
    time_slot: str = "midday"
    color_temp: str | None = None
    brightness: str | None = None
    saturation: str | None = None
    lighting: str | None = "diffused_natural"
    form: str | None = None
    texture: str | None = None
    scale: str | None = "spacious"
    crowd_level: str | None = "moderate"
    place_character: str | None = "concept"
    photo_mood: str | None = "emotional"
    elements: tuple[str, ...] = ()
    season: str = "all"
    extra_scenes: tuple[dict, ...] = field(default_factory=tuple)   # 야경 등 추가 장면


NATURE_OPEN = dict(color_temp="neutral", brightness="bright_soft", saturation="mid", form="organic", texture="rough",
                   scale="spacious", place_character="concept", photo_mood="emotional")
GOLDEN_EXTRA = ({"time_slot": "golden_hour", "color_temp": "warm", "brightness": "mid", "lighting": "direct_golden", "elements": ("fire",)},)
NIGHT_EXTRA = ({"time_slot": "night", "color_temp": "cool", "brightness": "high_contrast", "lighting": "cool_artificial_night", "saturation": "vivid"},)

CAT3: dict[str, Baseline] = {
    # 자연
    "A01010400": Baseline("attraction", **NATURE_OPEN, elements=("wood", "earth")),                       # 산
    "A01010500": Baseline("attraction", **NATURE_OPEN, elements=("wood",)),                               # 자연생태관광지
    "A01010600": Baseline("park", **NATURE_OPEN, elements=("wood",)),                                     # 자연휴양림
    "A01010700": Baseline("park", **{**NATURE_OPEN, "texture": "soft", "form": "curved"}, elements=("wood",)),   # 수목원
    "A01010800": Baseline("attraction", **{**NATURE_OPEN, "color_temp": "cool"}, elements=("water", "wood")),    # 폭포
    "A01010900": Baseline("attraction", **{**NATURE_OPEN, "color_temp": "cool"}, elements=("water", "wood")),    # 계곡
    "A01011100": Baseline("attraction", **{**NATURE_OPEN, "color_temp": "cool"}, elements=("water", "metal"), extra_scenes=GOLDEN_EXTRA),  # 해안절경
    "A01011200": Baseline("attraction", **{**NATURE_OPEN, "color_temp": "cool", "brightness": "bright_soft"}, elements=("water",), extra_scenes=GOLDEN_EXTRA),  # 해수욕장
    "A01011300": Baseline("attraction", **{**NATURE_OPEN, "color_temp": "cool"}, elements=("water", "wood"), extra_scenes=GOLDEN_EXTRA),   # 섬
    "A01011400": Baseline("attraction", **{**NATURE_OPEN, "form": "linear", "texture": "rough"}, elements=("water",), extra_scenes=GOLDEN_EXTRA),  # 항구/포구
    "A01011600": Baseline("attraction", **{**NATURE_OPEN, "form": "linear", "texture": "sleek"}, elements=("water", "metal")),   # 등대
    "A01011700": Baseline("park", **{**NATURE_OPEN, "color_temp": "cool"}, elements=("water", "wood"), extra_scenes=GOLDEN_EXTRA),   # 호수
    "A01011800": Baseline("park", **{**NATURE_OPEN, "color_temp": "cool"}, elements=("water",), extra_scenes=GOLDEN_EXTRA),   # 강
    "A01011900": Baseline("attraction", color_temp="cool", brightness="high_contrast", saturation="mid", lighting="cool_artificial_night",
                          form="organic", texture="rough", scale="medium", elements=("earth", "water")),         # 동굴
    # 인문 · 역사
    "A02010100": Baseline("heritage", color_temp="warm", brightness="mid", saturation="muted", lighting="direct_golden", form="linear",
                          texture="rough", scale="spacious", crowd_level="busy", place_character="detail", photo_mood="structural",
                          elements=("wood", "earth")),                                                       # 고궁
    "A02010200": Baseline("heritage", color_temp="warm", brightness="mid", saturation="muted", lighting="direct_golden", form="linear",
                          texture="rough", scale="spacious", photo_mood="structural", elements=("earth", "metal")),   # 성
    "A02010400": Baseline("heritage", color_temp="warm", brightness="mid", saturation="muted", form="linear", texture="rough",
                          scale="medium", crowd_level="quiet", place_character="detail", elements=("wood", "earth")),   # 고택
    "A02010600": Baseline("heritage", color_temp="warm", brightness="mid", saturation="muted", form="linear", texture="rough",
                          scale="medium", place_character="detail", elements=("wood", "earth")),             # 민속마을
    "A02010700": Baseline("heritage", color_temp="warm", brightness="mid", saturation="muted", form="organic", texture="rough",
                          scale="spacious", crowd_level="quiet", elements=("earth",)),                       # 유적지/사적지
    "A02010800": Baseline("heritage", color_temp="warm", brightness="mid", saturation="mid", form="linear", texture="rough",
                          scale="medium", crowd_level="quiet", place_character="detail", elements=("wood", "earth")),   # 사찰
    # 건축 · 조형물
    "A02050100": Baseline("attraction", color_temp="cool", brightness="high_contrast", saturation="mid", lighting="cool_artificial_night",
                          form="linear", texture="sleek", time_slot="night", photo_mood="structural", elements=("metal", "water")),   # 다리/대교
    "A02050200": Baseline("attraction", color_temp="cool", brightness="high_contrast", saturation="mid", form="linear", texture="sleek",
                          photo_mood="structural", elements=("metal",), extra_scenes=NIGHT_EXTRA),          # 전망대
    "A02050300": Baseline("attraction", color_temp="cool", brightness="high_contrast", saturation="vivid", lighting="cool_artificial_night",
                          form="organic", texture=None, time_slot="night", crowd_level="busy", elements=("water",)),   # 분수
    "A02050600": Baseline("attraction", color_temp="cool", brightness="high_contrast", saturation="mid", form="linear", texture="sleek",
                          photo_mood="structural", elements=("metal",), extra_scenes=NIGHT_EXTRA),          # 유명건물
    # 문화시설
    "A02060100": Baseline("museum", color_temp="neutral", brightness="bright_soft", saturation="muted", form="linear", texture="sleek",
                          crowd_level="quiet", photo_mood="structural", elements=("metal",)),               # 박물관
    "A02060300": Baseline("museum", color_temp="neutral", brightness="bright_soft", saturation="muted", form="linear", texture="sleek",
                          crowd_level="quiet", photo_mood="structural", elements=("metal",)),               # 전시관
    "A02060500": Baseline("museum", color_temp="cool", brightness="bright_soft", saturation="muted", form="linear", texture="sleek",
                          crowd_level="quiet", photo_mood="structural", elements=("metal",)),               # 미술관/화랑
    "A02060900": Baseline("museum", color_temp="warm", brightness="mid", saturation="muted", form="linear", texture="soft",
                          scale="medium", crowd_level="quiet", place_character="detail", elements=("wood",)),   # 도서관
    # 휴양 · 공원
    "A02020600": Baseline("attraction", color_temp="warm", brightness="bright_soft", saturation="vivid", form="curved", texture="soft",
                          crowd_level="busy", elements=("fire",), extra_scenes=NIGHT_EXTRA),                # 테마공원
    "A02020700": Baseline("park", **NATURE_OPEN, elements=("wood",), extra_scenes=GOLDEN_EXTRA),             # 공원
    # 카페
    "A05020900": Baseline("cafe", color_temp="warm", brightness="mid", saturation="muted", lighting="warm_artificial", form="curved",
                          texture="soft", scale="compact", crowd_level="moderate", place_character="detail", elements=("wood",)),   # 카페/전통찻집
}

CAT2: dict[str, Baseline] = {
    "A0101": Baseline("attraction", **NATURE_OPEN, elements=("wood",)),                                     # 자연관광지
    "A0201": Baseline("heritage", color_temp="warm", brightness="mid", saturation="muted", form="linear", texture="rough", elements=("earth",)),   # 역사관광지
    "A0202": Baseline("park", **NATURE_OPEN),                                                                # 휴양관광지
    "A0205": Baseline("attraction", color_temp="cool", brightness="high_contrast", saturation="mid", form="linear", texture="sleek",
                      photo_mood="structural", elements=("metal",)),                                        # 건축/조형물
    "A0206": Baseline("museum", color_temp="neutral", brightness="bright_soft", saturation="muted", form="linear", texture="sleek",
                      crowd_level="quiet", photo_mood="structural", elements=("metal",)),                   # 문화시설
    "A0502": Baseline("cafe", color_temp="warm", brightness="mid", saturation="muted", lighting="warm_artificial", form="curved",
                      texture="soft", scale="compact", place_character="detail"),                          # 카페 (음식점 하위)
}

CAT1: dict[str, Baseline] = {"A01": Baseline("attraction", **NATURE_OPEN), "A02": Baseline("attraction"), "A05": Baseline("restaurant")}

CONTENT_TYPE_FALLBACK = {"12": "attraction", "14": "museum", "39": "restaurant", "28": "attraction", "15": "festival_site"}


def baseline_for(cat1: str | None, cat2: str | None, cat3: str | None, content_type: str | None) -> Baseline:
    b = CAT3.get(cat3 or "") or CAT2.get(cat2 or "") or CAT1.get(cat1 or "")
    if b:
        return b
    return Baseline(CONTENT_TYPE_FALLBACK.get(content_type or "", "other"))


def scenes_from(b: Baseline) -> list[dict]:
    """초기 장면 목록 (대표 장면 + 추가 장면). scenes 컬럼명으로 된 dict."""
    base = {"time_slot": b.time_slot, "season": b.season, "color_temp": b.color_temp, "brightness": b.brightness,
            "saturation": b.saturation, "lighting": b.lighting, "form": b.form, "texture": b.texture, "scale": b.scale,
            "crowd_level": b.crowd_level, "place_character": b.place_character, "photo_mood": b.photo_mood,
            "elements": list(b.elements)}
    out = [base]
    for extra in b.extra_scenes:
        sc = {**base, **{k: v for k, v in extra.items() if k != "elements"}}
        sc["elements"] = sorted(set(base["elements"]) | set(extra.get("elements", ())))
        out.append(sc)
    return out
