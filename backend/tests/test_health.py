from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "demo": False}


def test_demo_copy_says_so(monkeypatch):
    monkeypatch.setenv("FINANCE_DEMO", "1")

    assert client.get("/api/health").json()["demo"] is True


def test_seed_script_refuses_the_real_database(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py"
    result = subprocess.run([sys.executable, str(script), str(tmp_path / "finance.db")], capture_output=True, text=True)

    assert result.returncode != 0
    assert "real database" in result.stderr
    assert not (tmp_path / "finance.db").exists()
