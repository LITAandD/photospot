-- =====================================================================
-- 포토스팟 추천 앱 — 장소 DB 스키마 (PostgreSQL 16 + PostGIS 3)
--
-- 설계 원칙
--   1. 추천 단위는 '장소'가 아니라 '장면(scene) = 스팟 × 시간대 × 계절'
--   2. 외부 서비스(네이버·구글·카카오·인스타)는 ID와 링크만 저장
--      (사진·리뷰·영업시간 같은 외부 콘텐츠는 저장하지 않고 실시간 조회)
--   3. 매핑 로직(규칙·가중치)은 코드가 아니라 데이터 → 배포 없이 수정 가능
--   4. 사주는 원본 생년월일시를 저장하지 않고 계산 결과만 저장
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------
-- 0. 타입 정의
-- ---------------------------------------------------------------------
CREATE TYPE gender_t        AS ENUM ('female', 'male', 'other', 'undisclosed');
CREATE TYPE pc_season_t     AS ENUM ('spring_warm', 'summer_cool', 'autumn_warm', 'winter_cool');
CREATE TYPE pc_subtone_t    AS ENUM ('light', 'bright', 'true', 'mute', 'deep');
CREATE TYPE body_type_t     AS ENUM ('straight', 'wave', 'natural');
CREATE TYPE height_band_t   AS ENUM ('small', 'medium', 'tall');
CREATE TYPE element_t       AS ENUM ('wood', 'fire', 'earth', 'metal', 'water');   -- 목화토금수

CREATE TYPE place_category_t AS ENUM ('attraction', 'park', 'museum', 'heritage', 'cafe',
                                      'restaurant', 'street', 'festival_site', 'other');
CREATE TYPE place_status_t  AS ENUM ('active', 'unverified', 'temporarily_closed', 'closed');
CREATE TYPE provider_t      AS ENUM ('naver', 'google', 'kakao', 'tourapi', 'instagram');

CREATE TYPE time_slot_t     AS ENUM ('morning', 'midday', 'golden_hour', 'night');
CREATE TYPE season_t        AS ENUM ('spring', 'summer', 'autumn', 'winter', 'all');

-- 장면 태그 (실용 레이어)
CREATE TYPE color_temp_t    AS ENUM ('warm', 'neutral', 'cool');
CREATE TYPE brightness_t    AS ENUM ('bright_soft', 'mid', 'high_contrast');       -- 명도·대비
CREATE TYPE saturation_t    AS ENUM ('muted', 'mid', 'vivid');                     -- 채도
CREATE TYPE lighting_t      AS ENUM ('diffused_natural', 'direct_golden',          -- 확산광 / 직사광·골든아워
                                     'warm_artificial', 'cool_artificial_night');  -- 따뜻한 조명 / 차가운 조명·야경
CREATE TYPE form_t          AS ENUM ('linear', 'curved', 'organic');               -- 직선 / 곡선·장식 / 비정형·자연
CREATE TYPE texture_t       AS ENUM ('sleek', 'soft', 'rough');                    -- 매끈 / 부드러움 / 거침·자연소재
CREATE TYPE scale_t         AS ENUM ('compact', 'medium', 'spacious');
-- 장면 태그 (보조 레이어)
CREATE TYPE crowd_t         AS ENUM ('quiet', 'moderate', 'busy');                 -- E/I
CREATE TYPE character_t     AS ENUM ('detail', 'concept');                         -- S/N
CREATE TYPE mood_t          AS ENUM ('structural', 'emotional');                   -- T/F

CREATE TYPE tag_source_t    AS ENUM ('auto', 'manual', 'verified');
CREATE TYPE photo_source_t  AS ENUM ('tourapi', 'user_upload', 'owner_upload', 'own_shoot');
CREATE TYPE license_t       AS ENUM ('kogl_type1', 'kogl_type2', 'kogl_type3', 'kogl_type4',
                                     'user_consent', 'owner_consent', 'own');
