-- 파이프라인용 컬럼·뷰 추가 (schema.sql 이후 실행)
ALTER TABLE photos
    ADD COLUMN IF NOT EXISTS time_slot time_slot_t,
    ADD COLUMN IF NOT EXISTS season    season_t,
    ADD COLUMN IF NOT EXISTS labels    jsonb;          -- 사진별 판정 원본 (재집계·디버깅용)

ALTER TABLE scenes
    ADD COLUMN IF NOT EXISTS tag_confidence jsonb,     -- 태그별 신뢰도
    ADD COLUMN IF NOT EXISTS photo_count    int,
    ADD COLUMN IF NOT EXISTS review_reasons text[];

-- 검수 대기열: 자동 태깅됐지만 아직 사람이 확인하지 않은 장면 중 신뢰도 낮은 순
CREATE OR REPLACE VIEW scene_review_queue AS
SELECT s.id AS scene_id, p.name AS place_name, sp.name AS spot_name,
       s.time_slot, s.season, s.confidence, s.photo_count, s.review_reasons, s.tagged_at
  FROM scenes s
  JOIN spots  sp ON sp.id = s.spot_id
  JOIN places p  ON p.id = sp.place_id
 WHERE s.tag_source = 'auto' AND s.verified_at IS NULL
   AND (s.confidence < 0.6 OR cardinality(s.review_reasons) > 0)
 ORDER BY s.confidence ASC NULLS FIRST;
