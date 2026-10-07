"""실행 진입점.

  # 0) TourAPI 전국 목록으로 장소 일괄 수집 (초기 태그 + 대표 사진 + 분석 작업)
  python -m pipeline.run import-tourapi-bulk --areas 1,6,39 --types 12,14 --target 500
  # 1) TourAPI 사진 등록
  python -m pipeline.run import-tourapi --spot <spot_id> --content-id 126508
  # 2) 미분석 사진 분석 → 장면 태그 생성
  python -m pipeline.run analyze [--spot <spot_id>] [--vision claude|off] [--mask none|rembg]
  # 3) 검수 완료 장면으로 색 기준값 보정 제안
  python -m pipeline.run calibrate

환경변수: DATABASE_URL, STORAGE_ROOT, ANTHROPIC_API_KEY, TOURAPI_KEY
"""
from __future__ import annotations

import argparse
import os

import psycopg
from PIL import Image

from .aggregate import aggregate, analyze_photo
from .calibrate import calibrate, load_pairs
from .config import PipelineConfig
from .db import fetch_pending_photos, load_spot_results, save_photo, upsert_scene
from .masking import get_masker
from .tourapi import LocalStorage, fetch_detail_images, register_images
from .tourapi_bulk import bulk_import, summary
from .naver_local import NaverLocalClient, harvest
from .instagram import InstagramClient, enrich_cafes
from . import integrity
from .vision import ClaudeVisionTagger