CREATE TYPE consent_type_t  AS ENUM ('style_profile', 'saju', 'photo_analysis', 'location');
CREATE TYPE rule_type_t     AS ENUM ('weekly_closed', 'open_period', 'closed_period');


-- ---------------------------------------------------------------------
-- 1. 사용자
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    deleted_at  timestamptz
);

-- 모든 항목 선택 입력(NULL = 모름/미입력). 미입력 항목은 점수 계산에서 빠지고 가중치가 자동 재배분됨
CREATE TABLE user_profiles (
    user_id     uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    gender      gender_t NOT NULL DEFAULT 'undisclosed',
    birth_year  smallint CHECK (birth_year BETWEEN 1900 AND 2100),   -- 추후 연령대별 트렌드 반영용
    height_cm   numeric(4,1) CHECK (height_cm BETWEEN 100 AND 230),
    pc_season   pc_season_t,
    pc_subtone  pc_subtone_t,
    body_type   body_type_t,
    mbti        char(4) CHECK (mbti ~ '^[EI][SN][TF][JP]$'),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- 사주: 원본 생년월일시는 계산 후 폐기하고 오행 개수만 저장
CREATE TABLE user_saju (
    user_id          uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    has_birth_time   boolean  NOT NULL,          -- false면 년·월·일 6글자로 계산
    wood   smallint NOT NULL CHECK (wood  >= 0),
    fire   smallint NOT NULL CHECK (fire  >= 0),
    earth  smallint NOT NULL CHECK (earth >= 0),
    metal  smallint NOT NULL CHECK (metal >= 0),
    water  smallint NOT NULL CHECK (water >= 0),
    lacking_element  element_t NOT NULL,         -- 보완형 추천에 쓰는 '가장 부족한 오행'
    calc_version     text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CHECK ((has_birth_time     AND wood + fire + earth + metal + water = 8)
        OR (NOT has_birth_time AND wood + fire + earth + metal + water = 6))
);

CREATE TABLE user_consents (
    id              bigserial PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type    consent_type_t NOT NULL,
    policy_version  text NOT NULL,
    granted_at      timestamptz NOT NULL DEFAULT now(),
    revoked_at      timestamptz
);
CREATE UNIQUE INDEX user_consents_active_uq
    ON user_consents (user_id, consent_type) WHERE revoked_at IS NULL;


-- ---------------------------------------------------------------------
-- 2. 장소 · 스팟 · 장면
-- ---------------------------------------------------------------------
CREATE TABLE places (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name              text NOT NULL,
    category          place_category_t NOT NULL,
    sido              text NOT NULL,                 -- 시·도
    sigungu           text,                          -- 시·군·구
    address           text,
    geom              geography(Point, 4326) NOT NULL,
    status            place_status_t NOT NULL DEFAULT 'unverified',
    last_verified_at  timestamptz,                   -- 카페 폐업·리뉴얼 점검 주기 관리용
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX places_geom_gix   ON places USING gist (geom);
CREATE INDEX places_region_idx ON places (sido, sigungu);

-- 외부 서비스 연결: ID와 링크만 저장 (구글은 place_id만 무기한 저장 허용)
CREATE TABLE place_external_ids (
    provider     provider_t NOT NULL,
    external_id  text NOT NULL,
    place_id     uuid NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    url          text,
    linked_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, external_id)
);
CREATE INDEX place_external_ids_place_idx ON place_external_ids (place_id);

-- 사장님(파트너) 계정
CREATE TABLE place_owners (
    place_id     uuid REFERENCES places(id) ON DELETE CASCADE,
    user_id      uuid REFERENCES users(id)  ON DELETE CASCADE,
    verified_at  timestamptz,
    PRIMARY KEY (place_id, user_id)
);

-- 운영 조건: 정기 휴무, 연중 반복 운영기간(MM-DD), 특정 연도 기간(축제 등)
CREATE TABLE operating_rules (
    id          bigserial PRIMARY KEY,
    place_id    uuid NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    rule_type   rule_type_t NOT NULL,
    weekday     smallint CHECK (weekday BETWEEN 0 AND 6),   -- 0=일요일 … 6=토요일
    start_md    char(5),                                   -- 매년 반복: 'MM-DD'
    end_md      char(5),
    start_date  date,                                      -- 특정 기간
    end_date    date,
    note        text,
    CHECK (
        (rule_type = 'weekly_closed' AND weekday IS NOT NULL)
     OR (rule_type IN ('open_period', 'closed_period') AND (
            (start_date IS NOT NULL AND end_date IS NOT NULL AND start_md IS NULL AND end_md IS NULL)
         OR (start_md ~ '^\d{2}-\d{2}$' AND end_md ~ '^\d{2}-\d{2}$' AND start_date IS NULL AND end_date IS NULL)))
    )
);
CREATE INDEX operating_rules_place_idx ON operating_rules (place_id);

-- 스팟: 한 장소 안의 촬영 지점 (예: '2층 창가', '스카이워크')
CREATE TABLE spots (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id    uuid NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    name        text NOT NULL,
    guide       text,                                  -- 촬영 위치·구도 안내
    geom        geography(Point, 4326),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX spots_place_idx ON spots (place_id);

-- 장면: 추천의 기본 단위 (스팟 × 시간대 × 계절)
CREATE TABLE scenes (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    spot_id          uuid NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    time_slot        time_slot_t NOT NULL,
    season           season_t NOT NULL DEFAULT 'all',
    -- 실용 레이어 (NULL = 해당 없음 → 점수 0)
    color_temp       color_temp_t,
    brightness       brightness_t,
    saturation       saturation_t,
    lighting         lighting_t,
    form             form_t,
    texture          texture_t,
    scale            scale_t,
    -- 보조 레이어
    crowd_level      crowd_t,
    place_character  character_t,
    photo_mood       mood_t,
    -- 태그 품질
    tag_source       tag_source_t NOT NULL DEFAULT 'auto',
    confidence       numeric(3,2) CHECK (confidence BETWEEN 0 AND 1),
    tagged_at        timestamptz NOT NULL DEFAULT now(),
    verified_at      timestamptz,
    UNIQUE (spot_id, time_slot, season)
);

-- 오행은 한 장면에 여러 개 가능 (예: 노을 억새밭 = 토 + 화)
CREATE TABLE scene_elements (
    scene_id  uuid REFERENCES scenes(id) ON DELETE CASCADE,
    element   element_t NOT NULL,
    PRIMARY KEY (scene_id, element)
);


-- ---------------------------------------------------------------------
-- 3. 사진 (태그 생성 원천) — 분석·저장이 허용된 출처만 받음
-- ---------------------------------------------------------------------
CREATE TABLE photos (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    spot_id       uuid NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    scene_id      uuid REFERENCES scenes(id) ON DELETE SET NULL,
    source        photo_source_t NOT NULL,
    source_ref    text,                               -- TourAPI contentid 등
    license       license_t NOT NULL,
    uploader_id   uuid REFERENCES users(id) ON DELETE SET NULL,
    storage_path  text NOT NULL,
    taken_at      timestamptz,
    -- 색 분석 결과 (인물 제외 배경 픽셀, CIELAB 기준)
    lab_l         numeric(5,2),                       -- 평균 명도
    lab_c         numeric(5,2),                       -- 평균 채도
    hue_deg       numeric(5,2),                       -- 평균 색상각 (웜/쿨 판정)
    l_stddev      numeric(5,2),                       -- 명도 편차 (대비 판정)
    palette       jsonb,                              -- [{"hex":"#F2EDE4","ratio":0.42}, ...]
    analyzed_at   timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    -- 상업적 이용 금지(공공누리 2·4유형) 사진은 입력 자체를 막음
    CONSTRAINT photo_license_ok CHECK (
        license NOT IN ('kogl_type2', 'kogl_type4')
        AND (source <> 'tourapi'      OR license IN ('kogl_type1', 'kogl_type3'))
        AND (source <> 'user_upload'  OR license = 'user_consent')
        AND (source <> 'owner_upload' OR license = 'owner_consent')
        AND (source <> 'own_shoot'    OR license = 'own')
    )
);
CREATE INDEX photos_spot_idx  ON photos (spot_id);
CREATE INDEX photos_scene_idx ON photos (scene_id);

-- 인스타그램 트렌드 신호: 게시물 자체는 저장하지 않고 수치만
CREATE TABLE trend_signals (
    id                  bigserial PRIMARY KEY,
    place_id            uuid NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    source              text NOT NULL DEFAULT 'instagram_hashtag',
    hashtag             text,
    recent_media_count  int,
    collected_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX trend_signals_place_idx ON trend_signals (place_id, collected_at DESC);


-- ---------------------------------------------------------------------
-- 4. 매핑 로직 (데이터로 관리)
-- ---------------------------------------------------------------------
-- 규칙: (사용자 차원, 사용자 값) × (장면 속성, 속성 값) → +1 / -1
-- 등록되지 않은 조합은 0(중립)
CREATE TABLE match_rules (
    dimension   text NOT NULL,      -- pc_season, pc_tone, body_type, height_band, mbti_ei, mbti_sn, mbti_tf, element
    user_value  text NOT NULL,
    attribute   text NOT NULL,      -- scenes 컬럼명 또는 'element'
    attr_value  text NOT NULL,
    score       smallint NOT NULL CHECK (score IN (-1, 1)),
    PRIMARY KEY (dimension, user_value, attribute, attr_value)
);

CREATE TABLE score_settings (
    version        int PRIMARY KEY,
    practical_min  numeric(5,1) NOT NULL,   -- 실용 레이어 최소 기준 (보조지표가 메인을 뒤집지 못하게)
    is_active      boolean NOT NULL DEFAULT false,
    note           text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX score_settings_one_active ON score_settings (is_active) WHERE is_active;

CREATE TABLE score_weights (
    version    int  NOT NULL REFERENCES score_settings(version),
    dimension  text NOT NULL,
    attribute  text NOT NULL,
    layer      text NOT NULL CHECK (layer IN ('practical', 'auxiliary')),
    weight     numeric(5,2) NOT NULL CHECK (weight > 0),
    PRIMARY KEY (version, dimension, attribute)
);


-- ---------------------------------------------------------------------
-- 5. 추천 기록 · 피드백 (태그 검증 루프)
-- ---------------------------------------------------------------------
CREATE TABLE recommendations (
    id               bigserial PRIMARY KEY,
    user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scene_id         uuid NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    weights_version  int NOT NULL REFERENCES score_settings(version),
    total            numeric(5,1) NOT NULL,
    breakdown        jsonb NOT NULL,
    visit_date       date,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX recommendations_user_idx ON recommendations (user_id, created_at DESC);

CREATE TABLE recommendation_feedback (
    recommendation_id  bigint PRIMARY KEY REFERENCES recommendations(id) ON DELETE CASCADE,
    visited            boolean,
    rating             smallint CHECK (rating BETWEEN 1 AND 5),
    photo_id           uuid REFERENCES photos(id) ON DELETE SET NULL,
    tag_corrections    jsonb,          -- 사용자가 고친 태그 예: {"lighting": "warm_artificial"}
    created_at         timestamptz NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------
-- 6. 헬퍼 함수 · 뷰
-- ---------------------------------------------------------------------
CREATE FUNCTION season_of(d date) RETURNS season_t
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN extract(month FROM d) IN (3, 4, 5)  THEN 'spring'
        WHEN extract(month FROM d) IN (6, 7, 8)  THEN 'summer'
        WHEN extract(month FROM d) IN (9, 10, 11) THEN 'autumn'
        ELSE 'winter'
    END::season_t
$$;

-- 키 구간: 성별 평균 기준 (초기값, 운영하며 조정)
CREATE FUNCTION calc_height_band(g gender_t, h numeric) RETURNS height_band_t
LANGUAGE sql IMMUTABLE AS $$
    SELECT (CASE
        WHEN h IS NULL      THEN NULL
        WHEN g = 'female'   THEN CASE WHEN h < 157 THEN 'small' WHEN h >= 167 THEN 'tall' ELSE 'medium' END
        WHEN g = 'male'     THEN CASE WHEN h < 170 THEN 'small' WHEN h >= 180 THEN 'tall' ELSE 'medium' END
        ELSE                     CASE WHEN h < 163 THEN 'small' WHEN h >= 174 THEN 'tall' ELSE 'medium' END
    END)::height_band_t
$$;

CREATE FUNCTION md_in_range(md text, s text, e text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN s <= e THEN md BETWEEN s AND e ELSE md >= s OR md <= e END   -- 연말~연초 걸친 기간 처리
$$;

CREATE FUNCTION is_open_on(p_place uuid, d date) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT
        NOT EXISTS (SELECT 1 FROM operating_rules r
                    WHERE r.place_id = p_place AND r.rule_type = 'weekly_closed'
                      AND r.weekday = extract(dow FROM d))
    AND NOT EXISTS (SELECT 1 FROM operating_rules r
                    WHERE r.place_id = p_place AND r.rule_type = 'closed_period'
                      AND ((r.start_date IS NOT NULL AND d BETWEEN r.start_date AND r.end_date)
                        OR (r.start_md  IS NOT NULL AND md_in_range(to_char(d, 'MM-DD'), r.start_md, r.end_md))))
    AND (NOT EXISTS (SELECT 1 FROM operating_rules r
                     WHERE r.place_id = p_place AND r.rule_type = 'open_period')
         OR EXISTS  (SELECT 1 FROM operating_rules r
                     WHERE r.place_id = p_place AND r.rule_type = 'open_period'
                       AND ((r.start_date IS NOT NULL AND d BETWEEN r.start_date AND r.end_date)
                         OR (r.start_md  IS NOT NULL AND md_in_range(to_char(d, 'MM-DD'), r.start_md, r.end_md)))))
$$;

-- 사용자 입력 → (차원, 값) 행으로 펼침. 미입력 항목은 행이 생기지 않음
CREATE VIEW user_dimensions AS
    SELECT user_id, 'pc_season' AS dimension, pc_season::text AS user_value
      FROM user_profiles WHERE pc_season IS NOT NULL
UNION ALL
    -- 세부 톤이 있으면 톤 규칙, 없거나 'true'면 계절 기본 규칙 사용
    SELECT user_id, 'pc_tone',
           CASE WHEN pc_subtone IS NULL OR pc_subtone = 'true'
                THEN 'default_' || pc_season::text ELSE pc_subtone::text END
      FROM user_profiles
     WHERE pc_season IS NOT NULL OR (pc_subtone IS NOT NULL AND pc_subtone <> 'true')
UNION ALL
    SELECT user_id, 'body_type', body_type::text FROM user_profiles WHERE body_type IS NOT NULL
UNION ALL
    SELECT user_id, 'height_band', calc_height_band(gender, height_cm)::text
      FROM user_profiles WHERE height_cm IS NOT NULL
UNION ALL
    SELECT user_id, 'mbti_ei', substr(mbti, 1, 1) FROM user_profiles WHERE mbti IS NOT NULL
UNION ALL
    SELECT user_id, 'mbti_sn', substr(mbti, 2, 1) FROM user_profiles WHERE mbti IS NOT NULL
UNION ALL
    SELECT user_id, 'mbti_tf', substr(mbti, 3, 1) FROM user_profiles WHERE mbti IS NOT NULL
UNION ALL
    -- 사주는 유효한 동의가 있을 때만 사용
    SELECT s.user_id, 'element', s.lacking_element::text
      FROM user_saju s
      JOIN user_consents c ON c.user_id = s.user_id AND c.consent_type = 'saju' AND c.revoked_at IS NULL;

-- 장면 태그 → (속성, 값) 행으로 펼침
CREATE VIEW scene_attributes AS
    SELECT s.id AS scene_id, a.attribute, a.attr_value
      FROM scenes s
     CROSS JOIN LATERAL (VALUES
        ('color_temp',      s.color_temp::text),
        ('brightness',      s.brightness::text),
        ('saturation',      s.saturation::text),
        ('lighting',        s.lighting::text),
        ('form',            s.form::text),
        ('texture',         s.texture::text),
        ('scale',           s.scale::text),
        ('crowd_level',     s.crowd_level::text),
        ('place_character', s.place_character::text),
        ('photo_mood',      s.photo_mood::text)
     ) AS a(attribute, attr_value)
     WHERE a.attr_value IS NOT NULL
UNION ALL
    SELECT scene_id, 'element', element::text FROM scene_elements;


-- ---------------------------------------------------------------------
-- 7. 점수 계산
--   total      = 100 × Σ(점수×가중치) / Σ(입력된 차원의 가중치)   → 미입력 항목 가중치 자동 재배분
--   practical  = 실용 레이어만 같은 방식으로 계산
--   passed     = practical ≥ practical_min
-- ---------------------------------------------------------------------
CREATE FUNCTION score_scenes(p_user uuid, p_visit date DEFAULT current_date)
RETURNS TABLE (
    scene_id    uuid,
    place_id    uuid,
    place_name  text,
    spot_name   text,
    time_slot   time_slot_t,
    season      season_t,
    total       numeric,
    practical   numeric,
    passed      boolean,
    breakdown   jsonb
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
     WHERE p.status IN ('active', 'unverified')
       AND (s.season = 'all' OR s.season = season_of(p_visit))
       AND is_open_on(p.id, p_visit)
),
parts AS (
    SELECT c.id AS scene_id, w.dimension, w.attribute, w.layer, w.weight,
           COALESCE((
               SELECT max(r.score)
                 FROM scene_attributes sa
                 JOIN match_rules r ON r.attribute = sa.attribute AND r.attr_value = sa.attr_value
                WHERE sa.scene_id  = c.id
                  AND sa.attribute = w.attribute
                  AND r.dimension  = w.dimension
                  AND r.user_value = ud.user_value
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
      FROM parts
     GROUP BY scene_id
)
SELECT c.id, c.place_id, c.place_name, c.spot_name, c.time_slot, c.season,
       a.total, a.practical,
       (a.practical IS NULL OR a.practical >= cfg.practical_min) AS passed,
       a.breakdown
  FROM candidate c
  JOIN agg a ON a.scene_id = c.id
 CROSS JOIN cfg
 ORDER BY passed DESC, a.total DESC;
$$;

-- 장소별 최고 장면만 골라 거리 조건으로 추천 (위경도 NULL이면 전국)
CREATE FUNCTION recommend_places(
    p_user      uuid,
    p_visit     date DEFAULT current_date,
    p_lat       double precision DEFAULT NULL,
    p_lng       double precision DEFAULT NULL,
    p_radius_m  int DEFAULT 30000,
    p_limit     int DEFAULT 10
)
RETURNS TABLE (
    place_id    uuid,
    place_name  text,
    spot_name   text,
    time_slot   time_slot_t,
    total       numeric,
    practical   numeric,
    distance_m  int,
    breakdown   jsonb
)
LANGUAGE sql STABLE AS $$
SELECT * FROM (
    SELECT DISTINCT ON (sc.place_id)
           sc.place_id, sc.place_name, sc.spot_name, sc.time_slot, sc.total, sc.practical,
           CASE WHEN p_lat IS NULL THEN NULL
                ELSE round(ST_Distance(p.geom, ST_MakePoint(p_lng, p_lat)::geography))::int END,
           sc.breakdown
      FROM score_scenes(p_user, p_visit) sc
      JOIN places p ON p.id = sc.place_id
     WHERE sc.passed
       AND (p_lat IS NULL OR ST_DWithin(p.geom, ST_MakePoint(p_lng, p_lat)::geography, p_radius_m))
     ORDER BY sc.place_id, sc.total DESC
) best
ORDER BY total DESC
LIMIT p_limit;
$$;


-- =====================================================================
-- 8. 초기 매핑 데이터 (v1) — 지금까지 합의한 로직
-- =====================================================================
INSERT INTO score_settings (version, practical_min, is_active, note)
VALUES (1, 10, true, '초기 버전: 실용 80 / 보조 20');

INSERT INTO score_weights (version, dimension, attribute, layer, weight) VALUES
    -- 퍼스널컬러 40 (조명이 얼굴에 직접 영향 → 가장 크게)
    (1, 'pc_season',   'lighting',        'practical', 16),
    (1, 'pc_season',   'color_temp',      'practical', 12),
    (1, 'pc_tone',     'brightness',      'practical',  6),
    (1, 'pc_tone',     'saturation',      'practical',  6),
    -- 체형 30 = 형태 15 + 질감 15
    (1, 'body_type',   'form',            'practical', 15),
    (1, 'body_type',   'texture',         'practical', 15),
    -- 키 10
    (1, 'height_band', 'scale',           'practical', 10),
    -- MBTI 12 (J/P는 점수 대신 결과 화면 구성에 사용)
    (1, 'mbti_ei',     'crowd_level',     'auxiliary',  4),
    (1, 'mbti_sn',     'place_character', 'auxiliary',  4),
    (1, 'mbti_tf',     'photo_mood',      'auxiliary',  4),
    -- 오행 8 (보완형)
    (1, 'element',     'element',         'auxiliary',  8);

INSERT INTO match_rules (dimension, user_value, attribute, attr_value, score) VALUES
    -- 퍼스널컬러: 계절 → 색온도·조명
    ('pc_season', 'spring_warm', 'color_temp', 'warm',  1),
    ('pc_season', 'spring_warm', 'color_temp', 'cool', -1),
    ('pc_season', 'spring_warm', 'lighting',   'direct_golden',          1),
    ('pc_season', 'spring_warm', 'lighting',   'cool_artificial_night', -1),
    ('pc_season', 'summer_cool', 'color_temp', 'cool',  1),
    ('pc_season', 'summer_cool', 'color_temp', 'warm', -1),
    ('pc_season', 'summer_cool', 'lighting',   'diffused_natural', 1),
    ('pc_season', 'summer_cool', 'lighting',   'warm_artificial', -1),
    ('pc_season', 'summer_cool', 'lighting',   'direct_golden',   -1),
    ('pc_season', 'autumn_warm', 'color_temp', 'warm',  1),
    ('pc_season', 'autumn_warm', 'color_temp', 'cool', -1),
    ('pc_season', 'autumn_warm', 'lighting',   'direct_golden',          1),
    ('pc_season', 'autumn_warm', 'lighting',   'warm_artificial',        1),
    ('pc_season', 'autumn_warm', 'lighting',   'cool_artificial_night', -1),
    ('pc_season', 'winter_cool', 'color_temp', 'cool',  1),
    ('pc_season', 'winter_cool', 'color_temp', 'warm', -1),
    ('pc_season', 'winter_cool', 'lighting',   'cool_artificial_night',  1),
    ('pc_season', 'winter_cool', 'lighting',   'warm_artificial',       -1),
    -- 퍼스널컬러: 톤 → 명도·채도 (세부 톤 미입력 시 계절 기본값)
    ('pc_tone', 'default_spring_warm', 'brightness', 'bright_soft',    1),
    ('pc_tone', 'default_spring_warm', 'brightness', 'high_contrast', -1),
    ('pc_tone', 'default_spring_warm', 'saturation', 'mid',            1),
    ('pc_tone', 'default_spring_warm', 'saturation', 'muted',         -1),
    ('pc_tone', 'default_summer_cool', 'brightness', 'bright_soft',    1),
    ('pc_tone', 'default_summer_cool', 'brightness', 'high_contrast', -1),
    ('pc_tone', 'default_summer_cool', 'saturation', 'muted',          1),
    ('pc_tone', 'default_summer_cool', 'saturation', 'vivid',         -1),
    ('pc_tone', 'default_autumn_warm', 'brightness', 'mid',            1),
    ('pc_tone', 'default_autumn_warm', 'saturation', 'muted',          1),
    ('pc_tone', 'default_autumn_warm', 'saturation', 'vivid',         -1),
    ('pc_tone', 'default_winter_cool', 'brightness', 'high_contrast',  1),
    ('pc_tone', 'default_winter_cool', 'brightness', 'bright_soft',   -1),
    ('pc_tone', 'default_winter_cool', 'saturation', 'vivid',          1),
    ('pc_tone', 'default_winter_cool', 'saturation', 'muted',         -1),
    ('pc_tone', 'light',  'brightness', 'bright_soft',    1),
    ('pc_tone', 'light',  'brightness', 'high_contrast', -1),
    ('pc_tone', 'light',  'saturation', 'vivid',         -1),
    ('pc_tone', 'bright', 'brightness', 'high_contrast',  1),
    ('pc_tone', 'bright', 'saturation', 'vivid',          1),
    ('pc_tone', 'bright', 'saturation', 'muted',         -1),
    ('pc_tone', 'mute',   'brightness', 'mid',            1),
    ('pc_tone', 'mute',   'brightness', 'high_contrast', -1),
    ('pc_tone', 'mute',   'saturation', 'muted',          1),
    ('pc_tone', 'mute',   'saturation', 'vivid',         -1),
    ('pc_tone', 'deep',   'brightness', 'high_contrast',  1),
    ('pc_tone', 'deep',   'brightness', 'bright_soft',   -1),
    -- 체형 → 형태·질감
    ('body_type', 'straight', 'form',    'linear',  1),
    ('body_type', 'straight', 'form',    'curved', -1),
    ('body_type', 'straight', 'texture', 'sleek',   1),
    ('body_type', 'wave',     'form',    'curved',  1),
    ('body_type', 'wave',     'texture', 'soft',    1),
    ('body_type', 'wave',     'texture', 'rough',  -1),
    ('body_type', 'natural',  'form',    'organic', 1),
    ('body_type', 'natural',  'texture', 'rough',   1),
    -- 키 → 공간 스케일
    ('height_band', 'tall',  'scale', 'spacious',  1),
    ('height_band', 'tall',  'scale', 'compact',  -1),
    ('height_band', 'small', 'scale', 'compact',   1),
    ('height_band', 'small', 'scale', 'spacious', -1),
    -- MBTI
    ('mbti_ei', 'E', 'crowd_level',     'busy',        1),
    ('mbti_ei', 'I', 'crowd_level',     'quiet',       1),
    ('mbti_ei', 'I', 'crowd_level',     'busy',       -1),
    ('mbti_sn', 'S', 'place_character', 'detail',      1),
    ('mbti_sn', 'N', 'place_character', 'concept',     1),
    ('mbti_tf', 'T', 'photo_mood',      'structural',  1),
    ('mbti_tf', 'F', 'photo_mood',      'emotional',   1),
    -- 오행 (보완형: 부족한 오행이 장면에 있으면 가점)
    ('element', 'wood',  'element', 'wood',  1),
    ('element', 'fire',  'element', 'fire',  1),
    ('element', 'earth', 'element', 'earth', 1),
    ('element', 'metal', 'element', 'metal', 1),
    ('element', 'water', 'element', 'water', 1);
