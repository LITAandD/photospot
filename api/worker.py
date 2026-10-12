"""작업 처리기: Postgres 큐에서 작업을 꺼내 파이프라인을 돌린다.

  python -m api.worker            # 계속 실행
  DATABASE_URL, STORAGE_ROOT, ANTHROPIC_API_KEY 환경변수 사용
  JOB_LOCK_TIMEOUT_S (기본 1800): 이보다 오래 'running'인 작업은 처리기가 죽은 것으로 보고 다시 대기열에 넣는다
"""
from __future__ import annotations

import os
import time
import traceback

import psycopg
from psycopg.rows import dict_row

from pipeline.config import PipelineConfig
from pipeline.masking import get_masker
from pipeline.run import analyze
from pipeline.tourapi import LocalStorage
from pipeline.vision import ClaudeVisionTagger

MAX_ATTEMPTS = 3
LOCK_TIMEOUT_S = int(os.environ.get("JOB_LOCK_TIMEOUT_S", "1800"))


def recover_stale(conn, timeout_s: int = LOCK_TIMEOUT_S) -> int:
    """Re-queue jobs left 'running' by a worker that died; give up after MAX_ATTEMPTS."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT id, kind, payload, attempts FROM jobs
                        WHERE status='running' AND locked_at < now() - make_interval(secs => %s)
                        ORDER BY id FOR UPDATE SKIP LOCKED""", (timeout_s,))
        stale = cur.fetchall()
        for job in stale:
            # A queued duplicate for the same spot already covers this work (unique while queued).
            cur.execute("""SELECT 1 FROM jobs WHERE status='queued' AND kind=%s AND payload->>'spot_id' = %s""",
                        (job["kind"], job["payload"].get("spot_id")))
            if job["attempts"] >= MAX_ATTEMPTS or cur.fetchone():
                cur.execute("""UPDATE jobs SET status='failed', finished_at=now(), locked_at=NULL,
                                      last_error='작업 처리기가 응답하지 않아 중단했어요' WHERE id=%s""", (job["id"],))
            else:
                cur.execute("""UPDATE jobs SET status='queued', locked_at=NULL, run_after=now(),
                                      last_error='작업 처리기 중단 후 다시 대기' WHERE id=%s""", (job["id"],))
    conn.commit()
    return len(stale)


def claim(conn) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""UPDATE jobs SET status='running', locked_at=now(), attempts=attempts+1
                        WHERE id = (SELECT id FROM jobs WHERE status='queued' AND run_after <= now()
                                     ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1)
                    RETURNING id, kind, payload, attempts""")
        job = cur.fetchone()
    conn.commit()
    return job


def run_once(conn, storage: LocalStorage, cfg: PipelineConfig, tagger=None, masker=None) -> dict | None:
    recover_stale(conn)
    job = claim(conn)
    if not job:
        return None
    try:
        if job["kind"] == "analyze_spot":
            analyze(conn, storage, cfg, spot_id=job["payload"]["spot_id"], tagger=tagger, masker=masker)
        elif job["kind"] == "delete_files":
            for path in job["payload"]["paths"]:
                storage.delete(path)
        else:
            raise ValueError(f"알 수 없는 작업: {job['kind']}")
        with conn.cursor() as cur:
            cur.execute("UPDATE jobs SET status='done', finished_at=now() WHERE id=%s", (job["id"],))
    except Exception:
        conn.rollback()
        retry = job["attempts"] < MAX_ATTEMPTS
        with conn.cursor() as cur:
            cur.execute("UPDATE jobs SET status='failed', last_error=%s, finished_at=now() WHERE id=%s",
                        (traceback.format_exc()[-2000:], job["id"]))
            if retry:
                from psycopg.types.json import Jsonb
                cur.execute("""INSERT INTO jobs (kind, payload, attempts, run_after)
                               VALUES (%s, %s, %s, now() + make_interval(mins => %s))
                               ON CONFLICT (kind, (payload->>'spot_id')) WHERE status='queued' DO NOTHING""",
                            (job["kind"], Jsonb(job["payload"]), job["attempts"], 5 * job["attempts"]))
    conn.commit()
    return job


def main():
    cfg = PipelineConfig()
    storage = LocalStorage(os.environ.get("STORAGE_ROOT", "./storage"))
    tagger = ClaudeVisionTagger(cfg.vision_model, cfg.vision_max_side) if os.environ.get("ANTHROPIC_API_KEY") else None
    masker = get_masker(os.environ.get("PHOTO_MASKER", "none"))
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        while True:
            if not run_once(conn, storage, cfg, tagger, masker):
                time.sleep(2)


if __name__ == "__main__":
    main()
