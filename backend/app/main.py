"""FastAPI entry point. Run with: uv run uvicorn app.main:app --reload"""

from fastapi import FastAPI

from app.routers import accounts, categories, dashboard, transactions, transfers

app = FastAPI(title="Finance Tracker")
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(transfers.router)
app.include_router(dashboard.router)


@app.get("/api/health")
def healthcheck():
    return {"status": "ok"}
