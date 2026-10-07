-- Saju is opt-in per search; day stem adds weight 4 without changing the practical gate.
-- Users without scoring dimensions can browse eligible nearby places.
CREATE OR REPLACE FUNCTION score_scenes_in(p_user uuid, p_visit date, p_place_ids uuid[], p_use_saju boolean, p_day_element text)
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
    SELECT dimension, user_value FROM user_dimensions WHERE user_id = p_user AND (dimension <> 'element' OR p_use_saju)
    UNION ALL
    SELECT 'day_element', p_day_element WHERE p_use_saju AND p_day_element IS NOT NULL
      AND EXISTS (SELECT 1 FROM user_dimensions WHERE user_id=p_user AND dimension='element')
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
weights AS (
    SELECT w.* FROM score_weights w JOIN cfg ON cfg.version=w.version
    UNION ALL
    SELECT cfg.version, 'day_element', 'element', 'auxiliary', 4 FROM cfg
),
matched AS (
    SELECT ca.scene_id, r.dimension, r.attribute, max(r.score) AS score
      FROM cand_attrs ca
      JOIN ud ON TRUE
      JOIN match_rules r ON r.dimension = ud.dimension AND r.user_value = ud.user_value
                        AND r.attribute = ca.attribute AND r.attr_value = ca.attr_value
     GROUP BY ca.scene_id, r.dimension, r.attribute
    UNION ALL
    SELECT ca.scene_id, 'day_element', 'element', 1 FROM cand_attrs ca
      WHERE ca.attribute='element' AND ca.attr_value=p_day_element AND p_use_saju
),
parts AS (
    SELECT c.id AS scene_id, w.dimension, w.attribute, w.layer, w.weight, COALESCE(m.score, 0) AS score
      FROM candidate c
     CROSS JOIN cfg
      JOIN weights w ON w.version = cfg.version
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
       COALESCE(a.total, 0), a.practical,
       (a.practical IS NULL OR a.practical >= cfg.practical_min),
       COALESCE(a.breakdown, '{}'::jsonb)
  FROM candidate c
  LEFT JOIN agg a ON a.scene_id = c.id
 CROSS JOIN cfg
 ORDER BY 9 DESC, COALESCE(a.total, 0) DESC, c.id;
$$;

CREATE OR REPLACE FUNCTION recommend_places_near(
    p_user uuid, p_visit date, p_lat double precision, p_lng double precision,
    p_radius_m int, p_limit int, p_time_slot time_slot_t, p_use_saju boolean, p_day_element text
)
RETURNS TABLE (
    scene_id uuid, place_id uuid, place_name text, spot_name text, time_slot time_slot_t,
    total numeric, practical numeric, distance_m int, breakdown jsonb
)
LANGUAGE sql STABLE AS $$
WITH origin AS (SELECT ST_MakePoint(p_lng, p_lat)::geography AS g),
near AS (
    SELECT p.id, ST_Distance(p.geom, o.g) AS dist
      FROM places p, origin o
     WHERE ST_DWithin(p.geom, o.g, p_radius_m)            -- GIST 인덱스 사용
       AND p.status IN ('active', 'unverified')
),
scored AS (
    SELECT * FROM score_scenes_in(p_user, p_visit, ARRAY(SELECT id FROM near), p_use_saju, p_day_element) s
     WHERE s.passed AND (p_time_slot IS NULL OR s.time_slot = p_time_slot)
),
best AS (
    SELECT DISTINCT ON (s.place_id) s.* FROM scored s ORDER BY s.place_id, s.total DESC
)
SELECT b.scene_id, b.place_id, b.place_name, b.spot_name, b.time_slot,
       b.total, b.practical, round(n.dist)::int, b.breakdown
  FROM best b JOIN near n ON n.id = b.place_id
 ORDER BY b.total DESC, n.dist ASC
 LIMIT p_limit;
$$;

-- Existing internal callers use the base profile, without the optional saju layer.
CREATE OR REPLACE FUNCTION score_scenes_in(p_user uuid, p_visit date, p_place_ids uuid[])
RETURNS TABLE (scene_id uuid, place_id uuid, place_name text, spot_name text,
 time_slot time_slot_t, season season_t, total numeric, practical numeric, passed boolean, breakdown jsonb)
LANGUAGE sql STABLE AS $$
 SELECT * FROM score_scenes_in(p_user, p_visit, p_place_ids, false, NULL);
$$;
