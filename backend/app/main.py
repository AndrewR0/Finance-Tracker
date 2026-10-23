"""FastAPI entry point. Run with: uv run uvicorn app.main:app --reload"""

from fastapi import FastAPI

app = FastAPI(title="Finance Tracker")


@app.get("/api/health")
def healthcheck():
    return {"status": "ok"}