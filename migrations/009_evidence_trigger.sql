-- 009: 사람이 입력·검수한 장면(manual/verified)은 근거가 항상 human 이 되도록 자동 보정 (008 이후)
CREATE OR REPLACE FUNCTION scenes_set_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.tag_source IN ('manual', 'verified') THEN
        NEW.evidence := 'human';
    ELSIF NEW.evidence = 'human' THEN                 -- 자동 태그가 human 을 주장할 수는 없다
        NEW.evidence := CASE WHEN COALESCE(NEW.photo_count, 0) > 0 THEN 'photos' ELSE 'category' END;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS scenes_evidence_trg ON scenes;
CREATE TRIGGER scenes_evidence_trg BEFORE INSERT OR UPDATE OF tag_source, evidence ON scenes
    FOR EACH ROW EXECUTE FUNCTION scenes_set_evidence();
UPDATE scenes SET evidence = 'human' WHERE tag_source IN ('manual', 'verified') AND evidence <> 'human';
