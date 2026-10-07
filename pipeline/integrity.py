"""사진 → 점수 정합성 점검.

  python -m pipeline.run integrity

검사 항목
  1. 근거별 장면 수와 채점 가능 수 (category / photos / human)
  2. 재현성: 저장된 사진 분석 결과로 장면 태그를 다시 집계했을 때 DB의 태그와 같은지 (기준값·규칙이 바뀌면 여기서 드러남)
  3. 흔들리는 태그: 채점 가능 장면 중 태그 신뢰도 0.5 미만이 있는 장면
  4. 기준 미달: 사진 근거는 있지만 장수·신뢰도가 모자라 채점에서 빠진 장면 (사진을 더 모으면 됨)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .aggregate import aggregate
from .config import PipelineConfig
from .db import TAG_COLUMNS, load_spot_results


@dataclass
class Report:
    by_evidence: dict[str, int] = field(default_factory=dict)
    scorable: int = 0
    reaggregated: int = 0
    drifted: list[dict] = field(default_factory=list)       # 다시 집계하면 태그가 달라지는 장면
    shaky: list[dict] = field(default_factory=list)         # 태그 신뢰도 0.5 미만
    below_threshold: list[dict] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.drifted

    def summary(self) -> str:
        lines = [f"근거별 장면: {self.by_evidence} · 채점 가능 {self.scorable}",
                 f"재집계 {self.reaggregated}개 중 태그가 달라진 장면 {len(self.drifted)}개" + (" ← 기준값/규칙 변경 후 재분석 필요" if self.drifted else " (재현성 OK)"),
                 f"흔들리는 태그가 있는 채점 장면 {len(self.shaky)}개, 사진 기준 미달 장면 {len(self.below_threshold)}개"]
        return "\n".join(lines)


def run(conn, cfg: PipelineConfig = PipelineConfig(), sample: int | None = None) -> Report:
    rep = Report()
    with conn.cursor() as cur:
        cur.execute("SELECT evidence::text, count(*), count(*) FILTER (WHERE scorable) FROM scene_integrity GROUP BY 1")
        for ev, n, sc in cur.fetchall():
            rep.by_evidence[ev] = n
            rep.scorable += sc
        cur.execute("""SELECT scene_id::text, place_name, spot_name, time_slot::text, tag_confidence
                         FROM scene_integrity WHERE scorable AND tag_confidence IS NOT NULL""")
        for sid, place, spot, slot, tc in cur.fetchall():
            weak = {k: v for k, v in (tc or {}).items() if v is not None and v < 0.5}
            if weak:
                rep.shaky.append({"scene_id": sid, "place": place, "spot": spot, "time_slot": slot, "weak_tags": weak})
        cur.execute("""SELECT scene_id::text, place_name, photo_count, confidence::float, review_reasons
                         FROM scene_integrity WHERE evidence = 'photos' AND NOT scorable""")
        rep.below_threshold = [{"scene_id": r[0], "place": r[1], "photo_count": r[2], "confidence": r[3], "reasons": r[4]} for r in cur.fetchall()]

        # 재현성: 사진 근거 장면을 저장된 분석 결과로 다시 집계
        cur.execute(f"""SELECT s.spot_id::text, s.time_slot::text, s.season::text, {", ".join("s." + c + "::text" for c in TAG_COLUMNS)},
                               p.name FROM scenes s JOIN spots sp ON sp.id = s.spot_id JOIN places p ON p.id = sp.place_id
                         WHERE s.evidence = 'photos' AND s.tag_source = 'auto' ORDER BY s.tagged_at DESC {"LIMIT %s" if sample else ""}""",
                    (sample,) if sample else ())
        rows = cur.fetchall()
    seen_spots: dict[str, dict] = {}
    for row in rows:
        spot_id, slot, season, *tags, place = row
        stored = dict(zip(TAG_COLUMNS, tags))
        if spot_id not in seen_spots:
            results = load_spot_results(conn, spot_id)
            seen_spots[spot_id] = {(st.time_slot, st.season): st for st in aggregate(results, cfg)} if results else {}
        fresh = seen_spots[spot_id].get((slot, season))
        if fresh is None:
            continue
        rep.reaggregated += 1
        diff = {c: (stored[c], fresh.tags.get(c)) for c in TAG_COLUMNS if (stored[c] or None) != (fresh.tags.get(c) or None)}
        if diff:
            rep.drifted.append({"place": place, "time_slot": slot, "season": season, "diff": diff})
    return rep
