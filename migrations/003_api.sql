-- =====================================================================
-- 003: API 서버용 (schema.sql, 002_pipeline.sql 이후 실행)
-- =====================================================================

-- 1) 반경 안 장소만 먼저 고른 뒤 채점 (전국 규모에서 전체 채점을 피함)
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
    SELECT s.id, sp.place_id, p.name AS place_name, sp.name AS spot_name, s.time_slot, s.season
      FROM scenes s
      JOIN spots  sp ON sp.id = s.spot_id
      JOIN places p  ON p.id  = sp.place_id
     WHERE (p_place_ids IS NULL OR p.id = ANY(p_place_ids))
       AND p.status IN ('active', 'unverified')
       AND (s.season = 'all' OR s.season = season_of(p_visit))
       AND is_open_on(p.id, p_visit)
),
parts AS (
    SELECT c.id AS scene_id, w.dimension, w.attribute, w.layer, w.weight,
           COALESCE((
               SELECT max(r.score)
                 FROM scene_attributes sa
                 JOIN match_rules r ON r.attribute = sa.attribute AND r.attr_value = sa.attr_value
                WHERE sa.scene_id = c.id AND sa.attribute = w.attribute
                  AND r.dimension = w.dimension AND r.user_value = ud.user_value
           ), 0) AS score
      FROM candidate c
     CROSS JOIN cfg
      JOIN score_weights w ON w.version = cfg.version
      JOIN ud ON ud.dimension = w.dimension
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

-- 기존 함수는 전체 대상 호출로 유지 (하위 호환)
CREATE OR REPLACE FUNCTION score_scenes(p_user uuid, p_visit date DEFAULT current_date)
RETURNS TABLE (
    scene_id uuid, place_id uuid, place_name text, spot_name text,
    time_slot time_slot_t, season season_t,
    total numeric, practical numeric, passed boolean, breakdown jsonb
)
LANGUAGE sql STABLE AS $$
    SELECT * FROM score_scenes_in(p_user, p_visit, NULL);
$$;

CREATE OR REPLACE FUNCTION recommend_places_near(
    p_user uuid, p_visit date, p_lat double precision, p_lng double precision,
    p_radius_m int DEFAULT 5000, p_limit int DEFAULT 20, p_time_slot time_slot_t DEFAULT NULL
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
    SELECT * FROM score_scenes_in(p_user, p_visit, ARRAY(SELECT id FROM near)) s
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


-- 2) 작업 큐: 별도 인프라 없이 Postgres로 (FOR UPDATE SKIP LOCKED)
CREATE TABLE IF NOT EXISTS jobs (
    id          bigserial PRIMARY KEY,
    kind        text NOT NULL,                 -- analyze_spot, import_tourapi ...
    payload     jsonb NOT NULL,
    status      text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts    int NOT NULL DEFAULT 0,
    run_after   timestamptz NOT NULL DEFAULT now(),
    locked_at   timestamptz,
    last_error  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS jobs_ready_idx ON jobs (run_after) WHERE status = 'queued';
-- 같은 스팟 분석 작업이 대기열에 중복으로 쌓이지 않게
CREATE UNIQUE INDEX IF NOT EXISTS jobs_dedup_uq ON jobs (kind, (payload->>'spot_id')) WHERE status = 'queued';


-- 3) 검수자 기록
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS verified_by uuid REFERENCES users(id) ON DELETE SET NULL;
