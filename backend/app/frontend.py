"""Serve the built React dashboard (frontend/dist) from FastAPI, so the app is one thing to start.

During development you don't need this: Vite's dev server serves the frontend and forwards
/api calls here. After `npm run build`, FastAPI serves the files itself.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

DEFAULT_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def mount_frontend(app: FastAPI, dist: Path = DEFAULT_DIST) -> None:
    """Serve files from dist, and index.html for every other non-API path.

    React decides what /transactions shows (client-side routing), so the server
    answers any unknown page path with index.html and lets React take over.
    Does nothing if the frontend hasn't been built yet.
    """
    if not (dist / "index.html").is_file():
        return

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")  # a mistyped API URL is not a page
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist.resolve()):  # never serve files outside dist
            return FileResponse(file)
        return FileResponse(dist / "index.html")
