-- =====================================================================
-- 예시 데이터: 서울 8곳 + 테스트 사용자 2명
-- 좌표는 예시용 근사값, 태그는 공개 정보 기반 추정치 (실서비스에선 사진 분석·현장 검수로 확정)
-- =====================================================================

INSERT INTO places (id, name, category, sido, sigungu, geom, status) VALUES
 ('10000000-0000-0000-0000-000000000001', '서울식물원',           'park',     '서울특별시', '강서구', ST_MakePoint(126.8350, 37.5694)::geography, 'active'),
 ('10000000-0000-0000-0000-000000000002', '창경궁 대온실',         'heritage', '서울특별시', '종로구', ST_MakePoint(126.9936, 37.5822)::geography, 'active'),
 ('10000000-0000-0000-0000-000000000003', '국립현대미술관 서울관', 'museum',   '서울특별시', '종로구', ST_MakePoint(126.9800, 37.5786)::geography, 'active'),
 ('10000000-0000-0000-0000-000000000004', 'DDP',                  'attraction','서울특별시', '중구',   ST_MakePoint(127.0092, 37.5665)::geography, 'active'),
 ('10000000-0000-0000-0000-000000000005', '하늘공원',             'park',     '서울특별시', '마포구', ST_MakePoint(126.8853, 37.5683)::geography, 'active'),
 ('10000000-0000-0000-0000-000000000006', '반포 달빛무지개분수',   'attraction','서울특별시', '서초구', ST_MakePoint(126.9960, 37.5122)::geography, 'active'),
 ('10000000-0000-0000-0000-000000000007', '어니언 성수',           'cafe',     '서울특별시', '성동구', ST_MakePoint(127.0584, 37.5447)::geography, 'unverified'),
 ('10000000-0000-0000-0000-000000000008', '창덕궁',               'heritage', '서울특별시', '종로구', ST_MakePoint(126.9910, 37.5794)::geography, 'active');

-- 운영 조건
INSERT INTO operating_rules (place_id, rule_type, weekday, start_md, end_md, note) VALUES
 ('10000000-0000-0000-0000-000000000001', 'weekly_closed', 1, NULL, NULL, '월요일 휴관'),
 ('10000000-0000-0000-0000-000000000002', 'weekly_closed', 1, NULL, NULL, '월요일 휴궁'),
 ('10000000-0000-0000-0000-000000000008', 'weekly_closed', 1, NULL, NULL, '월요일 휴궁'),
 ('10000000-0000-0000-0000-000000000006', 'open_period',   NULL, '03-15', '10-31', '분수 운영기간'),
 ('10000000-0000-0000-0000-000000000005', 'open_period',   NULL, '09-01', '11-10', '억새 시즌(예시)');

-- 스팟 (예시는 장소당 1개)
INSERT INTO spots (id, place_id, name) VALUES
 ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '온실 스카이워크'),
 ('20000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', '온실 내부'),
 ('20000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000003', '서울박스·마당'),
 ('20000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000004', '외관 곡면'),
 ('20000000-0000-0000-0000-000000000005', '10000000-0000-0000-0000-000000000005', '억새밭 산책로'),
 ('20000000-0000-0000-0000-000000000006', '10000000-0000-0000-0000-000000000006', '반포한강공원 강변'),
 ('20000000-0000-0000-0000-000000000007', '10000000-0000-0000-0000-000000000007', '실내 공장 공간'),
 ('20000000-0000-0000-0000-000000000008', '10000000-0000-0000-0000-000000000008', '전각 앞 마당');

