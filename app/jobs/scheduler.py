from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.jobs.tasks import job_attention, job_purge_payloads, job_release_handoffs
from app.timeutil import IST


def build_scheduler() -> AsyncIOScheduler:
    """All schedules are in IST."""
    scheduler = AsyncIOScheduler(timezone=IST, job_defaults={"coalesce": True, "max_instances": 1})
    scheduler.add_job(job_release_handoffs, IntervalTrigger(minutes=15, timezone=IST), id="release_handoffs")
    scheduler.add_job(job_attention, CronTrigger(hour=9, minute=0, timezone=IST), id="daily_attention")
    scheduler.add_job(job_purge_payloads, CronTrigger(hour=2, minute=30, timezone=IST), id="purge_payloads")
    return scheduler
