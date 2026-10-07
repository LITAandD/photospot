"""진짜 API로 작은 DB를 채우고 웹 테스트 준비까지 한 번에.

  docker compose run --rm tools python -m scripts.real_smoke --areas 1 --target 30
  (또는 로컬: DATABASE_URL, TOURAPI_KEY, [ANTHROPIC_API_KEY] 설정 후 python -m scripts.real_smoke)

단계
  1. TourAPI에서 장소 수집 (대표 사진 + 상세 사진 최대 8장)
  2. 사진 분석 작업을 여기서 바로 처리 (ANTHROPIC_API_KEY 있으면 AI 판정 포함)
  3. 정합성 리포트: 사진 근거 기준(3장·신뢰도 0.6)을 넘어 채점 가능한 장소 수
  4. 예시 사용자(여름쿨·웨이브)로 추천 미리보기
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

import psycopg

from pipeline.run import analyze
from pipeline import integrity
from pipeline.config import PipelineConfig
from pipeline.masking import get_masker
from pipeline.tourapi import LocalStorage
from pipeline.tourapi_bulk import bulk_import, summary
from pipeline.vision import ClaudeVisionTagger

CENTERS = {1: (37.5665, 126.9780), 6: (35.1796, 129.0756), 39: (33.4996, 126.5312), 2: (37.4563, 126.7052), 4: (35.8714, 128.6014)}


def main(argv=None, http_json=None, http_get=None, tagger=None, log=print) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", default="1", help="TourAPI 지역코드 (1 서울, 6 부산, 39 제주 …)")
    ap.add_argument("--types", default="12,14")
    ap.add_argument("--target", type=int, default=30)
    ap.add_argument("--vision", choices=["auto", "off"], default="auto")
    args = ap.parse_args(argv)

    dsn = os.environ.get("DATABASE_URL")
    key = os.environ.get("TOURAPI_KEY")
    if not dsn or (not key and http_json is None):
        log("DATABASE_URL 과 TOURAPI_KEY 환경변수가 필요해요 (.env 참고)"); return 2
    cfg = PipelineConfig()
    storage = LocalStorage(os.environ.get("STORAGE_ROOT", "./storage"))
    if tagger is None and args.vision == "auto" and os.environ.get("ANTHROPIC_API_KEY"):
        tagger = ClaudeVisionTagger(cfg.vision_model, cfg.vision_max_side)
    if tagger is None:
        log("※ ANTHROPIC_API_KEY 없음 → 색 분석만 합니다. 신뢰도가 0.8×(사진수/5)로 제한돼 사진 4장 이상 모인 장소만 채점됩니다.")

    with psycopg.connect(dsn) as conn:
        log(f"[1/4] TourAPI 수집: 지역 {args.areas}, 유형 {args.types}, 목표 {args.target}곳 (상세 사진 포함)")
        kwargs = {"detail_images": True}
        if http_json: kwargs["http_json"] = http_json; kwargs["http_json_bytes"] = lambda url: __import__("json").dumps(http_json(url)).encode()
        if http_get: kwargs["http_get"] = http_get
        stats = bulk_import(conn, key or "", [int(a) for a in args.areas.split(",")], [int(t) for t in args.types.split(",")],
                            storage, args.target, log=log, **kwargs)
        log("      " + summary(stats))
        for e in stats.errors[:3]:
            log("      오류: " + e)

        log("[2/4] 사진 분석 (방금 받은 사진을 여기서 바로 분석)")
        masker = get_masker(os.environ.get("PHOTO_MASKER", "none"))
        results = analyze(conn, storage, cfg, spot_id=None, tagger=tagger, masker=masker, log=lambda *_: None)
        updated = sum(1 for r in results if r["updated"])
        log(f"      장면 {len(results)}개 집계, {updated}개 갱신 (사진 {sum(r['photos'] for r in results)}장)")
        with conn.cursor() as cur:                   # 같은 스팟의 대기 작업은 처리된 것으로 정리
            cur.execute("UPDATE jobs SET status='done', finished_at=now() WHERE status='queued' AND kind='analyze_spot'")
        conn.commit()

        log("[3/4] 정합성 리포트")
        rep = integrity.run(conn, cfg)
        log("      " + rep.summary().replace("\n", "\n      "))
        with conn.cursor() as cur:
            cur.execute("SELECT count(DISTINCT sp.place_id) FROM scenes s JOIN spots sp ON sp.id = s.spot_id CROSS JOIN (SELECT * FROM score_settings WHERE is_active) cfg WHERE scene_scorable(s, cfg)")
            scorable_places = cur.fetchone()[0]
        log(f"      채점 가능한 장소: {scorable_places}곳")

        log("[4/4] 추천 미리보기 (여름쿨 라이트 · 웨이브 · INFP, 수 부족)")
        uid = str(uuid.uuid4())
        area0 = int(args.areas.split(",")[0])
        lat, lng = CENTERS.get(area0, CENTERS[1])
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (id) VALUES (%s)", (uid,))
            cur.execute("""INSERT INTO user_profiles (user_id, gender, height_cm, pc_season, pc_subtone, body_type, mbti)
                           VALUES (%s, 'female', 162, 'summer_cool', 'light', 'wave', 'INFP')""", (uid,))
            cur.execute("SELECT place_name, time_slot, total, distance_m FROM recommend_places_near(%s, current_date, %s, %s, 30000, 5)", (uid, lat, lng))
            rows = cur.fetchall()
            for name, slot, total, dist in rows:
                log(f"      {name} · {slot} · {total}점 · {dist/1000:.1f}km")
            if not rows:
                log("      (아직 없음 — 사진이 3장 이상 모인 장소가 없거나 신뢰도가 낮아요. --target을 늘리거나 ANTHROPIC_API_KEY를 넣어 다시 돌려보세요)")
            cur.execute("DELETE FROM users WHERE id = %s", (uid,))
        conn.commit()
    log("\n다음: app 폴더에서 `npx expo start --web` → 체험용 로그인 → 추천 목록 (서버 .env: DEV_LOGIN=1, CORS_ORIGINS=*)")
    return 0 if rep.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
