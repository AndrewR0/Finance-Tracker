import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.frontend import mount_frontend


@pytest.fixture
def site(tmp_path):
    """A fake built frontend: dist/index.html, dist/assets/app.js, and a secret file next to dist."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log('hi')")
    (tmp_path / "secret.txt").write_text("nope")

    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    mount_frontend(app, dist)
    return TestClient(app)


def test_root_is_index(site):
    assert site.get("/").text == "<html>app</html>"


def test_files_are_served(site):
    assert site.get("/assets/app.js").text == "console.log('hi')"


def test_page_paths_fall_back_to_index(site):
    assert site.get("/transactions").text == "<html>app</html>"


def test_api_routes_still_win(site):
    assert site.get("/api/health").json() == {"status": "ok"}


def test_unknown_api_path_is_404_not_a_page(site):
    assert site.get("/api/nope").status_code == 404


def test_cannot_escape_dist(site):
    assert "nope" not in site.get("/..%2Fsecret.txt").text


def test_nothing_is_mounted_before_a_build(tmp_path):
    app = FastAPI()
    mount_frontend(app, tmp_path / "missing")

    assert TestClient(app).get("/").status_code == 404
