"""API 비즈니스 로직 (DB·HTTP와 분리해서 테스트하기 쉽게)."""
from __future__ import annotations

import io
from datetime import date, time
from typing import Protocol

from PIL import Image, ImageOps

from pipeline.timeslot import exif_datetime

from . import labels as L

PRACTICAL_DIMS = {"pc_season", "pc_tone", "body_type", "height_band"}
ELEMENT_ORDER = ["wood", "fire", "earth", "metal", "water"]
ELEMENT_SHORT = dict(zip(ELEMENT_ORDER, ["목", "화", "토", "금", "수"]))
# Traditional relation directions; the point weights below are PhotoSpot's
# discovery heuristic, not a traditional yongsin diagnosis or a photo-fit score.
GENERATES = dict(zip(ELEMENT_ORDER, ELEMENT_ORDER[1:] + ELEMENT_ORDER[:1]))
CONTROLS = {"wood": "earth", "fire": "metal", "earth": "water", "metal": "wood", "water": "fire"}


def element_priorities(percents: dict, day_element: str) -> list[dict]:
    values = {e: float(percents[e]) for e in ELEMENT_ORDER}
    balanced = min(values.values()) == max(values.values())
    # Stored one-decimal percentages can sum to 99.9 or 100.1.
    normalize = 100 / sum(values.values())
    priorities = []
    for element in ELEMENT_ORDER:
        percent = values[element]
        personal = round(max(0, 20 - percent * normalize) / 20 * 70, 1)
        day, name = ELEMENT_SHORT[day_element], ELEMENT_SHORT[element]
        if GENERATES[day_element] == element:
            relation, points, label = "day_generates_place", 30, f"일진 {day} → 장소 {name} 상생"
        elif day_element == element:
            relation, points, label = "same", 24, f"일진과 장소가 같은 {name}"
        elif GENERATES[element] == day_element:
            relation, points, label = "place_generates_day", 18, f"장소 {name} → 일진 {day} 상생"
        elif CONTROLS[element] == day_element:
            relation, points, label = "place_controls_day", 6, f"장소 {name} → 일진 {day} 상극"
        else:
            relation, points, label = "day_controls_place", 0, f"일진 {day} → 장소 {name} 상극"
        priorities.append({"element": element, "label": name, "personal_percent": percent,
                           "personal_points": personal, "day_points": points,
                           "day_relation": relation, "day_relation_label": label,
                           "score": round(personal + points, 1), "is_candidate": balanced or percent * normalize < 20})
    return sorted(priorities, key=lambda p: (-p['score'], ELEMENT_ORDER.index(p['element'])))


def saju_place_match(elements, daily: dict | None) -> dict | None:
    if not daily:
        return None
    targets = set(daily.get('target_elements', []))
    # Highest supported element wins; multi-tagged places receive no automatic bonus.
    return next((p for p in daily.get('element_priorities', []) if p['element'] in elements and p['element'] in targets), None)


def recommended_elements(elements, daily: dict | None) -> list[str]:
    if not daily:
        return []
    targets = daily.get("target_elements")
    if targets is not None:
        return [e for e in targets if e in elements]
    targets = set(daily["deficient_elements"]) | {daily["day_element"]}
    return [e for e in ELEMENT_ORDER if e in targets and e in elements]


# ---------------------------------------------------------------------------
# 추천 이유: 점수 내역(breakdown) + 장면 태그 → 사람이 읽는 문장
# ---------------------------------------------------------------------------
def deficient_elements(percents: dict | None) -> list[str] | None:
    """Lowest stored percentages, including ties. None means missing/invalid data."""
    import math
    if not percents or set(percents) != set(ELEMENT_ORDER):
        return None
    try:
        values = {key: float(percents[key]) for key in ELEMENT_ORDER}
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(v) or not 0 <= v <= 100 for v in values.values()) or not 99 <= sum(values.values()) <= 101:
        return None
    low = min(values.values())
    if low == max(values.values()):
        return []
    return [key for key in ELEMENT_ORDER if values[key] == low]


