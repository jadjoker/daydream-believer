import os
import json
import sqlite3
import random
import string
from typing import Dict, List, Optional
from datetime import datetime, timezone, date as date_type
import math

DB_PATH = os.getenv(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "simulator.db"),
)

DEFAULT_STATE: Dict = {
    "cash": 100_000.0,
    "startingBalance": 100_000.0,
    "positions": {},
    "trades": [],
}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS simulator (
                id INTEGER PRIMARY KEY,
                cash REAL NOT NULL,
                starting_balance REAL NOT NULL,
                positions TEXT NOT NULL,
                trades TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        c.execute("""
            INSERT OR IGNORE INTO simulator
                (id, cash, starting_balance, positions, trades, updated_at)
            VALUES (1, 100000, 100000, '{}', '[]', ?)
        """, (datetime.now(timezone.utc).isoformat(),))
        c.commit()


def _read() -> Dict:
    _init()
    with _conn() as c:
        row = c.execute("SELECT * FROM simulator WHERE id=1").fetchone()
    if not row:
        return dict(DEFAULT_STATE)
    return {
        "cash": row["cash"],
        "startingBalance": row["starting_balance"],
        "positions": json.loads(row["positions"]),
        "trades": json.loads(row["trades"]),
    }


def _write(state: Dict):
    with _conn() as c:
        c.execute("""
            UPDATE simulator
            SET cash=?, starting_balance=?, positions=?, trades=?, updated_at=?
            WHERE id=1
        """, (
            state["cash"],
            state["startingBalance"],
            json.dumps(state["positions"]),
            json.dumps(state["trades"]),
            datetime.now(timezone.utc).isoformat(),
        ))
        c.commit()


def _uid() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def get_state() -> Dict:
    return _read()


def buy(ticker: str, name: str, shares: float, price: float, thesis: str) -> Dict:
    state = _read()
    total = round(shares * price, 4)

    if shares <= 0:
        return {"ok": False, "error": "Shares must be > 0"}
    if total > state["cash"]:
        return {"ok": False, "error": f"Insufficient funds. Need ${total:.2f}, have ${state['cash']:.2f}"}

    t_upper = ticker.upper()
    pos = state["positions"].get(t_upper, {
        "ticker": t_upper, "name": name, "shares": 0.0, "avgCost": 0.0, "openTradeIds": [],
    })
    new_shares = pos["shares"] + shares
    new_avg = (pos["shares"] * pos["avgCost"] + shares * price) / new_shares
    trade_id = _uid()

    state["positions"][t_upper] = {
        **pos,
        "name": name,
        "shares": new_shares,
        "avgCost": round(new_avg, 6),
        "openTradeIds": pos["openTradeIds"] + [trade_id],
    }
    state["cash"] = round(state["cash"] - total, 4)
    state["trades"] = [{
        "id": trade_id, "ticker": t_upper, "name": name,
        "action": "buy", "shares": shares, "price": price, "total": total,
        "timestamp": datetime.now(timezone.utc).isoformat(), "thesis": thesis,
    }] + state["trades"]

    _write(state)
    return {"ok": True, "state": state}


def sell(ticker: str, name: str, shares: float, price: float, thesis: str) -> Dict:
    state = _read()
    t_upper = ticker.upper()
    pos = state["positions"].get(t_upper)

    if shares <= 0:
        return {"ok": False, "error": "Shares must be > 0"}
    if not pos or pos["shares"] < shares:
        have = pos["shares"] if pos else 0
        return {"ok": False, "error": f"Not enough shares. Have {have}, selling {shares}"}

    total = round(shares * price, 4)
    cost_basis = shares * pos["avgCost"]
    realized = round(total - cost_basis, 4)
    realized_pct = round((realized / cost_basis) * 100, 4) if cost_basis else 0
    outcome = "win" if realized > 0 else ("loss" if realized < 0 else "breakeven")
    trade_id = _uid()
    now = datetime.now(timezone.utc).isoformat()

    remaining = pos["shares"] - shares
    if remaining <= 0.0001:
        del state["positions"][t_upper]
    else:
        state["positions"][t_upper] = {**pos, "shares": round(remaining, 6)}

    state["cash"] = round(state["cash"] + total, 4)
    state["trades"] = [{
        "id": trade_id, "ticker": t_upper, "name": name,
        "action": "sell", "shares": shares, "price": price, "total": total,
        "timestamp": now, "thesis": thesis,
        "closePrice": price, "closeTimestamp": now,
        "realizedPnl": realized, "realizedPnlPct": realized_pct, "outcome": outcome,
    }] + state["trades"]

    _write(state)
    return {"ok": True, "state": state}


def add_funds(amount: float) -> Dict:
    state = _read()
    state["cash"] = round(state["cash"] + amount, 4)
    state["startingBalance"] = round(state["startingBalance"] + amount, 4)
    _write(state)
    return state


def reset() -> Dict:
    state = {"cash": 100_000.0, "startingBalance": 100_000.0, "positions": {}, "trades": []}
    _write(state)
    _init_recurring()
    with _conn() as c:
        c.execute("UPDATE recurring_plans SET active=0")
        c.commit()
    return state


# ─── Recurring Investment Plans ───────────────────────────────────────────────

def _init_recurring():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS recurring_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL,
                frequency TEXT NOT NULL,
                start_date TEXT NOT NULL,
                last_executed_date TEXT,
                total_invested REAL NOT NULL DEFAULT 0,
                num_executions INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        c.commit()


def _next_due_date(frequency: str, last_date: str) -> str:
    import calendar
    from datetime import date as dt, timedelta
    d = dt.fromisoformat(last_date)
    if frequency == "weekly":
        d = d + timedelta(days=7)
    elif frequency == "biweekly":
        d = d + timedelta(days=14)
    else:  # monthly
        month = d.month % 12 + 1
        year = d.year + (1 if d.month == 12 else 0)
        max_day = calendar.monthrange(year, month)[1]
        d = dt(year, month, min(d.day, max_day))
    # Advance past weekends to next Monday — markets are closed Sat/Sun
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def get_recurring_plans() -> List[Dict]:
    _init_recurring()
    from datetime import date as dt
    today = dt.today().strftime("%Y-%m-%d")
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM recurring_plans WHERE active=1 ORDER BY created_at DESC"
        ).fetchall()
    plans = []
    for row in rows:
        plan = dict(row)
        last = plan.get("last_executed_date")
        next_due = _next_due_date(plan["frequency"], last) if last else plan["start_date"]
        plan["next_due_date"] = next_due
        plan["is_due"] = next_due <= today
        plans.append(plan)
    return plans


