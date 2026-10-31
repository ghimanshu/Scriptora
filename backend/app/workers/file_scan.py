import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import engine, session_factory
from app.integrations.scanner import scan
from app.integrations.storage import storage
from app.models.articles import File
from app.services.notifications import admins, emit


def run():
    factory = session_factory()
    with factory() as db:
        ids = list(
            db.scalars(
                select(File.id)
                .where(File.scan_status == "PENDING")
                .order_by(File.created_at)
                .limit(20)
            )
        )
    for file_id in ids:
        # Session advisory lock coordinates scanners without holding a row transaction during I/O.
        with (
            engine().connect() as connection,
            Session(bind=connection, expire_on_commit=False) as db,
        ):
            lock_key = file_id.int % (2**63 - 1)
            if not db.scalar(select(func.pg_try_advisory_lock(lock_key))):
                continue
            try:
                file = db.get(File, file_id)
                if not file or file.scan_status != "PENDING":
                    continue
                key, checksum = file.storage_key, file.sha256
                db.commit()
                try:
                    data = storage().get(key)
                    clean = hashlib.sha256(data).hexdigest() == checksum and scan(data)
                    file.scan_status = "CLEAN" if clean else "QUARANTINED"
                except Exception:
                    file.scan_attempts += 1
                    if file.scan_attempts >= 8:
                        file.scan_status = "FAILED"
                        emit(db, file.id, "SCAN_FAILED", admins(db), f"scan-failed:{file.id}")
                db.commit()
            finally:
                db.rollback()
                db.execute(select(func.pg_advisory_unlock(lock_key)))
                db.commit()
