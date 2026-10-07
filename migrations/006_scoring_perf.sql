-- =====================================================================
-- 006: 채점 함수 성능 개선 (005 이후 실행)
-- 이전 구현은 후보 장면마다 scene_attributes 뷰(전체 장면)를 다시 훑는 상관 서브쿼리라
-- 장소가 수백 곳이면 십수 초가 걸렸다. 후보 장면의 속성만 한 번 펼쳐 규칙과 조인한다.
-- =====================================================================
CREATE OR REPLACE FUNCTION score_scenes_in(p_user uuid, p_visit date, p_place_ids uuid[])
RETURNS TABLE (
    scene_id uuid, place_id uuid, place_name text, spot_name text,
    time_slot time_slot_t, season season_t,
    total numeric, practical numeric, passed boolean, breakdown jsonb
)
LANGUAGE sql STABLE AS $$
WITH cfg AS (
    SELECT version, practical_min FROM score_settings WHERE is_active
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
     WHERE (p_place_ids IS NULL OR p.id = ANY(p_place_ids))
       AND p.status IN ('active', 'unverified')
       AND (s.season = 'all' OR s.season = season_of(p_visit))
       AND is_open_on(p.id, p_visit)
),
cand_attrs AS (                                   -- 후보 장면의 속성만 펼친다
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
matched AS (                                      -- 사용자 값과 맞는 규칙 (+1/-1)
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

CREATE INDEX IF NOT EXISTS scenes_spot_idx ON scenes (spot_id);
CREATE INDEX IF NOT EXISTS match_rules_lookup_idx ON match_rules (dimension, user_value, attribute, attr_value);
