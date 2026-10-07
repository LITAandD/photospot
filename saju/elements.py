"""사주 오행 분포 계산.

포스텔러 만세력의 "조후·궁성 보정"과 같은 가중치를 쓴다 (공개 역산 자료로 소수점까지 검증된 규칙):
  - 글자마다 본기(대표 오행)만 센다 (지장간은 세지 않음)
  - 궁성 보정: 천간 각 2, 월지 7, 일지 3, 년지·시지 각 2 (합계 22, 시간 모르면 18)
  - 조후 보정(월지만): 未→전부 火, 丑→전부 水, 戌→7 중 4가 水, 辰→7 중 4가 木

합충 보정은 포스텔러의 내부 규칙이 공개돼 있지 않아 표준 명리 규칙으로 구현했다 (동일함은 미검증):
  - 천간합·지지육합(인접)·삼합·방합(세 글자 모두)은 합화 오행으로 전환
  - 인접 충은 두 글자 모두 절반으로 감소, 합에 참여한 글자는 충을 받지 않음
  - 합충을 먼저 적용하고, 월지가 합으로 바뀌지 않았을 때만 조후 보정을 적용
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .pillars import FourPillars

ELEMENTS = ["wood", "fire", "earth", "metal", "water"]
STEM_ELEMENT = ["wood", "wood", "fire", "fire", "earth", "earth", "metal", "metal", "water", "water"]
BRANCH_ELEMENT = ["water", "earth", "wood", "wood", "earth", "fire", "fire", "earth", "metal", "metal", "earth", "water"]

POSITION_WEIGHT = {"year_stem": 2, "year_branch": 2, "month_stem": 2, "month_branch": 7,
                   "day_stem": 2, "day_branch": 3, "hour_stem": 2, "hour_branch": 2}

STEM_COMBINE = {frozenset({0, 5}): "earth", frozenset({1, 6}): "metal", frozenset({2, 7}): "water",
                frozenset({3, 8}): "wood", frozenset({4, 9}): "fire"}
STEM_CLASH = {frozenset({0, 6}), frozenset({1, 7}), frozenset({2, 8}), frozenset({3, 9})}
BRANCH_SIX_COMBINE = {frozenset({0, 1}): "earth", frozenset({2, 11}): "wood", frozenset({3, 10}): "fire",
                      frozenset({4, 9}): "metal", frozenset({5, 8}): "water", frozenset({6, 7}): "fire"}
BRANCH_TRIADS = {frozenset({8, 0, 4}): "water", frozenset({2, 6, 10}): "fire",       # 삼합
                 frozenset({5, 9, 1}): "metal", frozenset({11, 3, 7}): "wood",
                 frozenset({2, 3, 4}): "wood", frozenset({5, 6, 7}): "fire",          # 방합
                 frozenset({8, 9, 10}): "metal", frozenset({11, 0, 1}): "water"}
BRANCH_CLASH = {frozenset({0, 6}), frozenset({1, 7}), frozenset({2, 8}), frozenset({3, 9}),
                frozenset({4, 10}), frozenset({5, 11})}
CLIMATE = {7: {"fire": 1.0}, 1: {"water": 1.0}, 10: {"water": 4 / 7, "earth": 3 / 7}, 4: {"wood": 4 / 7, "earth": 3 / 7}}

STEM_ORDER = ["year_stem", "month_stem", "day_stem", "hour_stem"]
BRANCH_ORDER = ["year_branch", "month_branch", "day_branch", "hour_branch"]


@dataclass
class ElementResult:
    scores: dict[str, float]       # 가중치 합 (최대 22)
    percents: dict[str, float]     # 0~100
    dominant: str                  # 가장 많은 오행 하나
    corrections: list[str] = field(default_factory=list)


def _chars(p: FourPillars) -> tuple[dict[str, int], dict[str, int]]:
    stems = {"year_stem": p.year.stem, "month_stem": p.month.stem, "day_stem": p.day.stem}
    branches = {"year_branch": p.year.branch, "month_branch": p.month.branch, "day_branch": p.day.branch}
    if p.hour:
        stems["hour_stem"], branches["hour_branch"] = p.hour.stem, p.hour.branch
    return stems, branches


def _adjacent(order: list[str], present: dict) -> list[tuple[str, str]]:
    keys = [k for k in order if k in present]
    return list(zip(keys, keys[1:]))


def weigh(p: FourPillars, harmony: bool = True, climate: bool = True) -> ElementResult:
    stems, branches = _chars(p)
    # 각 자리의 오행 분포 {element: 비율}, 자리 가중치는 마지막에 곱한다
    dist = {k: {STEM_ELEMENT[v]: 1.0} for k, v in stems.items()}
    dist.update({k: {BRANCH_ELEMENT[v]: 1.0} for k, v in branches.items()})
    factor = {k: 1.0 for k in dist}
    combined: set[str] = set()
    notes: list[str] = []

    if harmony:
        # 천간합 (인접)
        for a, b in _adjacent(STEM_ORDER, stems):
            el = STEM_COMBINE.get(frozenset({stems[a], stems[b]}))
            if el:
                dist[a], dist[b] = {el: 1.0}, {el: 1.0}
                combined |= {a, b}
                notes.append(f"천간합 {a}·{b} → {el}")
        # 삼합·방합 (세 글자가 모두 있을 때, 자리 무관)
        for triad, el in BRANCH_TRIADS.items():
            keys = [k for k, v in branches.items() if v in triad]
            if {branches[k] for k in keys} == triad:
                for k in keys:
                    dist[k] = {el: 1.0}
                combined |= set(keys)
                notes.append(f"삼합·방합 {'·'.join(keys)} → {el}")
        # 육합 (인접, 아직 합에 안 쓰인 글자만)
        for a, b in _adjacent(BRANCH_ORDER, branches):
            el = BRANCH_SIX_COMBINE.get(frozenset({branches[a], branches[b]}))
            if el and a not in combined and b not in combined:
                dist[a], dist[b] = {el: 1.0}, {el: 1.0}
                combined |= {a, b}
                notes.append(f"육합 {a}·{b} → {el}")
        # 충 (인접, 합에 참여한 글자는 제외)
        for order, chars, table, label in ((STEM_ORDER, stems, STEM_CLASH, "천간충"), (BRANCH_ORDER, branches, BRANCH_CLASH, "지지충")):
            for a, b in _adjacent(order, chars):
                if frozenset({chars[a], chars[b]}) in table and a not in combined and b not in combined:
                    factor[a] *= 0.5
                    factor[b] *= 0.5
                    notes.append(f"{label} {a}·{b} 반감")

    if climate and "month_branch" not in combined:
        rule = CLIMATE.get(branches["month_branch"])
        if rule:
            dist["month_branch"] = dict(rule)
            notes.append("조후 보정 월지 " + ", ".join(f"{e} {round(r, 2)}" for e, r in rule.items()))

    scores = {e: 0.0 for e in ELEMENTS}
    for k, d in dist.items():
        for el, ratio in d.items():
            scores[el] += POSITION_WEIGHT[k] * ratio * factor[k]
    total = sum(scores.values())
    percents = {e: round(scores[e] / total * 100, 1) for e in ELEMENTS}
    day_el = STEM_ELEMENT[p.day.stem]
    dominant = max(ELEMENTS, key=lambda e: (round(scores[e], 6), e == day_el, -ELEMENTS.index(e)))
    return ElementResult({e: round(v, 3) for e, v in scores.items()}, percents, dominant, notes)