def daily_context(visit: date, element: str | None, enabled: bool, percents: dict | None = None) -> dict | None:
    """Personal deficits and the selected Korean calendar day's element, combined."""
    lacking = deficient_elements(percents)
    if not enabled or not element or lacking is None:
        return None
    from saju.pillars import day_pillar
    from saju.elements import STEM_ELEMENT
    pillar = day_pillar(visit)
    day_element = STEM_ELEMENT[pillar.stem]
    priorities = element_priorities(percents, day_element)
    candidates = [p for p in priorities if p['is_candidate']]
    cutoff = candidates[min(1, len(candidates) - 1)]['score']
    targets = [p['element'] for p in candidates if p['score'] >= cutoff]
    return {"pillar": f"{pillar.hangul}({pillar.hanja})", "day_element": day_element,
            "day_label": L.VALUE_LABELS["element"][day_element], "personal_element": element,
            "personal_label": L.VALUE_LABELS["element"][element],
            "deficient_elements": lacking,
            "deficient_labels": [ELEMENT_SHORT[e] for e in lacking],
            "minimum_percent": min(float(v) for v in percents.values()),
            "target_elements": targets, "target_labels": [ELEMENT_SHORT[e] for e in targets],
            "element_priorities": priorities, "method": "personal70_daily30_v1",
            "note": ("20% 미만인 오행을 보완 후보로 두고 부족 정도 최대 70점과 일진 관계 최대 30점을 합산해요. "
                     if lacking else "오행 비율이 같아 개인 부족 점수는 0점이며 일진 관계로 우선순위를 정해요. ") +
                    "상위 두 오행을 우선 추천하며 경계의 동점은 함께 포함해요. 확인된 장소 오행 중 가장 높은 종합 점수로 정렬해요. "
                    "포토스팟의 취향 탐색 기준이며 전통 명리의 용신 판정이나 사진 정합도 점수는 아니에요."}


def reasons(breakdown: dict, scene: dict, elements: list[str], element: str | None, top: int = 5,
            day_element: str | None = None, deficient: list[str] | None = None) -> list[dict]:
    out = []
    for key, pts in (breakdown or {}).items():
        pts = float(pts)
        if pts <= 0:
            continue
        dim, attr = key.split(".", 1)
        if attr == "element":
            if dim == "element" and deficient is not None:
                matched = [L.VALUE_LABELS['element'][e] for e in deficient if e in elements]
                if matched:
                    out.append({"label": f"부족한 {'·'.join(matched)} 보완 · 장소 오행 대응", "points": pts, "layer": "auxiliary"})
                continue
            selected = day_element if dim == "day_element" else element
            if not selected or selected not in elements:
                continue
            label = f"{'촬영일 일진의' if dim == 'day_element' else '나의'} {L.VALUE_LABELS['element'][selected]}과 닮은 곳"
        else:
            value = scene.get(attr)
            label = L.VALUE_LABELS.get(attr, {}).get(value)
            if not label:
                continue
        out.append({"label": label, "points": pts,
                    "layer": "practical" if dim in PRACTICAL_DIMS else "auxiliary"})
    out.sort(key=lambda r: (-r["points"], r["label"]))
    return out[:top]


# ---------------------------------------------------------------------------
# 촬영 팁
# ---------------------------------------------------------------------------
OUTFIT = {
    "spring_warm": "아이보리·코랄 계열 상의가 따뜻한 빛과 잘 어울려요",
    "summer_cool": "화이트·라벤더 계열 상의가 쿨톤 배경과 이어져요",
    "autumn_warm": "카멜·카키 계열 상의로 따뜻한 배경과 맞춰보세요",
    "winter_cool": "블랙·화이트처럼 대비가 큰 코디가 또렷해 보여요",
}
LIGHT = {
    "spring_warm": "맑은 날 오전 햇살을 노려보세요",
    "summer_cool": "흐린 날이 오히려 좋아요. 빛이 더 부드러워져요",
    "autumn_warm": "해 지기 한 시간 전 골든아워를 추천해요",
    "winter_cool": "조명이 켜지는 해 질 녘 이후가 좋아요",
}


