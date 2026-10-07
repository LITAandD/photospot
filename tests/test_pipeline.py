"""파이프라인 테스트: 합성 이미지 + 가짜 AI 응답 + 실제 PostgreSQL.

실행: DATABASE_URL=... python -m pytest tests -q   (DB 테스트는 DATABASE_URL 없으면 건너뜀)
"""
import os
import sys
import tempfile
from datetime import datetime

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline import color as C                                   # noqa: E402
from pipeline.aggregate import aggregate, analyze_photo           # noqa: E402
from pipeline.config import PipelineConfig                        # noqa: E402
from pipeline.timeslot import exif_datetime, slot_from_datetime   # noqa: E402
from pipeline.tourapi import usable_images                        # noqa: E402
from pipeline.vision import parse_tool_output, validate           # noqa: E402

CFG = PipelineConfig()
RNG = np.random.default_rng(42)


# ---------------------------------------------------------------------------
# 합성 이미지
# ---------------------------------------------------------------------------
def _noise(arr, s=4):
    return np.clip(arr + RNG.normal(0, s, arr.shape), 0, 255).astype(np.uint8)


def img_gallery():            # 밝은 흰 벽, 약간 푸른 기, 연회색 바닥
    a = np.zeros((240, 320, 3)); a[:] = (232, 237, 246); a[180:] = (205, 209, 216)
    return Image.fromarray(_noise(a))


def img_golden_field():       # 노을 하늘 + 황금빛 들판 + 어두운 실루엣
    a = np.zeros((240, 320, 3))
    for y in range(240):
        t = y / 239
        a[y] = (1 - t) * np.array([250, 185, 115]) + t * np.array([195, 150, 80])
    a[150:175, 40:90] = (60, 42, 28); a[120:240, 250:275] = (55, 40, 25)
    return Image.fromarray(_noise(a))


def img_night_city():         # 까만 배경 + 네온·흰 조명
    a = np.zeros((240, 320, 3)); a[:] = (12, 14, 24)
    a[30:70, 20:90] = (40, 120, 255); a[100:130, 150:260] = (230, 40, 200)
    a[180:200, 40:300] = (245, 248, 255); a[20:40, 200:300] = (250, 252, 255)
    return Image.fromarray(_noise(a, 3))


def img_brick_cafe():         # 붉은 벽돌 + 줄눈
    a = np.zeros((240, 320, 3)); a[:] = (156, 86, 64)
    a[::20] = (205, 192, 172); a[:, ::45] = (205, 192, 172)
    return Image.fromarray(_noise(a))


def img_greenhouse():         # 식물 초록 + 흰 프레임 + 밝은 하늘
    a = np.zeros((240, 320, 3)); a[:] = (225, 234, 244)
    a[90:] = (78, 140, 72); a[150:, ::2] = (112, 168, 92)
    a[:, ::40] = (242, 243, 241); a[::60] = (242, 243, 241)
    return Image.fromarray(_noise(a))


def with_exif(img, dt: str):
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = dt
    buf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    img.save(buf.name, exif=exif.tobytes(), quality=92)
    return Image.open(buf.name)


def tags_of(img, mask=None):
    rgb = C.load_rgb(img, 384)
    s = C.analyze_pixels(rgb, mask, CFG)
    t = CFG.colors
    return s, (C.classify_color_temp(s, t), C.classify_brightness(s, t), C.classify_saturation(s, t))


# ---------------------------------------------------------------------------
# 1. 색 분석
# ---------------------------------------------------------------------------
def test_lab_matches_skimage():
    skc = pytest.importorskip("skimage.color")
    rgb = RNG.random((50, 3))
    assert np.allclose(C.srgb_to_lab(rgb), skc.rgb2lab(rgb[None])[0], atol=0.05)


def test_hex_roundtrip():
    assert C.lab_to_hex(C.srgb_to_lab(np.array([156, 86, 64]) / 255)) == "#9C5640"


