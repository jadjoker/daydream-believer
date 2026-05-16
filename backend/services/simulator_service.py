import os
import json
import sqlite3
import random
import string
from typing import Dict
from datetime import datetime, timezone

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
    return state