def tips(profile: dict, height_band: str | None, scene: dict) -> list[dict]:
    out = []
    season = profile.get("pc_season")
    if season:
        out.append({"kind": "outfit", "label": "코디", "text": OUTFIT[season]})
    form, scale = scene.get("form"), scene.get("scale")
    if height_band == "tall" and scale == "spacious":
        comp = "넓은 공간을 살려 전신샷을 찍어보세요"
    elif height_band == "small":
        comp = "로우앵글로 찍거나 계단 위에 서면 비율이 좋아 보여요"
    elif form == "curved":
        comp = "곡선 구조를 뒤에 두고 상반신 위주로 찍어보세요"
    elif form == "linear":
        comp = "직선이 수평·수직으로 맞게 정면에서 찍어보세요"
    else:
        comp = "자연 배경을 넓게 담는 가로 구도가 좋아요"
    out.append({"kind": "composition", "label": "구도", "text": comp})
    if season:
        out.append({"kind": "light", "label": "빛", "text": LIGHT[season]})
    return out


# ---------------------------------------------------------------------------
# 운영 조건 → 안내 문구
# ---------------------------------------------------------------------------
def _md(md: str) -> str:
    m, d = md.split("-")
    return f"{int(m)}월 {int(d)}일"


def visit_notes(rules: list[dict]) -> list[str]:
    notes = []
    for r in rules:
        if r["rule_type"] == "weekly_closed":
            notes.append(f"{L.WEEKDAY[r['weekday']]}요일 휴무")
        elif r["rule_type"] == "open_period":
            span = f"{_md(r['start_md'])}~{_md(r['end_md'])}" if r["start_md"] else f"{r['start_date']}~{r['end_date']}"
            notes.append(f"운영 기간 {span}")
        elif r["rule_type"] == "closed_period":
            span = f"{_md(r['start_md'])}~{_md(r['end_md'])}" if r["start_md"] else f"{r['start_date']}~{r['end_date']}"
            notes.append(f"휴무 기간 {span}")
    notes.append("영업시간·입장료는 지도 앱에서 최신 정보를 확인하세요")
    return notes


# ---------------------------------------------------------------------------
# 나의 포토 타입 카드: match_rules에서 바로 뽑아 점수 로직과 항상 일치
# ---------------------------------------------------------------------------
def type_card(profile: dict, saju_element: str | None, rules: list[dict]) -> dict:
    season, body = profile.get("pc_season"), profile.get("body_type")
    if not season and not body:
        return {"name": "아직 타입을 알 수 없어요", "subtitle": "퍼스널컬러나 체형을 입력해 주세요",
                "best_light": [], "good_backgrounds": [], "avoid": [], "lucky": None}
    parts = [p for p in (L.SEASON.get(season), L.BODY.get(body)) if p]
    name = " ".join(parts)
    if saju_element:
        name = f"{L.ELEMENT_PREFIX[saju_element]} {name}"
    tone = profile.get("pc_subtone")
    sub = [f"{L.SEASON[season]} {L.SUBTONE[tone]}" if season and tone else L.SEASON.get(season),
           L.BODY.get(body),
           f"{float(profile['height_cm']):g}cm" if profile.get("height_cm") else None,
           profile.get("mbti")]
    good, bad, light = [], [], []
    for r in rules:
        label = L.VALUE_LABELS.get(r["attribute"], {}).get(r["attr_value"])
        if not label:
            continue
        if r["attribute"] == "lighting" and r["score"] > 0:
            light.append(label)
        elif r["score"] > 0:
            good.append(label)
        else:
            bad.append(label)
    return {"name": name, "subtitle": " · ".join(s for s in sub if s),
            "best_light": light, "good_backgrounds": good, "avoid": bad,
            "lucky": f"가장 강한 {L.VALUE_LABELS['element'][saju_element]}과 닮은 {L.ELEMENT_PLACE[saju_element]}"
                     if saju_element else None}


