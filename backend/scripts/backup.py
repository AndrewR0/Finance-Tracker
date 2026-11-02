"""Copy finance.db into backend/backups/, keeping the newest KEEP copies.

Usage (from backend\\):  uv run python scripts/backup.py

It uses SQLite's backup API instead of copying the file. A plain file copy taken while
the app is writing can catch half a change; the backup API copies a consistent snapshot,
so it's safe to run with the app open.
"""

import datetime as dt
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DATABASE = BACKEND / "finance.db"
BACKUPS = BACKEND / "backups"
KEEP = 30


def backup(database: Path = DATABASE, folder: Path = BACKUPS, keep: int = KEEP) -> Path:
    if not database.exists():
        sys.exit(f"No database at {database}. Nothing to back up.")
    folder.mkdir(exist_ok=True)
    target = folder / f"finance-{dt.datetime.now():%Y-%m-%d-%H%M%S}.db"

    # mode=ro: open the real database read-only, so a bug here can't change it.
    source = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    with copy:
        source.backup(copy)
    copy.close()
    source.close()

    # The names sort by date, so everything before the newest `keep` is old.
    for old in sorted(folder.glob("finance-*.db"))[:-keep]:
        old.unlink()
    return target


if __name__ == "__main__":
    print(f"Backed up to {backup()}")
