#!/usr/bin/env python3
"""Collect an OKX-only HYPE market snapshot and render JSON/Markdown outputs.

Read-only by design: this script never creates, amends, or cancels orders.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from indicators import calculate_timeframe_indicators
from okx_client import CCXTOKXClient, OKXClient
from report_generator import render_report
from risk_calculator import calculate_position_size

BASE_DIR = Path(__file__).resolve().parent


def load_env(path=BASE_DIR / ".env"):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def default_config():
    return {
        "symbol": "HYPE-USDT-SWAP",
        "source": "OKX",
        "output_dir": str(BASE_DIR / "output"),
        "data_source_priority": ["okx_rest", "ccxt"],
        "collection": {
            "candle_limit": 180,
            "order_book_depth": 20,
            "trades_limit": 100,
            "timeframes": {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H"},
        },
        "risk": {
            "account_equity": 100,
            "max_loss_per_trade": 2,
            "max_daily_loss": 5,
            "leverage_cap": 15,
            "preferred_leverage": 10,
            "margin_mode": "isolated",
        },
    }


def deep_merge(base, override):
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path=BASE_DIR / "config.yaml"):
    config = default_config()
    if not path.exists() or importlib.util.find_spec("yaml") is None:
        return config
    import yaml

    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    return deep_merge(config, loaded)


def safe_call(label, missing_data, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - collection should continue on endpoint failures.
        missing_data.append(f"{label}: missing ({exc})")
        return None



def fetch_with_fallback(label, missing_data, clients, priority, method_name, *args):
    for source in priority:
        client = clients.get(source)
        if client is None:
            missing_data.append(f"{label}: missing (source={source}; endpoint={method_name}; params={args}; status_code=None; response_body=client not configured)")
            continue
        result = safe_call(f"{label} via {source}", missing_data, getattr(client, method_name), *args)
        if result:
            return result
    return None

def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize_order_book(book_payload):
    if not book_payload:
        return {}
    book = book_payload[0]
    bids = book.get("bids", [])[:20]
    asks = book.get("asks", [])[:20]

    def notional(level):
        price = to_float(level[0])
        size = to_float(level[1])
        return (price or 0) * (size or 0)

    bid_notional = sum(notional(level) for level in bids)
    ask_notional = sum(notional(level) for level in asks)
    all_notionals = [notional(level) for level in bids + asks]
    avg_notional = sum(all_notionals) / len(all_notionals) if all_notionals else 0
    wall_threshold = avg_notional * 2 if avg_notional else 0
    best_bid = to_float(bids[0][0]) if bids else None
    best_ask = to_float(asks[0][0]) if asks else None
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": (best_ask - best_bid) if best_bid is not None and best_ask is not None else None,
        "top_20_bid_notional": bid_notional,
        "top_20_ask_notional": ask_notional,
        "bid_ask_imbalance": (bid_notional - ask_notional) / (bid_notional + ask_notional) if (bid_notional + ask_notional) else None,
        "large_bid_walls": [level for level in bids if notional(level) >= wall_threshold],
        "large_ask_walls": [level for level in asks if notional(level) >= wall_threshold],
    }


def summarize_trades(trades):
    if not trades:
        return {}
    buy_volume = 0.0
    sell_volume = 0.0
    signed_cvd = 0.0
    enriched = []
    for trade in trades:
        size = to_float(trade.get("sz")) or 0.0
        price = to_float(trade.get("px")) or 0.0
        side = trade.get("side")
        if side == "buy":
            buy_volume += size
            signed_cvd += size
        elif side == "sell":
            sell_volume += size
            signed_cvd -= size
        enriched.append({**trade, "notional": price * size})
    avg_notional = sum(t["notional"] for t in enriched) / len(enriched) if enriched else 0
    threshold = avg_notional * 2 if avg_notional else 0
    return {
        "recent_buy_volume": buy_volume,
        "recent_sell_volume": sell_volume,
        "aggressive_buy_sell_ratio": buy_volume / sell_volume if sell_volume else None,
        "approx_okx_cvd": signed_cvd,
        "large_trades": [t for t in enriched if t["notional"] >= threshold],
        "note": "OKX single-exchange approximate CVD from recent trades, not global market CVD.",
    }


def normalize_account(balance_payload):
    if not balance_payload:
        return {}
    row = balance_payload[0]
    details = row.get("details", [])
    usdt = next((d for d in details if d.get("ccy") == "USDT"), {})
    return {"account_equity": row.get("totalEq"), "available_balance": usdt.get("availBal") or usdt.get("availEq")}


def main():
    load_env()
    config = load_config()
    symbol = config["symbol"]
    collection = config["collection"]
    risk_config = config["risk"]
    rest_client = OKXClient()
    ccxt_client = CCXTOKXClient()
    clients = {"okx_rest": rest_client, "ccxt": ccxt_client}
    priority = config.get("data_source_priority", ["okx_rest", "ccxt"])
    missing_data = []

    ticker_data = fetch_with_fallback("ticker", missing_data, clients, priority, "ticker", symbol)
    ticker = ticker_data[0] if ticker_data else {}

    timeframes = {}
    for tf, okx_bar in collection["timeframes"].items():
        candles = fetch_with_fallback(f"{tf} candles", missing_data, clients, priority, "candles", symbol, okx_bar, collection["candle_limit"])
        if candles is None:
            timeframes[tf] = {"candles": [], "indicators": {}}
            continue
        timeframes[tf] = {"candles": candles, "indicators": calculate_timeframe_indicators(candles)}

    book = fetch_with_fallback("order book", missing_data, clients, priority, "order_book", symbol, collection["order_book_depth"])
    trades = fetch_with_fallback("recent trades", missing_data, clients, priority, "trades", symbol, collection["trades_limit"])
    funding_data = fetch_with_fallback("funding rate", missing_data, clients, priority, "funding_rate", symbol)
    oi_data = fetch_with_fallback("open interest", missing_data, clients, priority, "open_interest", symbol)

    account = {}
    positions = []
    if rest_client.has_credentials:
        account = normalize_account(safe_call("account balance", missing_data, rest_client.account_balance) or [])
        positions = safe_call("positions", missing_data, rest_client.positions, symbol) or []
    else:
        missing_data.append("账户数据：缺失，未配置 API Key。")

    missing_data += [
        "Liquidation heatmap: missing",
        "Global CVD: missing",
        "Cross-exchange long/short ratio: missing",
        "External liquidation map: missing",
    ]

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "source": config["source"],
        "ticker": ticker,
        "timeframes": timeframes,
        "order_book_summary": summarize_order_book(book),
        "trades_summary": summarize_trades(trades),
        "funding": funding_data[0] if funding_data else {},
        "open_interest": oi_data[0] if oi_data else {},
        "account": account,
        "positions": positions,
        "risk_config": risk_config,
        "risk_template": calculate_position_size(None, None, risk_config["max_loss_per_trade"], risk_config["preferred_leverage"]),
        "missing_data": missing_data,
    }

    output_dir = Path(config.get("output_dir", BASE_DIR / "output"))
    if not output_dir.is_absolute():
        output_dir = BASE_DIR.parent / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest_snapshot.json").write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "latest_report.md").write_text(render_report(snapshot), encoding="utf-8")
    print(f"Wrote {output_dir / 'latest_snapshot.json'}")
    print(f"Wrote {output_dir / 'latest_report.md'}")


if __name__ == "__main__":
    main()
