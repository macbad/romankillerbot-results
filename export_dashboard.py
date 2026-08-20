"""Export closed-trade statistics for the public dashboard."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT.parent
DEFAULT_OUTPUT = ROOT / "docs" / "data" / "dashboard.json"
INITIAL_BALANCE = 250.0


def number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def read_trades(path: Path):
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def streaks(pnls):
    maximum = {"win": 0, "loss": 0}
    current_kind = None
    current_count = 0
    for pnl in pnls:
        kind = "win" if pnl >= 0 else "loss"
        current_count = current_count + 1 if kind == current_kind else 1
        current_kind = kind
        maximum[kind] = max(maximum[kind], current_count)
    return {
        "current_type": current_kind,
        "current_count": current_count if pnls else 0,
        "max_wins": maximum["win"],
        "max_losses": maximum["loss"],
    }


def drawdown(equity):
    peak = INITIAL_BALANCE
    maximum = maximum_pct = 0.0
    for value in equity:
        peak = max(peak, value)
        drop = peak - value
        maximum = max(maximum, drop)
        maximum_pct = max(maximum_pct, drop / peak * 100 if peak else 0.0)
    return maximum, maximum_pct


def export_dashboard(source=DEFAULT_SOURCE, output=DEFAULT_OUTPUT):
    source = Path(source)
    rows = read_trades(source / "SimLiveBotSimOnly_trades.csv")
    state = read_json(source / "SimLiveBotSimOnly_state.json")
    position = state.get("position") or {}
    open_entry_fee = number(position.get("entry_fee"))
    trades = []
    for row in rows:
        # Publishes closed-trade prices, but still excludes timestamps, size and strategy signals.
        trades.append({
            "trade_num": int(number(row.get("trade_num"))),
            "side": row.get("side", ""),
            "entry_price": number(row.get("entry_price")),
            "exit_price": number(row.get("exit_price")),
            "pnl": number(row.get("pnl")),
            "fee": number(row.get("fee")),
            "exit_reason": row.get("exit_reason", ""),
            "duration_secs": number(row.get("duration_secs")),
            "balance_after": number(row.get("balance_after"), INITIAL_BALANCE),
        })
    trades.sort(key=lambda trade: trade["trade_num"])

    pnls = [trade["pnl"] for trade in trades]
    wins = [pnl for pnl in pnls if pnl >= 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = [INITIAL_BALANCE] + [trade["balance_after"] for trade in trades]
    max_dd, max_dd_pct = drawdown(equity)
    exits = {"TP": 0, "SL": 0, "TIME": 0}
    sides = {"LONG": {"count": 0, "pnl": 0.0}, "SHORT": {"count": 0, "pnl": 0.0}}
    for trade in trades:
        exits[trade["exit_reason"]] = exits.get(trade["exit_reason"], 0) + 1
        if trade["side"] in sides:
            sides[trade["side"]]["count"] += 1
            sides[trade["side"]]["pnl"] += trade["pnl"]

    total = len(trades)
    realized = sum(pnls)
    generated = datetime.now(timezone.utc)
    payload = {
        "schema_version": 2,
        "generated_at": generated.isoformat().replace("+00:00", "Z"),
        "generated_epoch": generated.timestamp(),
        "mode": "TEST",
        "symbol": "BTCUSDT",
        "fee_model": "BTCUSDT 0.010% maker / 0.028% taker",
        "account": {
            "initial_balance": INITIAL_BALANCE,
            "balance": equity[-1],
            "realized_pnl": realized,
            "return_pct": realized / INITIAL_BALANCE * 100,
            "total_fees": sum(trade["fee"] for trade in trades) + open_entry_fee,
        },
        "statistics": {
            "trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": len(wins) / total * 100 if total else 0.0,
            "average_win": gross_profit / len(wins) if wins else 0.0,
            "average_loss": sum(losses) / len(losses) if losses else 0.0,
            "expectancy": realized / total if total else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else None,
            "best_trade": max(pnls, default=0.0),
            "worst_trade": min(pnls, default=0.0),
            "average_duration_secs": sum(t["duration_secs"] for t in trades) / total if total else 0.0,
            "max_drawdown": max_dd,
            "max_drawdown_pct": max_dd_pct,
            "streaks": streaks(pnls),
            "exit_counts": exits,
            "side_stats": sides,
        },
        "equity_curve": equity,
        "trades": trades,
    }

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, output)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=10.0)
    args = parser.parse_args()
    while True:
        payload = export_dashboard(args.source.resolve(), args.output.resolve())
        print(f"Public dashboard: {payload['statistics']['trades']} closed trades", flush=True)
        if not args.watch:
            break
        time.sleep(max(2.0, args.interval))


if __name__ == "__main__":
    main()
