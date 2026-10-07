-- =====================================================================
-- 007: 인스타그램 등 외부 게시물의 '분석 결과만' 저장 (006 이후 실행). 이미지 자체는 저장하지 않는다.
-- =====================================================================
CREATE TABLE IF NOT EXISTS external_media (
    id           bigserial PRIMARY KEY,
    place_id     uuid NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    spot_id      uuid NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    source       text NOT NULL,                  -- instagram
    media_id     text NOT NULL,
    permalink    text,                           -- 앱에서는 공식 임베드(oEmbed)로만 표시
    taken_at     timestamptz,
    labels       jsonb NOT NULL,                 -- 색 통계 + AI 판정 + 시간대 (사진 원본 없음)
    analyzed_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, media_id)
);
CREATE INDEX IF NOT EXISTS external_media_spot_idx ON external_media (spot_id);

ALTER TABLE places ADD COLUMN IF NOT EXISTS instagram_handle text;     -- 카페 공식 계정 (사장님 등록·수동 큐레이션)
