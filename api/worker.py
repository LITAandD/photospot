"""작업 처리기: Postgres 큐에서 작업을 꺼내 파이프라인을 돌린다.

  python -m api.worker            # 계속 실행
  DATABASE_URL, STORAGE_ROOT, ANTHROPIC_API_KEY 환경변수 사용
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