-- 장면 태그 (앞서 정리한 표를 enum으로 변환)
INSERT INTO scenes (id, spot_id, time_slot, season,
                    color_temp, brightness, saturation, lighting, form, texture, scale,
                    crowd_level, place_character, photo_mood, tag_source, confidence) VALUES
 ('30000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'midday', 'all',
  'neutral', 'bright_soft', 'mid', 'diffused_natural', 'curved', 'soft', 'spacious',
  'moderate', 'concept', 'emotional', 'manual', 0.70),
 ('30000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002', 'midday', 'all',
  'cool', 'bright_soft', 'muted', 'diffused_natural', 'curved', 'soft', 'medium',
  'moderate', 'concept', 'emotional', 'manual', 0.70),
 ('30000000-0000-0000-0000-000000000003', '20000000-0000-0000-0000-000000000003', 'midday', 'all',
  'cool', 'bright_soft', 'muted', 'diffused_natural', 'linear', 'sleek', 'spacious',
  'quiet', 'concept', 'structural', 'manual', 0.70),
 ('30000000-0000-0000-0000-000000000004', '20000000-0000-0000-0000-000000000004', 'night', 'all',
  'cool', 'high_contrast', 'mid', 'cool_artificial_night', 'curved', 'sleek', 'spacious',
  'moderate', 'concept', 'structural', 'manual', 0.70),
 ('30000000-0000-0000-0000-000000000005', '20000000-0000-0000-0000-000000000005', 'golden_hour', 'autumn',
  'warm', 'mid', 'muted', 'direct_golden', 'organic', 'rough', 'spacious',
  'busy', 'concept', 'emotional', 'manual', 0.70),
 ('30000000-0000-0000-0000-000000000006', '20000000-0000-0000-0000-000000000006', 'night', 'all',
  'cool', 'high_contrast', 'vivid', 'cool_artificial_night', 'organic', NULL, 'spacious',
  'busy', 'concept', 'emotional', 'manual', 0.70),
 ('30000000-0000-0000-0000-000000000007', '20000000-0000-0000-0000-000000000007', 'midday', 'all',
  'neutral', 'mid', 'muted', 'diffused_natural', 'organic', 'rough', 'medium',
  'busy', 'detail', 'structural', 'manual', 0.60),
 ('30000000-0000-0000-0000-000000000008', '20000000-0000-0000-0000-000000000008', 'midday', 'autumn',
  'warm', 'mid', 'muted', 'direct_golden', 'linear', 'rough', 'spacious',
  'moderate', 'detail', 'structural', 'manual', 0.70);

INSERT INTO scene_elements (scene_id, element) VALUES
 ('30000000-0000-0000-0000-000000000001', 'wood'),
 ('30000000-0000-0000-0000-000000000002', 'wood'),
 ('30000000-0000-0000-0000-000000000002', 'metal'),
 ('30000000-0000-0000-0000-000000000003', 'metal'),
 ('30000000-0000-0000-0000-000000000004', 'metal'),
 ('30000000-0000-0000-0000-000000000005', 'earth'),
 ('30000000-0000-0000-0000-000000000005', 'fire'),
 ('30000000-0000-0000-0000-000000000006', 'water'),
 ('30000000-0000-0000-0000-000000000007', 'earth'),
 ('30000000-0000-0000-0000-000000000008', 'wood'),
 ('30000000-0000-0000-0000-000000000008', 'earth');

-- 테스트 사용자
--  A: 여성 162cm, 여름쿨 라이트, 웨이브, INFP, 사주 입력(수 부족)
--  B: 남성 181cm, 겨울쿨 딥, 스트레이트, ENTJ, 사주 미입력
INSERT INTO users (id) VALUES
 ('a0000000-0000-0000-0000-000000000001'),
 ('b0000000-0000-0000-0000-000000000002');

INSERT INTO user_profiles (user_id, gender, height_cm, pc_season, pc_subtone, body_type, mbti) VALUES
 ('a0000000-0000-0000-0000-000000000001', 'female', 162, 'summer_cool', 'light', 'wave',     'INFP'),
 ('b0000000-0000-0000-0000-000000000002', 'male',   181, 'winter_cool', 'deep',  'straight', 'ENTJ');

INSERT INTO user_consents (user_id, consent_type, policy_version) VALUES
 ('a0000000-0000-0000-0000-000000000001', 'saju', 'v1');

INSERT INTO user_saju (user_id, has_birth_time, wood, fire, earth, metal, water, dominant_element, method, calc_version) VALUES
 ('a0000000-0000-0000-0000-000000000001', true, 18.2, 13.6, 13.6, 13.6, 40.9, 'water', 'forceteller_v1', 'v1');