@pytest.mark.parametrize("make, expected", [
    (img_gallery,      ("cool", "bright_soft", "muted")),
    (img_night_city,   ("cool", "high_contrast", None)),
    (img_brick_cafe,   ("warm", None, "mid")),
    (img_golden_field, ("warm", None, None)),
])
def test_color_classification(make, expected):
    _, got = tags_of(make())
    for g, e in zip(got, expected):
        if e is not None:
            assert g == e, f"{make.__name__}: {got}"


def test_foliage_not_counted_as_warm():
    s, (temp, _, _) = tags_of(img_greenhouse())
    assert temp != "warm", s
    assert "wood" in C.palette_elements(s.palette)


def test_night_rule_lighting():
    s, _ = tags_of(img_night_city())
    assert C.rule_lighting(s, CFG.colors)[0] == "cool_artificial_night"


def test_person_mask_changes_result():
    """차가운 배경 + 빨간 옷 인물. 웜/쿨은 중성 표면 기준이라 버티지만, 채도는 옷 때문에 부풀려진다."""
    a = np.zeros((240, 320, 3)); a[:] = (200, 215, 235); a[20:240, 90:230] = (210, 40, 40)
    img = Image.fromarray(_noise(a))
    s0, (temp0, _, sat0) = tags_of(img)
    mask = np.ones((240, 320), bool); mask[20:240, 90:230] = False
    s1, (temp1, _, sat1) = tags_of(img, mask)
    assert temp0 == temp1 == "cool"                  # 조명 색 기반 판정은 인물에 강함
    assert sat0 != "muted" and sat1 == "muted"       # 채도는 마스킹이 필요
    assert s1.warmth < s0.warmth


# ---------------------------------------------------------------------------
# 2. 시간대
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("dt, slot", [
    ("2026-10-10 17:30", "golden_hour"), ("2026-10-10 21:00", "night"),
    ("2026-10-10 09:00", "morning"), ("2026-10-10 13:00", "midday"),
    ("2026-06-20 19:30", "golden_hour"), ("2026-12-20 17:50", "night"),
])
def test_slot_from_datetime(dt, slot):
    assert slot_from_datetime(datetime.strptime(dt, "%Y-%m-%d %H:%M")) == slot


def test_exif_read():
    img = with_exif(img_golden_field(), "2026:10:10 17:30:00")
    assert exif_datetime(img) == datetime(2026, 10, 10, 17, 30)


# ---------------------------------------------------------------------------
# 3. AI 응답 검증 · TourAPI 파싱
# ---------------------------------------------------------------------------
def test_validate_drops_bad_enum():
    out = validate({"lighting": "moonlight", "form": "curved", "confidence": 0.9, "visible_elements": ["water", "x"]})
    assert "lighting" not in out and out["form"] == "curved"
    assert "lighting" in out["uncertain_fields"] and out["confidence"] < 0.9
    assert out["visible_elements"] == ["water"]


def test_parse_tool_output():
    blocks = [{"type": "text", "text": "..."}, {"type": "tool_use", "input": {"form": "linear", "confidence": 0.8}}]
    assert parse_tool_output(blocks)["form"] == "linear"


def test_tourapi_license_filter():
    raw = {"response": {"body": {"items": {"item": [
        {"originimgurl": "http://tong.visitkorea.or.kr/a.jpg", "cpyrhtDivCd": "Type1", "serialnum": "1"},
        {"originimgurl": "http://tong.visitkorea.or.kr/b.jpg", "cpyrhtDivCd": "Type3", "serialnum": "2"},
        {"originimgurl": "http://tong.visitkorea.or.kr/c.jpg", "cpyrhtDivCd": "Type2", "serialnum": "3"},
        {"originimgurl": "http://tong.visitkorea.or.kr/d.jpg", "cpyrhtDivCd": None, "serialnum": "4"},
    ]}}}}
    got = usable_images(raw, "126508")
    assert [g["license"] for g in got] == ["kogl_type1", "kogl_type3"]
    assert usable_images({"response": {"body": {"items": ""}}}, "1") == []