def add_recurring_plan(ticker: str, name: str, amount: float, frequency: str, start_date: str) -> Dict:
    _init_recurring()
    with _conn() as c:
        cur = c.execute("""
            INSERT INTO recurring_plans (ticker, name, amount, frequency, start_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ticker.upper(), name, amount, frequency, start_date, datetime.now(timezone.utc).isoformat()))
        c.commit()
        plan_id = cur.lastrowid
    plans = get_recurring_plans()
    return next((p for p in plans if p["id"] == plan_id), {})


def backfill_recurring_plan(plan_id: int, ohlcv: List[Dict]) -> Dict:
    """Execute all historical buys from a plan's start date using real OHLCV prices."""
    _init_recurring()
    with _conn() as c:
        row = c.execute("SELECT * FROM recurring_plans WHERE id=?", (plan_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "Plan not found"}

    plan = dict(row)
    frequency = plan["frequency"]
    start_date = plan["start_date"]
    amount = plan["amount"]
    ticker = plan["ticker"]
    name = plan["name"]

    prices = {r["date"]: r["close"] for r in ohlcv if r["date"] >= start_date}
    dates = sorted(prices.keys())
    if not dates:
        return {"ok": False, "error": "No price data for backfill range"}

    # Same schedule logic as compute_dca
    def is_buy_date(idx: int) -> bool:
        if idx == 0:
            return True
        if frequency == "weekly":
            return idx % 5 == 0
        if frequency == "biweekly":
            return idx % 10 == 0
        if frequency == "monthly":
            return idx % 21 == 0
        return False

    purchase_dates = [d for i, d in enumerate(dates) if is_buy_date(i)]
    if not purchase_dates:
        return {"ok": False, "error": "No purchase dates found in range"}

    state = _read()
    total_invested = float(plan.get("total_invested") or 0)
    num_executions = int(plan.get("num_executions") or 0)
    last_executed = plan.get("last_executed_date")
    executions = []

    for pd in purchase_dates:
        price = prices[pd]
        if price <= 0:
            continue
        shares = amount / price
        total = round(shares * price, 4)

        t_upper = ticker.upper()
        pos = state["positions"].get(t_upper, {
            "ticker": t_upper, "name": name, "shares": 0.0, "avgCost": 0.0, "openTradeIds": [],
        })
        new_shares = pos["shares"] + shares
        new_avg = (pos["shares"] * pos["avgCost"] + shares * price) / new_shares
        trade_id = _uid()

        state["positions"][t_upper] = {
            **pos,
            "name": name,
            "shares": round(new_shares, 6),
            "avgCost": round(new_avg, 6),
            "openTradeIds": pos.get("openTradeIds", []) + [trade_id],
        }
        state["cash"] = round(state["cash"] - total, 4)
        state["trades"].append({
            "id": trade_id, "ticker": t_upper, "name": name,
            "action": "buy", "shares": round(shares, 6), "price": round(price, 4), "total": total,
            "timestamp": pd + "T09:30:00+00:00",
            "thesis": f"DCA {frequency} · backfill",
            "isDca": True, "planId": plan_id,
        })
        total_invested += amount
        num_executions += 1
        last_executed = pd
        executions.append({"date": pd, "price": round(price, 4), "shares": round(shares, 6), "total": total})

    state["trades"] = sorted(state["trades"], key=lambda t: t["timestamp"], reverse=True)
    _write(state)

    with _conn() as c:
        c.execute("""
            UPDATE recurring_plans SET last_executed_date=?, total_invested=?, num_executions=?
            WHERE id=?
        """, (last_executed, round(total_invested, 4), num_executions, plan_id))
        c.commit()

    cash_warning = state["cash"] < 0
    return {
        "ok": True,
        "executions": executions,
        "total_invested": round(total_invested, 4),
        "num_executions": num_executions,
        "cash_warning": cash_warning,
        "state": state,
    }


def execute_recurring_plan(plan_id: int, price: float, name: str) -> Dict:
    """Execute the next due buy at current live price."""
    _init_recurring()
    from datetime import date as dt
    today = dt.today().strftime("%Y-%m-%d")

    with _conn() as c:
        row = c.execute("SELECT * FROM recurring_plans WHERE id=? AND active=1", (plan_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "Plan not found"}

    plan = dict(row)
    last = plan.get("last_executed_date")
    next_due = _next_due_date(plan["frequency"], last) if last else plan["start_date"]

    if next_due > today:
        return {"ok": False, "error": f"Next buy not due until {next_due}"}

    if price <= 0:
        return {"ok": False, "error": "Invalid price"}

    amount = plan["amount"]
    ticker = plan["ticker"]
    shares = amount / price
    result = buy(ticker, name or plan["name"], shares, price, f"DCA {plan['frequency']}")
    if not result.get("ok"):
        return result

    state = result["state"]
    if state["trades"]:
        state["trades"][0]["isDca"] = True
        state["trades"][0]["planId"] = plan_id
        _write(state)

    total_invested = float(plan.get("total_invested") or 0) + amount
    num_executions = int(plan.get("num_executions") or 0) + 1

    with _conn() as c:
        c.execute("""
            UPDATE recurring_plans SET last_executed_date=?, total_invested=?, num_executions=?
            WHERE id=?
        """, (today, round(total_invested, 4), num_executions, plan_id))
        c.commit()

    return {"ok": True, "state": state, "shares_bought": round(shares, 6), "price": price}


def delete_recurring_plan(plan_id: int) -> Dict:
    _init_recurring()
    with _conn() as c:
        c.execute("UPDATE recurring_plans SET active=0 WHERE id=?", (plan_id,))
        c.commit()
    return {"ok": True}


def compute_dca(
    ohlcv: List[Dict],
    spy_ohlcv: List[Dict],
    initial: float,
    recurring: float,
    frequency: str,   # "weekly" | "biweekly" | "monthly" | "none"
) -> Optional[Dict]:
    """
    Simulate dollar-cost averaging over historical price data.
    Returns a portfolio growth series plus a SPY buy-and-hold comparison.
    """
    if not ohlcv:
        return None

    # Build date → close price lookups
    prices = {row["date"]: row["close"] for row in ohlcv}
    spy_prices = {row["date"]: row["close"] for row in spy_ohlcv}
    dates = sorted(prices.keys())
    if not dates:
        return None

    # Determine purchase dates based on frequency
    def is_purchase_date(date_str: str, idx: int) -> bool:
        if frequency == "none":
            return idx == 0
        if idx == 0:
            return True  # always buy on first date (initial)
        if frequency == "weekly":
            # every 5 trading days ≈ 1 week
            return idx % 5 == 0
        if frequency == "biweekly":
            return idx % 10 == 0
        if frequency == "monthly":
            return idx % 21 == 0
        return False

    # Simulate ticker DCA
    shares = 0.0
    total_invested = 0.0
    portfolio_series: List[Dict] = []

    for idx, d in enumerate(dates):
        price = prices[d]
        if is_purchase_date(d, idx):
            amount = initial if idx == 0 else recurring
            if amount > 0 and price > 0:
                new_shares = amount / price
                shares += new_shares
                total_invested += amount

        portfolio_value = round(shares * price, 2)
        portfolio_series.append({
            "date": d,
            "value": portfolio_value,
            "invested": round(total_invested, 2),
        })

    # Simulate SPY buy-and-hold with same cash flows
    spy_dates = sorted(spy_prices.keys())
    spy_shares = 0.0
    spy_total_invested = 0.0
    spy_series: List[Dict] = []
    spy_date_set = set(spy_dates)

    for idx, d in enumerate(dates):
        # Find closest SPY price (same date or next available)
        spy_price = spy_prices.get(d)
        if spy_price is None:
            # use last known SPY price
            for prev_d in reversed(dates[:idx]):
                if prev_d in spy_prices:
                    spy_price = spy_prices[prev_d]
                    break
        if spy_price is None:
            spy_series.append({"date": d, "value": 0.0, "invested": 0.0})
            continue

        if is_purchase_date(d, idx):
            amount = initial if idx == 0 else recurring
            if amount > 0 and spy_price > 0:
                spy_shares += amount / spy_price
                spy_total_invested += amount

        spy_series.append({
            "date": d,
            "value": round(spy_shares * spy_price, 2),
            "invested": round(spy_total_invested, 2),
        })

    final = portfolio_series[-1] if portfolio_series else None
    spy_final = spy_series[-1] if spy_series else None

    if not final or final["invested"] == 0:
        return None

    total_return_pct = round((final["value"] - final["invested"]) / final["invested"] * 100, 2)
    spy_return_pct = round((spy_final["value"] - spy_final["invested"]) / spy_final["invested"] * 100, 2) if spy_final and spy_final["invested"] else 0

    # Compute max drawdown on portfolio
    peak = 0.0
    max_drawdown = 0.0
    for row in portfolio_series:
        peak = max(peak, row["value"])
        if peak > 0:
            dd = (peak - row["value"]) / peak * 100
            max_drawdown = max(max_drawdown, dd)

    return {
        "series": portfolio_series,
        "spy_series": spy_series,
        "total_invested": round(final["invested"], 2),
        "final_value": final["value"],
        "total_return_pct": total_return_pct,
        "total_return_dollars": round(final["value"] - final["invested"], 2),
        "spy_final_value": spy_final["value"] if spy_final else 0,
        "spy_return_pct": spy_return_pct,
        "spy_return_dollars": round((spy_final["value"] - spy_final["invested"]) if spy_final else 0, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "num_purchases": sum(1 for i, d in enumerate(dates) if is_purchase_date(d, i)),
    }
