"""Backup status: /api/backups/status. Read-only: it only looks at the backup files.

Backups are made outside the app (scripts/backup.py on the PC, deploy/backup.sh nightly on the
server). Both put them in a "backups" folder next to the database, named
finance-YYYY-MM-DD-HHMMSS.db, so the newest name tells us when the last one ran.
"""

import datetime as dt
import os
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.engine import make_url

from app.db import DATABASE_URL
from app.schemas import BackupStatus

router = APIRouter(prefix="/api/backups", tags=["backups"])

NAME = re.compile(r"^finance-(\d{4}-\d{2}-\d{2}-\d{6})\.db$")


def get_backups_dir() -> Path | None:
    """The backups folder next to the database file, or None for an in-memory database."""
    if override := os.environ.get("FINANCE_BACKUPS_DIR"):
        return Path(override)
    database = make_url(DATABASE_URL).database
    if not database or database == ":memory:":
        return None
    return Path(database).resolve().parent / "backups"


BackupsDir = Annotated[Path | None, Depends(get_backups_dir)]


@router.get("/status", response_model=BackupStatus)
def backup_status(folder: BackupsDir):
    stamps = []
    if folder is not None and folder.is_dir():
        for file in folder.iterdir():
            if match := NAME.match(file.name):
                stamps.append(dt.datetime.strptime(match.group(1), "%Y-%m-%d-%H%M%S"))
    return BackupStatus(last_backup_at=max(stamps) if stamps else None, count=len(stamps))
