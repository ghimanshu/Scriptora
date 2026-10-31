import logging
import signal
import socket
import threading

from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import db_now, session_factory
from app.models.notifications import WorkerHeartbeat
from app.workers import expiry, file_scan, outbox, reminders

stop = threading.Event()


def main():
    cfg = get_settings()
    configure_logging(cfg.log_level)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        for job in (expiry.run, reminders.run, file_scan.run, outbox.run):
            if stop.is_set():
                break
            try:
                job()
            except Exception:
                logging.getLogger(__name__).exception("Worker job failed: %s", job.__module__)
        with session_factory().begin() as db:
            now = db_now(db)
            db.execute(
                insert(WorkerHeartbeat)
                .values(id=socket.gethostname(), seen_at=now)
                .on_conflict_do_update(index_elements=["id"], set_={"seen_at": now})
            )
        stop.wait(cfg.worker_poll_interval_seconds)


if __name__ == "__main__":
    main()
