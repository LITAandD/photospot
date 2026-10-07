"""Claude 비전으로 색 통계만으로는 알 수 없는 태그(조명·형태·질감·스케일 등)를 판정.

도구 호출을 강제해서 정해진 값(enum)만 나오도록 구조화된 결과를 받는다.
대량 처리는 build_batch_requests()로 Message Batches API에 넣는 것을 권장.
"""
from __future__ import annotations

import base64
import io
from typing import Protocol

from PIL import Image, ImageOps

ENUMS = {
    "time_of_day":     ["morning", "midday", "golden_hour", "night"],
    "lighting":        ["diffused_natural", "direct_golden", "warm_artificial", "cool_artificial_night"],
    "form":            ["linear", "curved", "organic"],
    "texture":         ["sleek", "soft", "rough", "none"],
    "scale":           ["compact", "medium", "spacious"],
    "crowd_level":     ["quiet", "moderate", "busy"],
    "place_character": ["detail", "concept"],
    "photo_mood":      ["structural", "emotional"],
    "seasonal_feature": ["none", "cherry_blossom", "spring_flowers", "autumn_leaves", "silver_grass", "snow"],
}
ELEMENT_LABELS = {"plants": "wood", "sunset_or_fire": "fire", "earth_or_clay": "earth",
                  "stone_or_metal": "metal", "water": "water"}
FIELDS = [k for k in ENUMS]

TOOL = {
    "name": "record_scene_tags",
    "description": "사진 속 촬영 배경의 태그를 기록한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            **{k: {"type": "string", "enum": v} for k, v in ENUMS.items()},
            "indoor": {"type": "boolean"},
            "visible_elements": {"type": "array", "items": {"type": "string", "enum": list(ELEMENT_LABELS)}},
            "people_prominent": {"type": "boolean", "description": "인물이 화면의 큰 비중을 차지하는가"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "uncertain_fields": {"type": "array", "items": {"type": "string", "enum": FIELDS}},
        },
        "required": FIELDS + ["indoor", "visible_elements", "people_prominent", "confidence", "uncertain_fields"],
    },
}

SYSTEM_PROMPT = """너는 사진 촬영 장소를 분류하는 전문가야. 사진 속 인물이 아니라 '배경 환경'을 판정해.

- time_of_day: 빛의 상태로 판단 (morning 오전, midday 낮, golden_hour 해 질 녘 낮고 따뜻한 햇빛, night 야간)
- lighting: diffused_natural 그늘·흐린 날·창으로 들어온 부드러운 자연광 / direct_golden 그림자가 뚜렷한 직사광이나 골든아워 햇빛 / warm_artificial 노란빛 실내·간접 조명 / cool_artificial_night 흰색·푸른색 인공조명이나 야경
- form: linear 직선·기하학적 구조 / curved 곡선·장식적 요소 / organic 비정형·자연 지형
- texture: sleek 대리석·유리·금속처럼 매끈함 / soft 패브릭·꽃·식물처럼 부드러움 / rough 원목·돌·벽돌·콘크리트처럼 거침 / none 뚜렷한 표면이 없음(하늘·수면 등)
- scale: 전신샷 기준 공간 여유 (compact 좁음, medium 보통, spacious 넓음)
- crowd_level: 보이는 사람 밀도. 사진은 한산할 때 찍는 경우가 많으니 확실할 때만 busy
- place_character: detail 음식·소품·장식 디테일이 매력 / concept 공간 전체의 컨셉·분위기가 매력
- photo_mood: structural 건축·구도 중심 / emotional 감성·분위기 중심
- visible_elements: 화면에 실제로 보이는 것만 (plants 식물, water 물, sunset_or_fire 노을·불빛, earth_or_clay 흙·도자기·황토, stone_or_metal 석조·금속)
- 판단이 어려운 항목은 uncertain_fields에 넣어."""


class VisionTagger(Protocol):
    def tag(self, img: Image.Image) -> dict: ...


def encode_image(img: Image.Image, max_side: int) -> tuple[str, str]:
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return "image/jpeg", base64.standard_b64encode(buf.getvalue()).decode()


def build_params(img: Image.Image, model: str, max_side: int) -> dict:
    media_type, data = encode_image(img, max_side)
    return {
        "model": model,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "tools": [TOOL],
        "tool_choice": {"type": "tool", "name": TOOL["name"]},
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
            {"type": "text", "text": "이 사진의 배경 태그를 기록해줘."},
        ]}],
    }


def parse_tool_output(content_blocks) -> dict | None:
    for block in content_blocks:
        btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if btype == "tool_use":
            raw = block.get("input") if isinstance(block, dict) else block.input
            return validate(raw)
    return None


def validate(raw: dict) -> dict:
    """허용되지 않은 값은 버리고 신뢰도를 낮춘다."""
    out, bad = {}, []
    for k, allowed in ENUMS.items():
        v = raw.get(k)
        if v in allowed:
            out[k] = v
        else:
            bad.append(k)
    out["indoor"] = bool(raw.get("indoor", False))
    out["people_prominent"] = bool(raw.get("people_prominent", False))
    out["visible_elements"] = [e for e in raw.get("visible_elements", []) if e in ELEMENT_LABELS]
    conf = float(raw.get("confidence", 0.5))
    out["confidence"] = max(0.0, min(1.0, conf)) * (0.7 if bad else 1.0)
    out["uncertain_fields"] = sorted(set(f for f in raw.get("uncertain_fields", []) if f in FIELDS) | set(bad))
    return out


def field_confidence(labels: dict, field: str) -> float:
    base = labels.get("confidence", 0.5)
    return base * (0.5 if field in labels.get("uncertain_fields", []) else 1.0)


class ClaudeVisionTagger:
    def __init__(self, model: str, max_side: int = 1024, client=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()          # ANTHROPIC_API_KEY 환경변수 사용
        self.client, self.model, self.max_side = client, model, max_side

    def tag(self, img: Image.Image) -> dict:
        resp = self.client.messages.create(**build_params(img, self.model, self.max_side))
        labels = parse_tool_output(resp.content)
        if labels is None:
            raise RuntimeError("비전 응답에 tool_use 블록이 없음")
        return labels


# ---------------------------------------------------------------------------
# 대량 처리: Message Batches API
# ---------------------------------------------------------------------------
def build_batch_requests(items: list[tuple[str, Image.Image]], model: str, max_side: int = 1024) -> list[dict]:
    """[(photo_id, 이미지)] → client.messages.batches.create(requests=...)에 넣을 목록."""
    return [{"custom_id": pid, "params": build_params(img, model, max_side)} for pid, img in items]


def parse_batch_results(results) -> dict[str, dict]:
    """client.messages.batches.results(batch_id) 결과 → {photo_id: labels}. 실패 건은 제외."""
    out = {}
    for r in results:
        if r.result.type == "succeeded":
            labels = parse_tool_output(r.result.message.content)
            if labels:
                out[r.custom_id] = labels
    return out