def analyze(conn, storage: LocalStorage, cfg: PipelineConfig, spot_id=None, tagger=None, masker=None,
            reanalyze=False, log=print) -> list[dict]:
    # Explicit spot jobs also run after a deletion, when no new photo is pending.
    touched = {str(spot_id)} if spot_id else set()
    for ph in fetch_pending_photos(conn, spot_id, reanalyze):
        try:
            with Image.open(storage.open_path(ph["storage_path"])) as img:
                img.load()
                r = analyze_photo(ph["id"], ph["spot_id"], ph["source"], img, cfg, masker, tagger)
        except Exception as e:                      # 한 장 실패가 전체를 멈추지 않게
            conn.rollback()
            log(f"[skip] {ph['id']}: {e}")
            continue
        save_photo(conn, r)
        conn.commit()
        touched.add(ph["spot_id"])

    summary = []
    for sid in touched:
        groups = aggregate(load_spot_results(conn, sid), cfg)
        # Invalidate old automatic evidence before rebuilding it from surviving photos.
        # Human-reviewed scenes remain intact; records stay to preserve recommendation history.
        with conn.cursor() as cur:
            cur.execute("""UPDATE scenes SET evidence='category', photo_count=0, confidence=0,
                                  review_reasons=ARRAY['사진 근거 재집계 필요']
                            WHERE spot_id=%s AND tag_source='auto' AND evidence='photos'""", (sid,))
        for st in groups:
            scene_id, updated = upsert_scene(conn, st)
            summary.append({"scene_id": scene_id, "spot_id": sid, "time_slot": st.time_slot,
                            "season": st.season, "updated": updated, "confidence": st.confidence,
                            "photos": len(st.photo_ids), "needs_review": st.needs_review,
                            "tags": st.tags, "elements": st.elements, "reasons": st.reasons})
    conn.commit()
    return summary


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--spot")
    a.add_argument("--vision", choices=["claude", "off"], default="claude")
    a.add_argument("--mask", choices=["none", "rembg"], default="none")
    a.add_argument("--reanalyze", action="store_true")
    sub.add_parser("calibrate")
    ig2 = sub.add_parser("integrity", help="사진 → 점수 정합성 점검 (근거별 수, 재현성, 흔들리는 태그)")
    ig2.add_argument("--sample", type=int, default=None, help="재집계할 장면 수 제한")
    ig2.add_argument("--json", action="store_true")
    bk = sub.add_parser("import-tourapi-bulk", help="지역×유형 목록으로 장소 일괄 수집")
    bk.add_argument("--areas", default="1,2,3,4,5,6,7,8,31,32,33,34,35,36,37,38,39", help="TourAPI 지역코드 (쉼표)")
    bk.add_argument("--types", default="12,14", help="콘텐츠 유형: 12 관광지, 14 문화시설, 39 음식점(카페 포함)")
    bk.add_argument("--target", type=int, default=500, help="새로 추가할 장소 수")
    bk.add_argument("--no-images", action="store_true", help="사진 내려받기·분석 작업 생략 (빠른 시드)")
    bk.add_argument("--detail-images", action="store_true", help="장소별 상세 사진(최대 8장)까지 받기 — 채점 기준(3장)을 넘기려면 필요")
    nv = sub.add_parser("harvest-naver-cafes", help="네이버 지역 검색으로 카페 목록 수집 (동네 × 테마)")
    nv.add_argument("--areas", required=True, help="동네 이름 (쉼표): 성수동,연남동,을지로,해운대,애월")
    nv.add_argument("--themes", default=None, help="테마 (쉼표). 기본: 한옥,플라워,화이트,미니멀,빈티지,루프탑,오션뷰,정원,베이커리,감성,뷰,일반")
    nv.add_argument("--target", type=int, default=300)
    ig = sub.add_parser("enrich-instagram", help="사진 없는 카페에 인스타 게시물 분석·인기 신호 채우기")
    ig.add_argument("--limit", type=int, default=30, help="이번 실행에서 처리할 카페 수 (해시태그 예산 7일 30개)")
    ig.add_argument("--vision", choices=["claude", "off"], default="claude")
    t = sub.add_parser("import-tourapi")
    t.add_argument("--spot", required=True)
    t.add_argument("--content-id", required=True)
    args = ap.parse_args()

    cfg = PipelineConfig()
    storage = LocalStorage(os.environ.get("STORAGE_ROOT", "./storage"))
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        if args.cmd == "harvest-naver-cafes":
            client = NaverLocalClient(os.environ["NAVER_CLIENT_ID"], os.environ["NAVER_CLIENT_SECRET"])
            themes = args.themes.split(",") if args.themes else None
            st = harvest(conn, client, args.areas.split(","), themes, args.target)
            print(f"완료: 검색 {st.queries}회, 추가 {st.added}곳, 중복 {st.skipped_existing}, 카페 아님 {st.skipped_not_cafe}, 오류 {len(st.errors)}")
            return
        if args.cmd == "enrich-instagram":
            client = InstagramClient(os.environ["INSTAGRAM_ACCESS_TOKEN"], os.environ["INSTAGRAM_USER_ID"])
            tagger = ClaudeVisionTagger(cfg.vision_model, cfg.vision_max_side) if args.vision == "claude" else None
            enrich_cafes(conn, client, cfg, args.limit, tagger)
            return
        if args.cmd == "import-tourapi-bulk":
            stats = bulk_import(conn, os.environ["TOURAPI_KEY"], [int(a) for a in args.areas.split(",")],
                                [int(t) for t in args.types.split(",")], storage, args.target, download_images=not args.no_images,
                                detail_images=args.detail_images)
            print("완료:", summary(stats))
            for e in stats.errors[:5]:
                print("  오류:", e)
            return
        if args.cmd == "import-tourapi":
            imgs = fetch_detail_images(os.environ["TOURAPI_KEY"], args.content_id)
            print(f"사용 가능한 사진 {len(imgs)}장, 신규 등록 {register_images(conn, args.spot, imgs, storage)}장")
            return
        if args.cmd == "integrity":
            rep = integrity.run(conn, cfg, args.sample)
            if args.json:
                import json as _json, dataclasses
                print(_json.dumps(dataclasses.asdict(rep), ensure_ascii=False, indent=1, default=str))
            else:
                print(rep.summary())
                for d in rep.drifted[:10]:
                    print("  달라짐:", d["place"], d["time_slot"], d["diff"])
            return 0 if rep.ok() else 1
        if args.cmd == "calibrate":
            pairs = load_pairs(conn)
            if len(pairs) < 30:
                print(f"검수된 사진이 {len(pairs)}장뿐이라 보정 결과를 신뢰하기 어려움 (30장 이상 권장)")
            _, report, changed = calibrate(pairs, cfg.colors)
            print("정확도:", report)
            print("제안 기준값 (현재 → 제안):", changed or "변경 없음")
            return
        tagger = ClaudeVisionTagger(cfg.vision_model, cfg.vision_max_side) if args.vision == "claude" else None
        for s in analyze(conn, storage, cfg, args.spot, tagger, get_masker(args.mask), args.reanalyze):
            flag = "검수필요" if s["needs_review"] else "OK"
            state = "갱신" if s["updated"] else "수동태그 유지"
            print(f"[{flag}] {s['spot_id'][:8]} {s['time_slot']}/{s['season']} "
                  f"신뢰도 {s['confidence']} 사진 {s['photos']}장 ({state}) {s['reasons']}")


if __name__ == "__main__":
    main()
