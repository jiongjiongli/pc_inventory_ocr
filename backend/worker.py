import logging
import os
import time
import psycopg
from psycopg.types.json import Jsonb
from app import database, UPLOADS, remove_photo_files
from init_db import initialize
from ocr import extract_text
from diagnostics import configure_logging, step, event

log = logging.getLogger(__name__)

def process_next():
    with database() as db:
        pc = db.execute("SELECT id, photo FROM pcs WHERE ocr_status='pending' OR (ocr_status='failed' AND ocr_attempts<3) ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if not pc:
            return False
        db.execute("UPDATE pcs SET ocr_status='processing', ocr_attempts=ocr_attempts+1 WHERE id=%s", (pc['id'],))
    event('ocr.job_claimed', pc_id=pc['id'], photo=pc['photo'])
    started = time.perf_counter()
    with step('ocr.job', pc_id=pc['id'], photo=pc['photo']):
        result = extract_text(UPLOADS / pc['photo'])
    duration = time.perf_counter() - started
    with database() as db:
        updated = db.execute("UPDATE pcs SET ocr_text=%s, ocr_status=%s, ocr_confidence=%s, ocr_lines=%s, ocr_duration_seconds=%s WHERE id=%s AND photo=%s AND ocr_status='processing'", (result['text'], result['status'], result['confidence'], Jsonb(result['lines']), duration, pc['id'], pc['photo'])).rowcount
    if not updated:
        remove_photo_files(pc['photo'])
    event('ocr.job_finished', pc_id=pc['id'], photo=pc['photo'], status=result['status'], result_saved=bool(updated), duration_seconds=round(duration, 3), confidence=result['confidence'])
    return True

def main():
    configure_logging()
    event('worker.start')
    initialize()
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as owner:
        # Session lock prevents duplicate workers; a crash releases it.
        owner.execute('SELECT pg_advisory_lock(728452)')
        with database() as db:
            db.execute("UPDATE pcs SET ocr_status='pending', ocr_attempts=GREATEST(ocr_attempts-1,0) WHERE ocr_status='processing'")
        idle = False
        while True:
            try:
                owner.execute('SELECT 1')
                if not process_next():
                    if not idle:
                        event('worker.queue_drained')
                    idle = True
                    time.sleep(2)
                else:
                    idle = False
            except Exception:
                log.exception('worker.failed')
                raise

if __name__ == '__main__':
    main()
