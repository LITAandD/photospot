"""사람이 확정한 장면(manual/verified)의 사진으로 색 기준값을 보정한다.

좌표 하강법: 기준값 하나씩 격자 탐색 → 정답 태그와 가장 많이 일치하는 값으로 교체, 몇 바퀴 반복.
결과는 제안값으로만 출력하고, 반영은 사람이 config.py에서 한다.
"""
from __future__ import annotations

from dataclasses import asdict, replace

import numpy as np

from . import color as C
from .config import ColorThresholds

GRIDS = {
    "warm_min":           ("color_temp", np.arange(4, 20.5, 0.5)),
    "cool_max":           ("color_temp", np.arange(-6, 8.5, 0.5)),
    "muted_c_max":        ("saturation", np.arange(6, 24.5, 0.5)),
    "vivid_c_min":        ("saturation", np.arange(24, 50.5, 0.5)),
    "bright_l_min":       ("brightness", np.arange(50, 80.5, 1.0)),
    "bright_std_max":     ("brightness", np.arange(12, 30.5, 0.5)),
    "contrast_std_min":   ("brightness", np.arange(18, 40.5, 0.5)),
    "contrast_range_min": ("brightness", np.arange(55, 95.5, 1.0)),
}
CLASSIFIERS = {"color_temp": C.classify_color_temp, "brightness": C.classify_brightness,
               "saturation": C.classify_saturation}


def accuracy(pairs, t: ColorThresholds, tag: str) -> float:
    rows = [(s, truth[tag]) for s, truth in pairs if truth.get(tag)]
    if not rows:
        return float("nan")
    return float(np.mean([CLASSIFIERS[tag](s, t) == y for s, y in rows]))


def _valid(t: ColorThresholds) -> bool:
    return t.cool_max < t.warm_min and t.muted_c_max < t.vivid_c_min


def calibrate(pairs, base: ColorThresholds = ColorThresholds(), rounds: int = 3):
    """pairs: [(ColorStats, {"color_temp":..., "brightness":..., "saturation":...})]"""
    t = base
    for _ in range(rounds):
        for name, (tag, grid) in GRIDS.items():
            cur = getattr(t, name)
            best_v, best_acc = cur, accuracy(pairs, t, tag)
            for v in grid:
                cand = replace(t, **{name: float(v)})
                if not _valid(cand):
                    continue
                acc = accuracy(pairs, cand, tag)
                # 정확도가 같으면 현재값에 가까운 쪽 (과적합 방지)
                if acc > best_acc + 1e-9 or (abs(acc - best_acc) < 1e-9 and abs(v - cur) < abs(best_v - cur)):
                    best_v, best_acc = float(v), acc
            t = replace(t, **{name: best_v})
    report = {tag: {"before": round(accuracy(pairs, base, tag), 3), "after": round(accuracy(pairs, t, tag), 3)}
              for tag in CLASSIFIERS}
    changed = {k: (getattr(base, k), v) for k, v in asdict(t).items() if v != getattr(base, k)}
    return t, report, changed


def load_pairs(conn):
    with conn.cursor() as cur:
        cur.execute("""SELECT p.labels->'stats', s.color_temp::text, s.brightness::text, s.saturation::text
                         FROM photos p JOIN scenes s ON s.id = p.scene_id
                        WHERE s.tag_source IN ('manual', 'verified') AND p.labels ? 'stats'""")
        return [(C.ColorStats(**st), {"color_temp": ct, "brightness": br, "saturation": sa})
                for st, ct, br, sa in cur.fetchall()]
