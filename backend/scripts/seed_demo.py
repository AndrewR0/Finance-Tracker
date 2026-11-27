"""Fill a DEMO database with a made-up person, for showing the app to friends.

Usage (inside the demo container, while the demo app is running):
    python scripts/seed_demo.py /data/demo.db --reset

Everything here is invented: the person, the payees, the amounts. It goes through the running
demo app's own API over HTTP (--url, default http://127.0.0.1:8000), so every rule the app
enforces applies to the demo data too. A fixed random seed makes it come out the same every time.

Safety: it refuses any file named finance.db, and refuses a database that already has data
unless --reset is given (which empties that database first).
"""

import argparse
import datetime as dt
import os
import random
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("database", type=Path, help="the demo database file, e.g. /data/demo.db")
parser.add_argument("--reset", action="store_true", help="empty the database first")
parser.add_argument("--url", default="http://127.0.0.1:8000", help="the running demo app (the one using this database)")
args = parser.parse_args()

DATABASE = args.database.resolve()
if DATABASE.name == "finance.db":
    sys.exit("Refusing: that looks like the real database (finance.db). Use a separate file, like demo.db.")

# Point app.db at the demo database BEFORE importing it (used here only to prepare the schema).
os.environ["FINANCE_DB_URL"] = f"sqlite:///{DATABASE.as_posix()}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
import json  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from sqlalchemy import inspect, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.models import Account  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
TODAY = dt.date.today()
START = dt.date(TODAY.year - 1, 1, 1)  # about two years of history
rng = random.Random(2026)


