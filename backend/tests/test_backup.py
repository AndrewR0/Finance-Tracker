"""scripts/backup.py: a consistent copy, and only the newest few are kept."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup.py"
spec = importlib.util.spec_from_file_location("backup", SCRIPT)
backup_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_module)


def make_database(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE t (x INTEGER)")
        db.execute("INSERT INTO t VALUES (42)")
    db.close()


def test_backup_copies_the_data(tmp_path):
    database = tmp_path / "finance.db"
    make_database(database)

    target = backup_module.backup(database, tmp_path / "backups")

    copy = sqlite3.connect(target)
    assert copy.execute("SELECT x FROM t").fetchall() == [(42,)]
    copy.close()


def test_only_the_newest_are_kept(tmp_path):
    database = tmp_path / "finance.db"
    make_database(database)
    folder = tmp_path / "backups"
    folder.mkdir()
    for day in range(1, 6):  # five old backups
        (folder / f"finance-2026-01-0{day}-000000.db").write_bytes(b"")

    newest = backup_module.backup(database, folder, keep=3)

    left = sorted(p.name for p in folder.glob("finance-*.db"))
    assert left == ["finance-2026-01-04-000000.db", "finance-2026-01-05-000000.db", newest.name]


def test_no_database_stops_with_a_message(tmp_path):
    with pytest.raises(SystemExit):
        backup_module.backup(tmp_path / "missing.db", tmp_path / "backups")
