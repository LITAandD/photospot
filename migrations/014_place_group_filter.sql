-- Filter categories before scoring and limiting; retain the existing nine-argument API.
CREATE OR REPLACE FUNCTION recommend_places_near(
    p_user uuid, p_visit date, p_lat double precision, p_lng double precision,
    p_radius_m int, p_limit int, p_time_slot time_slot_t, p_use_saju boolean, p_day_element text, p_place_group text
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
       AND (p_place_group='all' OR (p_place_group='cafe' AND p.category='cafe')
         OR (p_place_group='festival' AND p.category='festival_site')
         OR (p_place_group='travel' AND p.category IN ('attraction','park','museum','heritage','street')))
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
 ORDER BY b.total DESC, n.dist ASC, b.place_id
 LIMIT p_limit;
$$;
