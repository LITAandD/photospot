-- =====================================================================
-- 004: 사주 오행을 '개수'가 아니라 '가중 비율(%)'로 저장하고, 가장 많은 오행(dominant)을 추천에 사용
-- (003 이후 실행). 기존 행은 원본이 없어 재계산할 수 없으므로 사용자가 다시 입력해야 한다.
-- =====================================================================
ALTER TABLE user_saju
    ADD COLUMN IF NOT EXISTS dominant_element element_t,
    ADD COLUMN IF NOT EXISTS method text NOT NULL DEFAULT 'count_v1';   -- forceteller_v1: 궁성·조후·합충 보정

DO $$
DECLARE c text;
BEGIN
    SELECT conname INTO c FROM pg_constraint
     WHERE conrelid = 'user_saju'::regclass AND contype = 'c'
       AND pg_get_constraintdef(oid) LIKE '%has_birth_time%';
    IF c IS NOT NULL THEN
        EXECUTE format('ALTER TABLE user_saju DROP CONSTRAINT %I', c);
    END IF;
END $$;

ALTER TABLE user_saju
    ALTER COLUMN wood  TYPE numeric(5,2), ALTER COLUMN fire  TYPE numeric(5,2),
    ALTER COLUMN earth TYPE numeric(5,2), ALTER COLUMN metal TYPE numeric(5,2),
    ALTER COLUMN water TYPE numeric(5,2),
    ALTER COLUMN lacking_element DROP NOT NULL;
COMMENT ON COLUMN user_saju.wood IS '오행 비율(%). method=forceteller_v1 이면 궁성·조후·합충 보정 적용값';

-- 추천에는 가장 많은 오행을 쓴다 (예전 행은 부족 오행으로 대체)
CREATE OR REPLACE VIEW user_dimensions AS
    SELECT user_id, 'pc_season' AS dimension, pc_season::text AS user_value
      FROM user_profiles WHERE pc_season IS NOT NULL
UNION ALL
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
    SELECT s.user_id, 'element', COALESCE(s.dominant_element, s.lacking_element)::text
      FROM user_saju s
      JOIN user_consents c ON c.user_id = s.user_id AND c.consent_type = 'saju' AND c.revoked_at IS NULL
     WHERE COALESCE(s.dominant_element, s.lacking_element) IS NOT NULL;
