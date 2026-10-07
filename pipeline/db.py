"""DB 입출력. 사람이 입력·검수한 태그(manual/verified)는 절대 덮어쓰지 않는다."""
from __future__ import annotations

import re

from psycopg.types.json import Jsonb

from .aggregate import PhotoResult, SceneTags
from .color import ColorStats
from .config import SOURCE_WEIGHT

TAG_COLUMNS = ["color_temp", "brightness", "saturation", "lighting", "form", "texture", "scale",
               "crowd_level", "place_character", "photo_mood"]


def fetch_pending_photos(conn, spot_id: str | None = None, reanalyze: bool = False) -> list[dict]:
    sql = "SELECT id::text, spot_id::text, source::text, storage_path FROM photos WHERE TRUE"
    params = []
    if not reanalyze:
        sql += " AND analyzed_at IS NULL"
    if spot_id:
        sql += " AND spot_id = %s"
        params.append(spot_id)
    with conn.cursor() as cur:
        cur.execute(sql + " ORDER BY created_at", params)
        return [dict(zip(("id", "spot_id", "source", "storage_path"), r)) for r in cur.fetchall()]


def load_spot_results(conn, spot_id: str) -> list[PhotoResult]:
    """재집계용: 같은 스팟에서 이미 분석된 모든 사진의 판정을 복원 (새 사진만으로 태그가 흔들리지 않게)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT id::text, source::text, time_slot::text, season::text, labels
                         FROM photos
                        WHERE spot_id = %s AND analyzed_at IS NOT NULL AND labels IS NOT NULL""", (spot_id,))
        rows = cur.fetchall()
    with conn.cursor() as cur:
        cur.execute("""SELECT media_id, labels FROM external_media WHERE spot_id = %s""", (spot_id,))
        ext = cur.fetchall()
    out = []
    for mid, lb in ext:
        out.append(PhotoResult(photo_id=mid, spot_id=spot_id, weight=0.7, time_slot=lb["time_slot"], time_source=lb["time_source"],
                               season=lb["season"], stats=ColorStats(**lb["stats"]), color_tags=lb["color_tags"],
                               rule_lighting=tuple(lb["rule_lighting"]), palette_elements=set(lb["palette_elements"]), vision=lb["vision"]))
    for pid, source, slot, season, lb in rows:
        out.append(PhotoResult(
            photo_id=pid, spot_id=spot_id, weight=SOURCE_WEIGHT.get(source, 0.7),
            time_slot=slot, time_source=lb["time_source"], season=season,
            stats=ColorStats(**lb["stats"]), color_tags=lb["color_tags"],
            rule_lighting=tuple(lb["rule_lighting"]), palette_elements=set(lb["palette_elements"]),
            vision=lb["vision"]))
    return out


def save_photo(conn, r: PhotoResult) -> None:
    s = r.stats
    with conn.cursor() as cur:
        cur.execute("""UPDATE photos SET lab_l=%s, lab_c=%s, hue_deg=%s, l_stddev=%s, palette=%s,
                              time_slot=%s, season=%s, labels=%s, analyzed_at=now()
                        WHERE id=%s""",
                    (s.lab_l, s.lab_c, s.hue_deg, s.l_stddev, Jsonb(s.palette),
                     r.time_slot, r.season, Jsonb({**r.labels_json(), "stats": s.to_dict()}), r.photo_id))


def upsert_scene(conn, st: SceneTags) -> tuple[str, bool]:
    """장면 저장. 반환: (scene_id, 자동 태그를 실제로 갱신했는지)."""
    cols = ", ".join(TAG_COLUMNS)
    vals = ", ".join(["%s"] * len(TAG_COLUMNS))
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in TAG_COLUMNS)
    with conn.cursor() as cur:
        cur.execute(f"""
            INSERT INTO scenes (spot_id, time_slot, season, {cols}, tag_source, evidence, confidence,
                                tag_confidence, photo_count, review_reasons, tagged_at)
            VALUES (%s, %s, %s, {vals}, 'auto', 'photos', %s, %s, %s, %s, now())
            ON CONFLICT (spot_id, time_slot, season) DO UPDATE SET
                {updates}, evidence='photos', confidence=EXCLUDED.confidence, tag_confidence=EXCLUDED.tag_confidence,
                photo_count=EXCLUDED.photo_count, review_reasons=EXCLUDED.review_reasons, tagged_at=now()
            WHERE scenes.tag_source = 'auto'
            RETURNING id::text""",
            (st.spot_id, st.time_slot, st.season, *[st.tags.get(c) for c in TAG_COLUMNS],
             st.confidence, Jsonb(st.tag_confidence), len(st.photo_ids), st.reasons))
        row = cur.fetchone()
        updated = row is not None
        if not updated:   # 사람이 확정한 장면 → 태그는 그대로 두고 사진만 연결
            cur.execute("SELECT id::text FROM scenes WHERE spot_id=%s AND time_slot=%s AND season=%s",
                        (st.spot_id, st.time_slot, st.season))
            row = cur.fetchone()
        scene_id = row[0]
        if updated:
            cur.execute("DELETE FROM scene_elements WHERE scene_id=%s", (scene_id,))
            for e in st.elements:
                cur.execute("INSERT INTO scene_elements (scene_id, element) VALUES (%s, %s)", (scene_id, e))
        uuids = [pid for pid in st.photo_ids if re.fullmatch(r"[0-9a-f-]{36}", pid)]    # 외부 미디어 ID는 제외
        if uuids:
            cur.execute("UPDATE photos SET scene_id=%s WHERE id = ANY(%s::uuid[])", (scene_id, uuids))
    return scene_id, updated
