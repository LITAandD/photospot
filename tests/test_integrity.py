"""사진 → 점수 정합성: 재현성, 근거 기준, 검수 확정."""
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline import integrity                                      # noqa: E402
from pipeline.aggregate import aggregate, analyze_photo              # noqa: E402
from pipeline.config import PipelineConfig                           # noqa: E402
from test_pipeline import GREEN_DAY, NIGHT, FakeTagger, _resized, img_greenhouse, img_night_city   # noqa: E402

DSN = os.environ.get("DATABASE_URL")
CFG = PipelineConfig()


def _photos():
    tagger = FakeTagger({320: GREEN_DAY, 321: {**GREEN_DAY, "form": "organic"}, 330: NIGHT})
    return [analyze_photo(f"p{i}", "spot", "tourapi", _resized(img_greenhouse() if w != 330 else img_night_city(), w), CFG, tagger=tagger)
            for i, w in enumerate([320, 320, 321, 320, 330, 330, 330])]


def test_same_photos_same_tags_regardless_of_order():
    photos = _photos()
    base = {(s.time_slot, s.season): (s.tags, s.tag_confidence, s.elements, s.confidence) for s in aggregate(photos, CFG)}
    for seed in range(5):
        shuffled = photos[:]
        random.Random(seed).shuffle(shuffled)
        again = {(s.time_slot, s.season): (s.tags, s.tag_confidence, s.elements, s.confidence) for s in aggregate(shuffled, CFG)}
        assert again == base


def test_reanalysis_is_deterministic():
    """같은 이미지를 두 번 분석하면 통계·태그·시간대가 완전히 같다."""
    tagger = FakeTagger({320: GREEN_DAY, 330: NIGHT})
    images = [_resized(img_greenhouse(), 320), _resized(img_night_city(), 330)]
    a = [analyze_photo(f"p{i}", "spot", "tourapi", im, CFG, tagger=tagger) for i, im in enumerate(images)]
    b = [analyze_photo(f"p{i}", "spot", "tourapi", im, CFG, tagger=tagger) for i, im in enumerate(images)]
    assert [(p.color_tags, p.stats.to_dict(), p.time_slot, p.palette_elements) for p in a] == \
           [(p.color_tags, p.stats.to_dict(), p.time_slot, p.palette_elements) for p in b]


@pytest.mark.skipif(not DSN, reason="DATABASE_URL 없음")
def test_evidence_gate_and_integrity_report():
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO places (name, category, sido, geom, status) VALUES ('정합성 테스트 ' || gen_random_uuid()::text, 'cafe', '서울특별시', ST_MakePoint(126.99, 37.58)::geography, 'active') RETURNING id::text""")
        pid = cur.fetchone()[0]
        cur.execute("INSERT INTO spots (place_id, name) VALUES (%s, '대표 지점') RETURNING id::text", (pid,))
        sid = cur.fetchone()[0]
        # 사진 근거지만 2장뿐 → 채점 제외
        cur.execute("""INSERT INTO scenes (spot_id, time_slot, season, color_temp, lighting, tag_source, evidence, confidence, photo_count)
                       VALUES (%s, 'midday', 'all', 'cool', 'diffused_natural', 'auto', 'photos', 0.9, 2) RETURNING id::text""", (sid,))
        few = cur.fetchone()[0]
        # 사진 5장인데 신뢰도 낮음 → 채점 제외
        cur.execute("""INSERT INTO scenes (spot_id, time_slot, season, color_temp, lighting, tag_source, evidence, confidence, photo_count)
                       VALUES (%s, 'night', 'all', 'cool', 'cool_artificial_night', 'auto', 'photos', 0.4, 5) RETURNING id::text""", (sid,))
        shaky = cur.fetchone()[0]
        conn.commit()
        cur.execute("SELECT scene_id::text, scorable FROM scene_integrity WHERE scene_id = ANY(%s::uuid[])", ([few, shaky],))
        assert dict(cur.fetchall()) == {few: False, shaky: False}
        # 사람이 확정하면 근거가 human 이 되어 항상 채점
        cur.execute("UPDATE scenes SET tag_source='verified', evidence='human', verified_at=now() WHERE id = %s", (few,)); conn.commit()
        cur.execute("SELECT scorable FROM scene_integrity WHERE scene_id = %s", (few,))
        assert cur.fetchone()[0] is True
        cur.execute("SELECT count(*) FROM score_scenes_in('a0000000-0000-0000-0000-000000000001', '2026-10-10', ARRAY[%s]::uuid[])", (pid,))
        assert cur.fetchone()[0] == 1                                          # 확정된 낮 장면만 채점

        rep = integrity.run(conn, CFG)
        assert rep.by_evidence.get("human", 0) >= 1 and rep.scorable >= 1
        assert any(b["scene_id"] == shaky for b in rep.below_threshold)
        assert rep.ok(), rep.drifted                                            # 저장된 분석 결과로 재집계해도 태그가 같다
