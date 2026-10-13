"""Tempest station scheduling, separate from OpenWeatherMap jobs."""
from .db import get_db
from .tempest import collect_tempest_station


def run_tempest_job(station_id):
    with get_db() as db:
        job = db.execute(
            "SELECT station_id FROM tempest_jobs WHERE station_id=%s AND enabled=TRUE",
            (station_id,),
        ).fetchone()
    if not job:
        return False
    try:
        collect_tempest_station(station_id)
        status, detail = "completed", None
    except Exception as exc:
        status, detail = "failed", str(exc)[:1000]
    with get_db() as db:
        db.execute(
            """UPDATE tempest_jobs SET last_run_at=CURRENT_TIMESTAMP,
               last_status=%s, last_error=%s, updated_at=CURRENT_TIMESTAMP
               WHERE station_id=%s""",
            (status, detail, station_id),
        )
        db.commit()
    return status == "completed"


def run_due_tempest_jobs():
    # Row locking prevents concurrent scheduler processes from claiming the same job.
    with get_db() as db:
        rows = db.execute(
            """SELECT station_id FROM tempest_jobs WHERE enabled=TRUE
               AND (last_status='queued' OR last_run_at IS NULL OR last_run_at <= CURRENT_TIMESTAMP -
                    interval_minutes * INTERVAL '1 minute')
               FOR UPDATE SKIP LOCKED"""
        ).fetchall()
        ids = [row["station_id"] for row in rows]
        if ids:
            db.execute(
                """UPDATE tempest_jobs SET last_run_at=CURRENT_TIMESTAMP,
                   last_status='running' WHERE station_id=ANY(%s)""",
                (ids,),
            )
        db.commit()
    return [(station_id, run_tempest_job(station_id)) for station_id in ids]