# ---------------------------------------------------------------------------
# 4. 장면 집계
# ---------------------------------------------------------------------------
class FakeTagger:
    """이미지 크기(가로 px)로 사진을 구분해 정해진 판정을 돌려주는 가짜 AI."""
    def __init__(self, by_width):
        self.by_width = by_width

    def tag(self, img):
        return validate(self.by_width[img.width])


GREEN_DAY = {"time_of_day": "midday", "lighting": "diffused_natural", "form": "curved", "texture": "soft",
             "scale": "medium", "crowd_level": "quiet", "place_character": "concept", "photo_mood": "emotional",
             "seasonal_feature": "none", "indoor": True, "visible_elements": ["plants"],
             "people_prominent": False, "confidence": 0.85, "uncertain_fields": []}
NIGHT = {**GREEN_DAY, "time_of_day": "night", "lighting": "cool_artificial_night", "form": "linear",
         "texture": "sleek", "scale": "spacious", "visible_elements": ["water"], "photo_mood": "structural"}


def _resized(img, w):
    return img.resize((w, 240))


def test_aggregate_groups_and_confidence():
    tagger = FakeTagger({320: GREEN_DAY, 321: {**GREEN_DAY, "form": "organic"}, 330: NIGHT})
    photos = [analyze_photo(f"p{i}", "spot", "tourapi", _resized(img_greenhouse(), w), CFG, tagger=tagger)
              for i, w in enumerate([320, 320, 320, 321, 330, 330])]
    scenes = {s.time_slot: s for s in aggregate(photos, CFG)}
    assert set(scenes) == {"midday", "night"}
    day = scenes["midday"]
    assert day.tags["form"] == "curved" and day.tag_confidence["form"] == 0.75   # 4장 중 3장 일치
    assert "wood" in day.elements and len(day.photo_ids) == 4
    assert scenes["night"].tags["lighting"] == "cool_artificial_night"
    assert scenes["night"].needs_review            # 사진 2장뿐


def test_seasonal_feature_splits_scene():
    autumn = {**GREEN_DAY, "seasonal_feature": "autumn_leaves"}
    tagger = FakeTagger({320: GREEN_DAY, 322: autumn})
    photos = [analyze_photo("a", "s", "tourapi", _resized(img_greenhouse(), 320), CFG, tagger=tagger),
              analyze_photo("b", "s", "tourapi", _resized(img_greenhouse(), 322), CFG, tagger=tagger)]
    assert {(s.time_slot, s.season) for s in aggregate(photos, CFG)} == {("midday", "all"), ("midday", "autumn")}


def test_without_vision_flags_review():
    photos = [analyze_photo("x", "s", "tourapi", img_gallery(), CFG, tagger=None)]
    st = aggregate(photos, CFG)[0]
    assert st.tags["form"] is None and st.needs_review
    assert any("AI 판정 없음" in r for r in st.reasons)


# ---------------------------------------------------------------------------
# 5. DB 통합 (schema.sql + seed_example.sql + 002_pipeline.sql 적용된 DB)
# ---------------------------------------------------------------------------
DSN = os.environ.get("DATABASE_URL")
db = pytest.mark.skipif(not DSN, reason="DATABASE_URL 없음")