# ---------------------------------------------------------------------------
# 자가진단 (앱 화면과 같은 문항. 서버에 두면 앱 업데이트 없이 문항을 고칠 수 있음)
# ---------------------------------------------------------------------------
PC_QUESTIONS = [
    ("손목 안쪽 혈관은 어떤 색에 가까운가요?", "w", [("초록빛이에요", 1), ("파란빛이나 보랏빛이에요", -1), ("잘 모르겠어요", 0)]),
    ("더 잘 어울린다는 말을 듣는 액세서리는?", "w", [("골드", 1), ("실버", -1), ("둘 다 비슷해요", 0)]),
    ("햇볕에 오래 있으면 피부가 어떻게 되나요?", "w", [("금방 구릿빛으로 타요", 1), ("빨갛게 달아오르고 잘 안 타요", -1), ("잘 모르겠어요", 0)]),
    ("머리카락과 눈동자 색은 어떤가요?", "d", [("밝은 갈색에 가까워요", -1), ("짙은 흑갈색이나 검정이에요", 1), ("중간이에요", 0)]),
    ("얼굴 인상은 어느 쪽에 가까운가요?", "d", [("부드럽고 은은한 편", -1), ("또렷하고 선명한 편", 1), ("중간이에요", 0)]),
    ("칭찬받는 옷 색은 어느 쪽인가요?", "d", [("파스텔이나 흐린 색", -1), ("진하거나 선명한 색", 1), ("둘 다 비슷해요", 0)]),
]
BODY_QUESTIONS = [
    ("손목을 잡았을 때 느낌은?", [("단면이 둥글고 두툼해요", "straight"), ("납작하고 가늘어요", "wave"), ("뼈가 도드라지고 단단해요", "natural")]),
    ("쇄골은 어떻게 보이나요?", [("잘 드러나지 않아요", "straight"), ("가늘게 보여요", "wave"), ("크고 뚜렷해요", "natural")]),
    ("살이 찌면 어디부터 붙나요?", [("상체와 배 쪽", "straight"), ("하체와 엉덩이 쪽", "wave"), ("전체적으로 고르게", "natural")]),
    ("피부를 만졌을 때 느낌은?", [("탄력 있고 단단해요", "straight"), ("부드럽고 말랑해요", "wave"), ("얇고 뼈나 힘줄이 느껴져요", "natural")]),
    ("잘 어울린다는 말을 듣는 옷은?", [("심플한 셔츠나 정장", "straight"), ("니트, 러플, 플레어 스커트", "wave"), ("오버핏, 린넨, 데님", "natural")]),
]


def diagnosis_questions(kind: str) -> list[dict]:
    if kind == "personal-color":
        return [{"id": i, "text": q, "options": [o for o, _ in opts]} for i, (q, _, opts) in enumerate(PC_QUESTIONS)]
    return [{"id": i, "text": q, "options": [o for o, _ in opts]} for i, (q, opts) in enumerate(BODY_QUESTIONS)]


def _season_of(w: int, d: int) -> str:
    if w > 0:
        return "autumn_warm" if d > 0 else "spring_warm"
    return "winter_cool" if d > 0 else "summer_cool"


