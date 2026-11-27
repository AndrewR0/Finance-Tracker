"""Backup status: reads the newest backup file's name. No database involved."""

import datetime as dt

from app.main import app
from app.routers.backups import get_backups_dir


def status(client, folder):
    app.dependency_overrides[get_backups_dir] = lambda: folder
    try:
        response = client.get("/api/backups/status")
    finally:
        app.dependency_overrides.pop(get_backups_dir)
    assert response.status_code == 200, response.json()
    return response.json()


def test_newest_backup_wins(client, tmp_path):
    for name in ("finance-2026-11-25-030001.db", "finance-2026-11-26-030002.db", "notes.txt"):
        (tmp_path / name).write_bytes(b"")

    body = status(client, tmp_path)

    assert dt.datetime.fromisoformat(body["last_backup_at"]) == dt.datetime(2026, 11, 26, 3, 0, 2)
    assert body["count"] == 2  # notes.txt isn't a backup


def test_no_backups_yet(client, tmp_path):
    assert status(client, tmp_path) == {"last_backup_at": None, "count": 0}


def test_missing_folder(client, tmp_path):
    assert status(client, tmp_path / "nope") == {"last_backup_at": None, "count": 0}
