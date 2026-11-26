"""FastAPI entry point. Run with: uv run uvicorn app.main:app --reload"""

import asyncio
import datetime as dt
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app import prices
from app.db import engine
from app.frontend import mount_frontend
from app.routers import (
    accounts,
    categories,
    dashboard,
    goals,
    imports,
    investments,
    recurring,
    retirement,
    transactions,
    transfers,
)

log = logging.getLogger(__name__)

# How often prices are fetched while the app runs. Markets close once a day; a few checks a
# day catch the close without hammering Yahoo.
REFRESH_EVERY = dt.timedelta(hours=6)


def refresh_prices_once() -> None:
    with Session(engine) as db:
        result = prices.refresh_prices(db, prices.YFinanceProvider(), dt.date.today())
    log.info("prices refreshed: %d updated, failed: %s", result.updated, result.failed or "none")


async def refresh_prices_forever() -> None:
    """Background task: refresh at startup, then every REFRESH_EVERY. Never crashes the app."""
    while True:
        try:
            # In a thread: yfinance blocks while it downloads, and the API should keep answering.
            await asyncio.to_thread(refresh_prices_once)
        except Exception:
            log.exception("price refresh crashed")
        await asyncio.sleep(REFRESH_EVERY.total_seconds())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the price refresher with the app, and stop it on shutdown.

    FINANCE_PRICE_REFRESH=off turns it off (tests do, so they never touch the network).
    """
    task = None
    if os.environ.get("FINANCE_PRICE_REFRESH", "on") != "off":
        task = asyncio.create_task(refresh_prices_forever())
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Finance Tracker", lifespan=lifespan)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(transfers.router)
app.include_router(dashboard.router)
app.include_router(imports.router)
app.include_router(recurring.router)
app.include_router(goals.router)
app.include_router(investments.router)
app.include_router(retirement.router)


@app.get("/api/health")
def healthcheck():
    return {"status": "ok"}


# Last: its catch-all route must come after every /api route.
mount_frontend(app)
