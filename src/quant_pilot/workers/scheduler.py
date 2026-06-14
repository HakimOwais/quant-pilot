"""APScheduler process: periodic jobs that enqueue work onto the RQ queue.

Runs in its own container (`python -m quant_pilot.workers.scheduler`). Timezone is
Asia/Kolkata so cron times line up with the NSE session.
"""

from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler

from quant_pilot.log import configure_logging, get_logger
from quant_pilot.workers import tasks
from quant_pilot.workers.queue import get_queue


def build_scheduler() -> BlockingScheduler:
    sched = BlockingScheduler(timezone="Asia/Kolkata")
    # Nightly OHLCV refresh after the NSE close (placeholder symbol list).
    sched.add_job(
        lambda: get_queue().enqueue(tasks.ingest_data, []),
        trigger="cron",
        hour=18,
        minute=0,
        id="nightly_data_refresh",
        replace_existing=True,
    )
    return sched


def main() -> None:
    configure_logging()
    log = get_logger("scheduler")
    log.info("scheduler.start", timezone="Asia/Kolkata")
    build_scheduler().start()


if __name__ == "__main__":
    main()
