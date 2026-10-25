"""FastAPI entry point. Run with: uv run uvicorn app.main:app --reload"""

from fastapi import FastAPI

from app.routers import accounts

app = FastAPI(title="Finance Tracker")
app.include_router(accounts.router)


@app.get("/api/health")
def healthcheck():
    return {"status": "ok"}