@db
def test_db_end_to_end(tmp_path):
    import psycopg
    from pipeline.run import analyze
    from pipeline.tourapi import LocalStorage

    storage = LocalStorage(str(tmp_path))
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO places (name, category, sido, sigungu, geom, status)
                       VALUES ('테스트 온실 카페', 'cafe', '서울특별시', '성동구',
                               ST_MakePoint(127.04, 37.545)::geography, 'active') RETURNING id::text""")
        place_id = cur.fetchone()[0]
        cur.execute("INSERT INTO spots (place_id, name) VALUES (%s, '온실 창가') RETURNING id::text", (place_id,))
        spot_id = cur.fetchone()[0]
        widths = [320, 320, 320, 320, 320, 330, 330]
        for i, w in enumerate(widths):
            path = storage.save(f"t/{i}.jpg", b"")
            _resized(img_greenhouse() if w == 320 else img_night_city(), w).save(storage.open_path(path))
            cur.execute("""INSERT INTO photos (spot_id, source, license, storage_path)
                           VALUES (%s, 'own_shoot', 'own', %s)""", (spot_id, path))
        # 사람이 확정한 장면(창경궁 대온실 낮)에 새 사진 추가 → 태그가 바뀌면 안 됨
        manual_spot = "20000000-0000-0000-0000-000000000002"
        cur.execute("SELECT form, lighting FROM scenes WHERE spot_id=%s AND time_slot='midday'", (manual_spot,))
        before = cur.fetchone()
        path = storage.save("t/manual.jpg", b"")
        img_night_city().resize((320, 240)).save(storage.open_path(path))
        cur.execute("""INSERT INTO photos (spot_id, source, license, storage_path)
                       VALUES (%s, 'own_shoot', 'own', %s)""", (manual_spot, path))
        conn.commit()

        tagger = FakeTagger({320: GREEN_DAY, 330: NIGHT})
        summary = analyze(conn, storage, CFG, tagger=tagger, log=lambda *_: None)

        mine = {s["time_slot"]: s for s in summary if s["spot_id"] == spot_id}
        assert set(mine) == {"midday", "night"} and all(s["updated"] for s in mine.values())
        assert mine["midday"]["photos"] == 5 and not mine["midday"]["needs_review"]

        cur.execute("SELECT form, lighting FROM scenes WHERE spot_id=%s AND time_slot='midday'", (manual_spot,))
        assert cur.fetchone() == before                                    # 수동 태그 보존
        manual = [s for s in summary if s["spot_id"] == manual_spot][0]
        assert manual["updated"] is False

        cur.execute("SELECT count(*) FROM scene_review_queue q JOIN scenes s ON s.id = q.scene_id WHERE s.spot_id=%s", (spot_id,))
        assert cur.fetchone()[0] == 1                                      # 야간 장면(사진 2장)만 검수 대기

        cur.execute("""SELECT place_name, time_slot, total FROM score_scenes(
                         'a0000000-0000-0000-0000-000000000001', '2026-10-10')
                       WHERE place_name = '테스트 온실 카페' ORDER BY total DESC""")
        rows = cur.fetchall()
        assert rows and rows[0][1] == "midday"                             # 새 장면이 바로 추천 대상


# ---------------------------------------------------------------------------
# 6. 기준값 보정
# ---------------------------------------------------------------------------
def test_calibrate_recovers_thresholds():
    from dataclasses import replace
    from pipeline.calibrate import calibrate
    from pipeline.config import ColorThresholds

    truth_t = replace(ColorThresholds(), warm_min=7.0, vivid_c_min=31.0)   # '실제 사람 기준'
    rng = np.random.default_rng(1)
    pairs = []
    for _ in range(300):
        s = C.ColorStats(lab_l=rng.uniform(20, 95), l_median=50, l_stddev=rng.uniform(3, 35),
                         l_range=rng.uniform(10, 95), lab_c=rng.uniform(3, 50), hue_deg=0, cast_b=None,
                         warmth=rng.uniform(-10, 25), background_ratio=1.0, palette=[])
        pairs.append((s, {"color_temp": C.classify_color_temp(s, truth_t),
                          "brightness": C.classify_brightness(s, truth_t),
                          "saturation": C.classify_saturation(s, truth_t)}))
    t, report, changed = calibrate(pairs)
    assert report["color_temp"]["after"] > report["color_temp"]["before"]
    assert report["saturation"]["after"] >= 0.98
    assert abs(t.warm_min - 7.0) <= 1.0 and abs(t.vivid_c_min - 31.0) <= 1.0