def prepare_database() -> None:
    """Fresh schema at the latest migration (and empty, with --reset)."""
    alembic_cfg = Config(str(BACKEND / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    has_tables = "accounts" in inspect(engine).get_table_names()
    if has_tables:
        with Session(engine) as db:
            has_data = db.scalar(select(Account.id).limit(1)) is not None
        if has_data and not args.reset:
            sys.exit(f"{DATABASE} already has data. Add --reset to empty it first.")
        if args.reset:
            Base.metadata.drop_all(engine)
            with engine.begin() as conn:
                conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    command.upgrade(alembic_cfg, "head")


prepare_database()


def call(method: str, url: str, **body):
    """One request to the running demo app. Exits with the app's message if it refuses."""
    data = json.dumps(body).encode() if body else None
    request = urllib.request.Request(args.url + url, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read()
    except urllib.error.HTTPError as error:
        sys.exit(f"{method} {url} failed ({error.code}): {error.read().decode()}\nbody: {body}")
    return json.loads(text) if text else None


def money(low: float, high: float) -> int:
    """A random amount in cents between two dollar amounts."""
    return int(rng.uniform(low, high) * 100)


def days(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


# ---- accounts and categories ----

acct = {
    "checking": call("POST", "/api/accounts", name="Everyday Checking", type="checking")["id"],
    "savings": call("POST", "/api/accounts", name="High-Yield Savings", type="savings")["id"],
    "card": call("POST", "/api/accounts", name="Rewards Visa", type="credit_card")["id"],
    "brokerage": call("POST", "/api/accounts", name="Index Brokerage", type="brokerage")["id"],
    "roth": call("POST", "/api/accounts", name="Roth IRA", type="retirement")["id"],
    "k401": call("POST", "/api/accounts", name="Workplace 401k", type="retirement")["id"],
}

TREE = {
    "income": {"Paycheck": [], "Interest": []},
    "expense": {
        "Housing": ["Rent", "Renters Insurance"],
        "Food": ["Groceries", "Dining Out", "Coffee"],
        "Transportation": ["Gas", "Rideshare", "Car Insurance"],
        "Bills & Utilities": ["Phone", "Internet", "Electric", "Subscriptions"],
        "Shopping": ["Clothing", "Electronics", "Home"],
        "Entertainment": ["Movies", "Concerts", "Games"],
        "Health": ["Gym", "Pharmacy"],
        "Travel": ["Flights", "Hotels"],
        "Giving": ["Gifts", "Charity"],
    },
    "transfer": {"Transfers": ["Credit Card Payment", "To Savings", "To Investments"]},
}
cat: dict[str, int] = {}
for kind, tops in TREE.items():
    for top, subs in tops.items():
        top_id = call("POST", "/api/categories", name=top, kind=kind)["id"]
        cat[top] = top_id
        for sub in subs:
            cat[sub] = call("POST", "/api/categories", name=sub, kind=kind, parent_id=top_id)["id"]

PAYEES = {
    "Groceries": ["FreshFields Market", "Corner Grocer", "Big Box Wholesale"],
    "Dining Out": ["Taco Hub", "Noodle Bar", "The Burger Joint", "Sunrise Diner", "Pizza Planet Co"],
    "Coffee": ["Bean There Cafe", "Daily Grind"],
    "Gas": ["QuickFuel", "Highway Gas"],
    "Rideshare": ["ZoomRide"],
    "Clothing": ["Threadline", "Outlet Row"],
    "Electronics": ["GadgetHub"],
    "Home": ["NestGoods", "Hardware Barn"],
    "Movies": ["Starlight Cinema"],
    "Concerts": ["TicketBooth"],
    "Games": ["PixelStore"],
    "Pharmacy": ["CareRx"],
}


def pick(sub: str) -> str:
    return rng.choice(PAYEES[sub])


card_balance = 0  # what the card owes right now (positive)


def spend(day: dt.date, sub: str, cents: int, payee: str | None = None, account: str = "card") -> None:
    global card_balance
    call("POST", "/api/transactions", account_id=acct[account], date=day.isoformat(), amount_cents=-cents,
         payee=payee or pick(sub), category_id=cat[sub])
    if account == "card":
        card_balance += cents


def earn(day: dt.date, sub: str, cents: int, payee: str, account: str = "checking") -> None:
    call("POST", "/api/transactions", account_id=acct[account], date=day.isoformat(), amount_cents=cents,
         payee=payee, category_id=cat[sub])


def transfer(day: dt.date, src: str, dst: str, cents: int, sub: str, description: str | None = None) -> None:
    call("POST", "/api/transfers", from_account_id=acct[src], to_account_id=acct[dst], date=day.isoformat(),
         amount_cents=cents, category_id=cat[sub], description=description)


# ---- opening balances (the day before the story starts) ----

opening = START - dt.timedelta(days=1)
call("POST", f"/api/accounts/{acct['checking']}/reconcile", date=opening.isoformat(), balance_cents=420000)
call("POST", f"/api/accounts/{acct['savings']}/reconcile", date=opening.isoformat(), balance_cents=650000)

# ---- investments: real tickers, prices from Yahoo when reachable, otherwise a smooth made-up path ----

FALLBACK = {"VTI": (240.0, 0.10), "VXUS": (58.0, 0.06)}  # (price at START, yearly drift)


def price_history(ticker: str) -> dict[dt.date, float]:
    try:
        from app.prices import YFinanceProvider

        closes = YFinanceProvider().closes(ticker, START - dt.timedelta(days=10), TODAY)
        if closes:
            return {d: float(p) for d, p in closes.items()}
    except Exception as error:  # offline: fall back to a made-up path
        print(f"(no live prices for {ticker}: {error}; using a made-up price path)")
    base, drift = FALLBACK[ticker]
    walk = random.Random(ticker)
    prices, price = {}, base
    for day in days(START - dt.timedelta(days=10), TODAY):
        if day.weekday() < 5:
            price *= 1 + drift / 252 + walk.gauss(0, 0.009)
            prices[day] = round(price, 2)
    return prices


HISTORY = {t: price_history(t) for t in FALLBACK}


def price_on(ticker: str, day: dt.date) -> float:
    candidates = [d for d in HISTORY[ticker] if d <= day]
    return HISTORY[ticker][max(candidates)] if candidates else next(iter(HISTORY[ticker].values()))


def shares_for(cents: int, price: float) -> str:
    return f"{cents / 100 / price:.4f}"


setup_day = START
for key, ticker, name, value in (("brokerage", "VTI", "Total Stock Market ETF", 900000),
                                 ("roth", "VXUS", "Total International ETF", 600000)):
    price = price_on(ticker, setup_day)
    call("POST", f"/api/accounts/{acct[key]}/holdings", date=setup_day.isoformat(), holdings=[{
        "ticker": ticker, "name": name, "kind": "fund", "price_source": "yfinance",
        "shares": shares_for(value, price), "cost_basis_cents": int(value * 0.85), "market_value_cents": value,
    }])
call("POST", f"/api/accounts/{acct['k401']}/holdings", date=setup_day.isoformat(), holdings=[{
    "ticker": "TRUST2060", "name": "Target Retirement 2060 Trust", "kind": "fund", "price_source": "manual",
    "shares": "520", "cost_basis_cents": 1800000, "market_value_cents": 2080000,
}])
holdings = {h["ticker"]: h["security_id"] for a in call("GET", "/api/holdings") for h in a["holdings"]}

# ---- the story, day by day ----

trust_price = 40.0
for day in days(START, TODAY):
    month_start = day.day == 1
    # Paychecks every other Friday, with a raise in the second year.
    if day.weekday() == 4 and (day - START).days // 7 % 2 == 0:
        earn(day, "Paycheck", 245000 if day.year == START.year else 262000, "Acme Analytics Payroll")
    if month_start:
        spend(day, "Rent", 165000, "Maple Court Apartments", account="checking")
        spend(day, "Renters Insurance", 1450, "SafeNest Insurance", account="checking")
        earn(day, "Interest", money(8, 22), "High-Yield Savings Interest", account="savings")
    if day.day == 3:
        spend(day, "Phone", 6500, "Bluewave Mobile")
        spend(day, "Internet", 5999, "FiberLink")
    if day.day == 5:
        spend(day, "Subscriptions", 1549, "StreamFlix")
        spend(day, "Gym", 4500, "IronWorks Gym")
    if day.day == 12:
        spend(day, "Subscriptions", 1199, "TuneBox Music")
        spend(day, "Electric", money(45, 130), "City Power & Light", account="checking")
    if day.day == 15:
        transfer(day, "checking", "savings", 40000, "To Savings")
        transfer(day, "checking", "brokerage", 30000, "To Investments")
        transfer(day, "checking", "roth", 50000, "To Investments")
        spend(day, "Charity", 2500, "Food Bank Fund", account="checking")
        spend(day, "Car Insurance", 11200, "RoadSure", account="checking")
    if day.day == 16:  # invest those transfers
        for key, ticker, cents in (("brokerage", "VTI", 30000), ("roth", "VXUS", 50000)):
            call("POST", f"/api/accounts/{acct[key]}/trades", date=day.isoformat(), kind="buy",
                 security_id=holdings[ticker], shares=shares_for(cents, price_on(ticker, day)), amount_cents=cents)
    if day.day == 28:  # 401k payroll contribution for the month (never passes through checking)
        trust_price *= 1 + rng.gauss(0.006, 0.02)
        call("POST", f"/api/accounts/{acct['k401']}/trades", date=day.isoformat(), kind="contribution",
             security_id=holdings["TRUST2060"], shares=f"{750 / trust_price:.4f}", amount_cents=75000)
    if day.day == 20 and card_balance > 0:  # pay the card in full
        transfer(day, "checking", "card", card_balance, "Credit Card Payment")
        card_balance = 0

    # Everyday life, with a little randomness.
    if day.weekday() in (5, 6) and rng.random() < 0.8:
        spend(day, "Groceries", money(55, 145))
    if rng.random() < 0.22 + (0.18 if day.weekday() >= 4 else 0):  # more dining out on weekends
        spend(day, "Dining Out", money(14, 68))
    if day.weekday() < 5 and rng.random() < 0.35:
        spend(day, "Coffee", money(4, 7))
    if rng.random() < 0.11:
        spend(day, "Gas", money(32, 58))
    if rng.random() < 0.04:
        spend(day, "Rideshare", money(12, 35))
    if rng.random() < 0.08:
        sub = rng.choice(["Clothing", "Home", "Clothing", "Electronics"])
        cents = money(20, 140) if sub != "Electronics" else money(60, 450)
        spend(day, sub, cents)
        if rng.random() < 0.12:  # sometimes it goes back
            refund_day = min(day + dt.timedelta(days=rng.randint(3, 14)), TODAY)
            call("POST", "/api/transactions", account_id=acct["card"], date=refund_day.isoformat(),
                 amount_cents=cents, payee=pick(sub), category_id=cat[sub], notes="Returned")
            card_balance -= cents
    if rng.random() < 0.05:
        spend(day, rng.choice(["Movies", "Games", "Concerts"]), money(12, 95))
    if rng.random() < 0.025:
        spend(day, "Pharmacy", money(8, 40))
    if day.month == 12 and 1 <= day.day <= 22 and rng.random() < 0.18:
        spend(day, "Gifts", money(25, 110), rng.choice(["Threadline", "GadgetHub", "NestGoods", "Bookworm Books"]))
    # Two trips a year: spring and late summer.
    if (day.month, day.day) in ((4, 10), (8, 22)):
        spend(day, "Flights", money(280, 520), "SkyHigh Airlines")
        spend(day + dt.timedelta(days=0), "Hotels", money(420, 900), "Harbor View Hotel")

# Card payment for whatever's left, and this month's reconciles so the checklist starts tidy.
balances = {a["id"]: a["balance_cents"] for a in call("GET", "/api/accounts")}
for key in ("checking", "savings", "card"):
    call("POST", f"/api/accounts/{acct[key]}/reconcile", date=TODAY.isoformat(), balance_cents=balances[acct[key]])

# ---- goals, budgets, retirement ----

call("POST", "/api/goals", name="Emergency fund", account_id=acct["savings"], target_cents=1500000)
call("POST", "/api/goals", name="New laptop", account_id=acct["savings"], target_cents=220000,
     target_date=dt.date(TODAY.year + 1, 3, 1).isoformat())
call("POST", "/api/goals", name="Japan trip", account_id=acct["savings"], target_cents=600000)
budget_month = dt.date(TODAY.year, 1, 1).isoformat()
for name, cents in (("Food", 75000), ("Shopping", 30000), ("Entertainment", 12000), ("Dining Out", 40000),
                    ("Bills & Utilities", 26000)):
    call("PUT", f"/api/budgets/{cat[name]}", month=budget_month, amount_cents=cents)
call("PUT", "/api/retirement/settings", birth_year=1997, retire_age=55, withdrawal_rate_bp=400, real_return_bp=700,
     volatility_bp=1500, spending_override_cents=None, contribution_override_cents=None, k401_yearly_cents=900000)
call("POST", f"/api/securities/{holdings['TRUST2060']}/prices", date=TODAY.isoformat(), price=f"{trust_price:.2f}")

count = len(call("GET", "/api/transactions"))
print(f"Demo data ready in {DATABASE}: {count} transactions from {START} to {TODAY}.")
