from .db import get_db
from .weather import current, save_current

def run_weather_job(job_id):
    with get_db() as db:
        job=db.execute("SELECT * FROM weather_jobs WHERE id=%s AND enabled=TRUE",(job_id,)).fetchone()
    if not job: return False
    try:
        save_current(current(job["location"],job["latitude"],job["longitude"]))
        with get_db() as db:
            db.execute("""UPDATE weather_jobs SET last_run_at=CURRENT_TIMESTAMP,last_status='completed',
                          last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=%s""",(job_id,)); db.commit()
        return True
    except Exception as exc:
        with get_db() as db:
            db.execute("""UPDATE weather_jobs SET last_run_at=CURRENT_TIMESTAMP,last_status='failed',
                          last_error=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s""",(str(exc),job_id)); db.commit()
        return False

def due_weather_jobs():
    with get_db() as db:
        return db.execute("""SELECT * FROM weather_jobs WHERE enabled=TRUE AND
            (last_run_at IS NULL OR last_run_at <= CURRENT_TIMESTAMP -
             (interval_minutes * INTERVAL '1 minute')) ORDER BY id""").fetchall()

def run_due_weather_jobs():
    return [(job["id"],run_weather_job(job["id"])) for job in due_weather_jobs()]