def diagnose(kind: str, answers: list[int]) -> dict:
    qs = PC_QUESTIONS if kind == "personal-color" else BODY_QUESTIONS
    if len(answers) != len(qs) or any(not (0 <= a < 3) for a in answers):
        raise ValueError(f"답변은 {len(qs)}개, 각각 0~2 사이여야 해요")
    if kind == "personal-color":
        w = sum(qs[i][2][a][1] for i, a in enumerate(answers) if qs[i][1] == "w")
        d = sum(qs[i][2][a][1] for i, a in enumerate(answers) if qs[i][1] == "d")
        result = _season_of(w, d)
        second = _season_of(-1 if w > 0 else 1, d) if abs(w) <= abs(d) else _season_of(w, -1 if d > 0 else 1)
        strength = abs(w) + abs(d)
        conf = "high" if strength >= 4 else "medium" if strength >= 2 else "low"
        return {"result": result, "result_label": L.SEASON[result], "confidence": conf,
                "second": second, "second_label": L.SEASON[second],
                "note": "자가진단은 참고용이에요. 정확하게 알고 싶다면 드레이핑 진단을 받아보세요."}
    counts = {"straight": 0, "wave": 0, "natural": 0}
    for i, a in enumerate(answers):
        counts[qs[i][1][a][1]] += 1
    ranked = sorted(counts, key=lambda k: (-counts[k], list(counts).index(k)))
    top, runner = ranked[0], ranked[1]
    conf = "high" if counts[top] >= 4 else "medium" if counts[top] > counts[runner] else "low"
    return {"result": top, "result_label": L.BODY[top], "confidence": conf,
            "second": runner if counts[runner] > 0 else None,
            "second_label": L.BODY[runner] if counts[runner] > 0 else None,
            "note": "자가진단은 참고용이에요. 결과는 언제든 바꿀 수 있어요."}


# ---------------------------------------------------------------------------
# 사주 오행 계산기 (saju 패키지). 결과의 dominant(가장 많은 오행)를 추천에 쓴다.
# ---------------------------------------------------------------------------
class ElementCalculator(Protocol):
    def calculate(self, birth_date: date | str, birth_time: time | None, calendar: str, leap_month: bool = False, birth_hour_branch: str | None = None):
        """saju.calculator.SajuResult 를 돌려준다."""


class UnconfiguredCalculator:
    def calculate(self, birth_date, birth_time, calendar, leap_month=False, birth_hour_branch=None):
        raise NotImplementedError("사주 계산 모듈이 아직 설정되지 않았어요")


def lacking_element(counts: dict[str, int]) -> str:
    """(예전 방식) 가장 적은 오행. 동률이면 목→화→토→금→수 순."""
    return min(ELEMENT_ORDER, key=lambda e: (counts.get(e, 0), ELEMENT_ORDER.index(e)))


# ---------------------------------------------------------------------------
# 업로드 사진 정리: 위치(GPS)·기기 정보 제거, 촬영 시각만 남김
# ---------------------------------------------------------------------------
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def sanitize_photo(data: bytes, max_side: int = 3000) -> tuple[bytes, object]:
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        if img.width * img.height > 25_000_000:
            raise ValueError("이미지 해상도가 너무 커요")
        img.load()
    except Exception as e:
        raise ValueError("이미지를 읽을 수 없어요") from e
    if fmt not in ALLOWED_FORMATS:
        raise ValueError("JPEG, PNG, WebP만 올릴 수 있어요")
    taken = exif_datetime(img)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    exif = Image.Exif()
    if taken:
        exif.get_ifd(0x8769)[36867] = taken.strftime("%Y:%m:%d %H:%M:%S")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, exif=exif.tobytes())
    return buf.getvalue(), taken


def photo_attribution(source: str, license: str) -> tuple[str, bool]:
    """(출처 표기, 원본 비율 유지 여부)."""
    if source == "tourapi":
        kind = "제1유형" if license == "kogl_type1" else "제3유형"
        return f"사진: 한국관광공사 (공공누리 {kind})", license == "kogl_type3"
    if source == "owner_upload":
        return "사진: 장소 제공", False
    return "사진: 포토스팟", False
