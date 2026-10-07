"""사진 → 색 통계(CIELAB) → 색온도·명도·채도 태그.

인물 픽셀은 마스크로 제외하고 배경만 분석한다.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
from PIL import Image, ImageOps
from sklearn.cluster import KMeans

from .config import ColorThresholds, PipelineConfig

_M_RGB2XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]])
_WHITE_D65 = np.array([0.95047, 1.0, 1.08883])


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB(0~1) → CIELAB(D65). shape (..., 3)."""
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = (lin @ _M_RGB2XYZ.T) / _WHITE_D65
    eps, k = 216 / 24389, 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (k * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def lab_to_hex(lab: np.ndarray) -> str:
    L, a, b = lab
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    eps, k = 216 / 24389, 24389 / 27
    xyz = np.array([fx ** 3 if fx ** 3 > eps else (116 * fx - 16) / k,
                    fy ** 3 if L > k * eps else L / k,
                    fz ** 3 if fz ** 3 > eps else (116 * fz - 16) / k]) * _WHITE_D65
    lin = np.linalg.solve(_M_RGB2XYZ, xyz)
    rgb = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.clip(lin, 0, None) ** (1 / 2.4) - 0.055)
    r, g, bb = (np.clip(rgb, 0, 1) * 255).round().astype(int)
    return f"#{r:02X}{g:02X}{bb:02X}"


@dataclass
class ColorStats:
    lab_l: float          # 평균 명도
    l_median: float
    l_stddev: float       # 명도 편차 → 대비
    l_range: float        # p95 - p5
    lab_c: float          # 보이는 픽셀 평균 채도
    hue_deg: float        # 평균 색상각
    cast_b: float         # 중성색 표면의 색 편향 (조명 색)
    warmth: float         # 최종 웜/쿨 지수
    background_ratio: float
    palette: list

    def to_dict(self) -> dict:
        return asdict(self)


def load_rgb(path_or_img, max_side: int) -> np.ndarray:
    img = path_or_img if isinstance(path_or_img, Image.Image) else Image.open(path_or_img)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    return np.asarray(img, dtype=np.float64) / 255.0


def _hue(lab: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360


def analyze_pixels(rgb: np.ndarray, background_mask: np.ndarray | None, cfg: PipelineConfig) -> ColorStats:
    lab = srgb_to_lab(rgb)
    if background_mask is None:
        background_mask = np.ones(lab.shape[:2], dtype=bool)
    bg_ratio = float(background_mask.mean())
    px = lab[background_mask] if background_mask.any() else lab.reshape(-1, 3)

    L, a, b = px[:, 0], px[:, 1], px[:, 2]
    C = np.hypot(a, b)
    H = _hue(px)

    visible = L > 25                                   # 까만 영역은 채도 계산에서 제외
    lab_c = float(C[visible].mean()) if visible.any() else float(C.mean())

    # 1) 조명 색: 중성에 가까운 밝은 표면(벽·바닥 등)의 색 편향
    neutral = (C < 20) & (L > 30)
    cast = float((b[neutral] + 0.3 * a[neutral]).mean()) if neutral.mean() > 0.05 else None
    # 2) 배경 색: 식물 초록(색상각 95~200°)은 웜·쿨 판단에서 제외
    non_foliage = ~((H >= 95) & (H < 200) & (C > 10))
    scene = float((b[non_foliage] + 0.3 * a[non_foliage]).mean()) if non_foliage.any() else 0.0
    warmth = scene if cast is None else 0.6 * cast + 0.4 * scene

    p5, p95 = np.percentile(L, [5, 95])
    return ColorStats(
        lab_l=round(float(L.mean()), 2), l_median=round(float(np.median(L)), 2),
        l_stddev=round(float(L.std()), 2), l_range=round(float(p95 - p5), 2),
        lab_c=round(lab_c, 2), hue_deg=round(float(_hue(px.mean(axis=0))), 2),
        cast_b=round(cast, 2) if cast is not None else None, warmth=round(warmth, 2),
        background_ratio=round(bg_ratio, 3), palette=extract_palette(px, cfg.palette_k),
    )


def extract_palette(px: np.ndarray, k: int, sample: int = 4000) -> list:
    rng = np.random.default_rng(0)
    if len(px) > sample:
        px = px[rng.choice(len(px), sample, replace=False)]
    k = min(k, len(np.unique(px.round(1), axis=0)))
    km = KMeans(n_clusters=k, n_init=3, random_state=0).fit(px)
    counts = np.bincount(km.labels_, minlength=k) / len(px)
    order = np.argsort(-counts)
    return [{"hex": lab_to_hex(km.cluster_centers_[i]),
             "ratio": round(float(counts[i]), 3),
             "lab": [round(float(v), 1) for v in km.cluster_centers_[i]]} for i in order]


# ---------------------------------------------------------------------------
# 통계 → 태그 (규칙 기반)
# ---------------------------------------------------------------------------
def classify_color_temp(s: ColorStats, t: ColorThresholds) -> str:
    if s.warmth >= t.warm_min:
        return "warm"
    if s.warmth <= t.cool_max:
        return "cool"
    return "neutral"


def classify_brightness(s: ColorStats, t: ColorThresholds) -> str:
    if s.l_stddev >= t.contrast_std_min or s.l_range >= t.contrast_range_min:
        return "high_contrast"
    if s.lab_l >= t.bright_l_min and s.l_stddev <= t.bright_std_max:
        return "bright_soft"
    return "mid"


def classify_saturation(s: ColorStats, t: ColorThresholds) -> str:
    if s.lab_c >= t.vivid_c_min:
        return "vivid"
    if s.lab_c <= t.muted_c_max:
        return "muted"
    return "mid"


def rule_lighting(s: ColorStats, t: ColorThresholds) -> tuple[str, float]:
    """색 통계만으로 추정한 조명 (AI 판정의 보조·교차검증용). (값, 신뢰도)"""
    if s.l_median <= t.night_l_median_max and s.l_range >= t.night_range_min:
        return ("warm_artificial" if s.warmth >= t.warm_min else "cool_artificial_night"), 0.6
    if s.warmth >= t.warm_min and s.l_stddev >= 24:
        return "direct_golden", 0.4
    return "diffused_natural", 0.3


def palette_elements(palette: list) -> set[str]:
    """주조색 비율로 추정한 오행 (약한 근거)."""
    share = {"wood": 0.0, "fire": 0.0, "earth": 0.0, "metal": 0.0, "water": 0.0}
    for p in palette:
        L, a, b = p["lab"]
        C, H = float(np.hypot(a, b)), float(np.degrees(np.arctan2(b, a)) % 360)
        if C < 8 and L > 55:
            share["metal"] += p["ratio"]
        elif (H < 55 or H > 340) and C > 25:
            share["fire"] += p["ratio"]
        elif 55 <= H < 95 and 8 <= C < 35 and 25 < L < 80:
            share["earth"] += p["ratio"]
        elif 95 <= H < 200 and C > 10:
            share["wood"] += p["ratio"]
        elif 200 <= H < 300 and C > 10:
            share["water"] += p["ratio"]
    minimum = {"wood": 0.25, "fire": 0.2, "earth": 0.3, "metal": 0.4, "water": 0.25}
    return {e for e, v in share.items() if v >= minimum[e]}
