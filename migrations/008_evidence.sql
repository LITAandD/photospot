-- =====================================================================
-- 008: 점수의 근거(evidence)를 명시하고, 사진 근거 또는 사람 확정 장면만 채점에 쓴다 (007 이후 실행)
--   category : 분류 코드·검색 테마로 붙인 초기 태그 → 추천에 쓰지 않음 (분석 대기 표시)
--   photos   : 사진 분석으로 확정 → 사진 수·신뢰도 기준을 넘어야 채점
--   human    : 사람이 입력·검수 → 항상 채점
-- =====================================================================
CREATE TYPE evidence_t AS ENUM ('category', 'photos', 'human');

ALTER TABLE scenes ADD COLUMN IF NOT EXISTS evidence evidence_t;
UPDATE scenes SET evidence = CASE
    WHEN tag_source IN ('manual', 'verified') THEN 'human'::evidence_t
    WHEN COALESCE(photo_count, 0) > 0 THEN 'photos'::evidence_t
    ELSE 'category'::evidence_t END
 WHERE evidence IS NULL;
ALTER TABLE scenes ALTER COLUMN evidence SET NOT NULL, ALTER COLUMN evidence SET DEFAULT 'category';

-- 사진 근거 최소 기준 (운영하며 조정)
ALTER TABLE score_settings
    ADD COLUMN IF NOT EXISTS min_photos int NOT NULL DEFAULT 3,
    ADD COLUMN IF NOT EXISTS min_confidence numeric(3,2) NOT NULL DEFAULT 0.60;

-- 채점 대상 여부를 한 곳에서 판단
CREATE OR REPLACE FUNCTION scene_scorable(s scenes, cfg score_settings) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT s.evidence = 'human'
        OR (s.evidence = 'photos' AND COALESCE(s.photo_count, 0) >= cfg.min_photos
            AND COALESCE(s.confidence, 0) >= cfg.min_confidence)
$$;

CREATE OR REPLACE FUNCTION score_scenes_in(p_user uuid, p_visit date, p_place_ids uuid[])
RETURNS TABLE (
    scene_id uuid, place_id uuid, place_name text, spot_name text,
    time_slot time_slot_t, season season_t,
    total numeric, practical numeric, passed boolean, breakdown jsonb
)
LANGUAGE sql STABLE AS $$
WITH cfg AS (
    SELECT * FROM score_settings WHERE is_active
),
ud AS (
    SELECT dimension, user_value FROM user_dimensions WHERE user_id = p_user
),
candidate AS (
    SELECT s.id, sp.place_id, p.name AS place_name, sp.name AS spot_name, s.time_slot, s.season,
           s.color_temp, s.brightness, s.saturation, s.lighting, s.form, s.texture, s.scale,
           s.crowd_level, s.place_character, s.photo_mood
      FROM scenes s
      JOIN spots  sp ON sp.id = s.spot_id
      JOIN places p  ON p.id  = sp.place_id
     CROSS JOIN cfg
     WHERE (p_place_ids IS NULL OR p.id = ANY(p_place_ids))
       AND p.status IN ('active', 'unverified')
       AND scene_scorable(s, cfg)                                    -- 사진 근거 또는 사람 확정만
       AND (s.season = 'all' OR s.season = season_of(p_visit))
       AND is_open_on(p.id, p_visit)
),
cand_attrs AS (
    SELECT c.id AS scene_id, a.attribute, a.attr_value
      FROM candidate c
     CROSS JOIN LATERAL (VALUES
        ('color_temp', c.color_temp::text), ('brightness', c.brightness::text), ('saturation', c.saturation::text),
        ('lighting', c.lighting::text), ('form', c.form::text), ('texture', c.texture::text), ('scale', c.scale::text),
        ('crowd_level', c.crowd_level::text), ('place_character', c.place_character::text), ('photo_mood', c.photo_mood::text)
     ) AS a(attribute, attr_value)
     WHERE a.attr_value IS NOT NULL
    UNION ALL
    SELECT c.id, 'element', e.element::text FROM candidate c JOIN scene_elements e ON e.scene_id = c.id
),
matched AS (
    SELECT ca.scene_id, r.dimension, r.attribute, max(r.score) AS score
      FROM cand_attrs ca
      JOIN ud ON TRUE
      JOIN match_rules r ON r.dimension = ud.dimension AND r.user_value = ud.user_value
                        AND r.attribute = ca.attribute AND r.attr_value = ca.attr_value
     GROUP BY ca.scene_id, r.dimension, r.attribute
),
parts AS (
    SELECT c.id AS scene_id, w.dimension, w.attribute, w.layer, w.weight, COALESCE(m.score, 0) AS score
      FROM candidate c
     CROSS JOIN cfg
      JOIN score_weights w ON w.version = cfg.version
      JOIN ud ON ud.dimension = w.dimension
      LEFT JOIN matched m ON m.scene_id = c.id AND m.dimension = w.dimension AND m.attribute = w.attribute
),
agg AS (
    SELECT scene_id,
           round(100 * sum(score * weight) / nullif(sum(weight), 0), 1) AS total,
           round(100 * sum(score * weight) FILTER (WHERE layer = 'practical')
                     / nullif(sum(weight) FILTER (WHERE layer = 'practical'), 0), 1) AS practical,
           jsonb_object_agg(dimension || '.' || attribute, score * weight) AS breakdown
      FROM parts GROUP BY scene_id
)
SELECT c.id, c.place_id, c.place_name, c.spot_name, c.time_slot, c.season,
       a.total, a.practical,
       (a.practical IS NULL OR a.practical >= cfg.practical_min),
       a.breakdown
  FROM candidate c
  JOIN agg a ON a.scene_id = c.id
 CROSS JOIN cfg
 ORDER BY 9 DESC, a.total DESC;
$$;

-- 정합성 점검용: 장면별 근거 상태
CREATE OR REPLACE VIEW scene_integrity AS
SELECT s.id AS scene_id, p.name AS place_name, sp.name AS spot_name, s.time_slot, s.season,
       s.evidence, s.tag_source, s.photo_count, s.confidence, s.tag_confidence, s.review_reasons,
       scene_scorable(s, cfg) AS scorable
  FROM scenes s
  JOIN spots sp ON sp.id = s.spot_id
  JOIN places p ON p.id = sp.place_id
 CROSS JOIN (SELECT * FROM score_settings WHERE is_active) cfg;
