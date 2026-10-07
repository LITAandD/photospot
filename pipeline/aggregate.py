"""사진 1장 분석 → 장면(스팟 × 시간대 × 계절) 단위로 묶어 태그 확정."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from . import color as C
from .config import PipelineConfig, SOURCE_WEIGHT
from .masking import BackgroundMasker, NoMask
from .timeslot import SEASONAL_FEATURE_SEASON, exif_datetime, season_from_month, slot_from_datetime
from .vision import ELEMENT_LABELS, VisionTagger, field_confidence

VISION_FIELDS = ["form", "texture", "scale", "crowd_level", "place_character", "photo_mood"]


@dataclass
class PhotoResult:
    photo_id: str
    spot_id: str
    weight: float
    time_slot: str
    time_source: str               # exif | vision | color | default
    season: str                    # 장면 계절 (계절 요소가 없으면 'all')
    stats: C.ColorStats
    color_tags: dict
    rule_lighting: tuple
    palette_elements: set
    vision: dict | None

    def labels_json(self) -> dict:
        return {"time_source": self.time_source, "color_tags": self.color_tags,
                "rule_lighting": list(self.rule_lighting),
                "palette_elements": sorted(self.palette_elements), "vision": self.vision}


def analyze_photo(photo_id: str, spot_id: str, source: str, img: Image.Image, cfg: PipelineConfig,
                  masker: BackgroundMasker | None = None, tagger: VisionTagger | None = None) -> PhotoResult:
    masker = masker or NoMask()
    small = img.copy()
    small.thumbnail((cfg.analysis_max_side, cfg.analysis_max_side))
    rgb = C.load_rgb(small, cfg.analysis_max_side)
    mask = masker.background_mask(Image.fromarray((rgb * 255).astype(np.uint8)))
    stats = C.analyze_pixels(rgb, mask, cfg)
    t = cfg.colors
    color_tags = {"color_temp": C.classify_color_temp(stats, t),
                  "brightness": C.classify_brightness(stats, t),
                  "saturation": C.classify_saturation(stats, t)}
    rule_light = C.rule_lighting(stats, t)
    vision = tagger.tag(img) if tagger else None

    # 시간대: EXIF > AI > 색 통계 > 기본값
    dt = exif_datetime(img)
    if dt:
        slot, src = slot_from_datetime(dt), "exif"
    elif vision and "time_of_day" in vision:
        slot, src = vision["time_of_day"], "vision"
    elif rule_light[0] in ("cool_artificial_night",) or (rule_light[0] == "warm_artificial" and rule_light[1] >= 0.6):
        slot, src = "night", "color"
    else:
        slot, src = "midday", "default"

    # 계절: 벚꽃·단풍·억새·눈처럼 계절 요소가 보일 때만 계절 장면으로 분리
    feature = (vision or {}).get("seasonal_feature", "none")
    if feature in SEASONAL_FEATURE_SEASON:
        season = SEASONAL_FEATURE_SEASON[feature]
    elif feature == "none" or not dt:
        season = "all"
    else:
        season = season_from_month(dt.month)

    return PhotoResult(photo_id, spot_id, SOURCE_WEIGHT.get(source, 0.7), slot, src, season,
                       stats, color_tags, rule_light, C.palette_elements(stats.palette), vision)


# ---------------------------------------------------------------------------
@dataclass
class SceneTags:
    spot_id: str
    time_slot: str
    season: str
    tags: dict
    tag_confidence: dict
    elements: list
    confidence: float
    photo_ids: list
    needs_review: bool
    reasons: list = field(default_factory=list)


def _vote(pairs: list[tuple[str | None, float]]) -> tuple[str | None, float]:
    score = defaultdict(float)
    for value, w in pairs:
        if value is not None and w > 0:
            score[value] += w
    if not score:
        return None, 0.0
    total = sum(score.values())
    winner = max(score, key=score.get)
    return winner, score[winner] / total


def _averaged_stats(photos: list[PhotoResult]) -> C.ColorStats:
    w = np.array([p.weight * max(p.stats.background_ratio, 0.05) for p in photos])
    w = w / w.sum()
    avg = lambda attr: float(np.dot(w, [getattr(p.stats, attr) for p in photos]))
    first = photos[0].stats
    return C.ColorStats(avg("lab_l"), avg("l_median"), avg("l_stddev"), avg("l_range"), avg("lab_c"),
                        first.hue_deg, None, avg("warmth"), avg("background_ratio"), first.palette)


def aggregate(photos: list[PhotoResult], cfg: PipelineConfig) -> list[SceneTags]:
    groups: dict[tuple, list[PhotoResult]] = defaultdict(list)
    for p in photos:
        groups[(p.spot_id, p.time_slot, p.season)].append(p)
    return [_aggregate_group(key, grp, cfg) for key, grp in groups.items()]


def _aggregate_group(key, photos: list[PhotoResult], cfg: PipelineConfig) -> SceneTags:
    spot_id, slot, season = key
    t = cfg.colors
    tags, conf, reasons = {}, {}, []

    # 1) 색 태그: 가중 평균 통계로 판정, 신뢰도 = 같은 판정을 낸 사진 비율
    avg = _averaged_stats(photos)
    final_color = {"color_temp": C.classify_color_temp(avg, t),
                   "brightness": C.classify_brightness(avg, t),
                   "saturation": C.classify_saturation(avg, t)}
    total_w = sum(p.weight for p in photos)
    for f, v in final_color.items():
        tags[f] = v
        agree = sum(p.weight for p in photos if p.color_tags[f] == v) / total_w
        low_bg = np.mean([p.stats.background_ratio < cfg.min_background_ratio for p in photos])
        conf[f] = round(agree * (0.6 if low_bg > 0.5 else 1.0), 2)
    if conf["color_temp"] < 1 and any(p.stats.background_ratio < cfg.min_background_ratio for p in photos):
        reasons.append("인물 비중이 커서 배경 색 분석이 불안정한 사진 포함")

    # 2) 조명: AI 판정 우선, 색 규칙은 절반 가중치로 보조
    pairs = []
    for p in photos:
        if p.vision and "lighting" in p.vision:
            pairs.append((p.vision["lighting"], p.weight * field_confidence(p.vision, "lighting")))
        pairs.append((p.rule_lighting[0], p.weight * p.rule_lighting[1] * 0.5))
    tags["lighting"], conf["lighting"] = _vote(pairs)
    night_votes = sum(p.rule_lighting[0] == "cool_artificial_night" for p in photos)
    if slot != "night" and night_votes > len(photos) / 2:
        reasons.append("색 분석은 야간인데 시간대는 낮으로 판정됨")

    # 3) 형태·질감·스케일·보조 태그: AI 판정 투표
    has_vision = any(p.vision for p in photos)
    for f in VISION_FIELDS:
        v, c = _vote([(p.vision.get(f), p.weight * field_confidence(p.vision, f))
                      for p in photos if p.vision])
        tags[f] = None if v == "none" else v
        conf[f] = round(c, 2)
    if not has_vision:
        reasons.append("AI 판정 없음: 형태·질감·스케일 등은 수동 입력 필요")

    # 4) 오행: AI가 본 요소(강한 근거) + 팔레트(약한 근거)
    n = len(photos)
    elements = []
    for label, element in ELEMENT_LABELS.items():
        seen = sum(1 for p in photos if p.vision and label in p.vision.get("visible_elements", []))
        pal = sum(1 for p in photos if element in p.palette_elements)
        if seen / n >= cfg.element_vision_share or pal / n >= cfg.element_palette_share:
            elements.append(element)
    if slot == "golden_hour" and "fire" not in elements and tags.get("color_temp") == "warm":
        elements.append("fire")                                 # 노을빛 장면은 화(火)

    # 5) 장면 신뢰도 = 태그 신뢰도 평균 × 사진 수 감쇠
    core = [conf[f] for f in ("color_temp", "brightness", "saturation", "lighting")]
    core += [conf[f] for f in VISION_FIELDS] if has_vision else [0.0]
    scene_conf = round(float(np.mean(core)) * min(1.0, n / cfg.min_photos_full_confidence), 2)
    if n < 3:
        reasons.append(f"사진 {n}장뿐")
    weak = [f for f, c in conf.items() if c < 0.5 and tags.get(f) is not None]
    if weak:
        reasons.append("판정이 엇갈린 태그: " + ", ".join(weak))

    return SceneTags(spot_id, slot, season, tags, conf, sorted(elements), scene_conf,
                     [p.photo_id for p in photos], scene_conf < cfg.review_confidence or bool(reasons), reasons)
