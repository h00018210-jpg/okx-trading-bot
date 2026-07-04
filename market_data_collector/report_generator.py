"""Markdown report rendering for OKX HYPE snapshots."""

from __future__ import annotations


def fmt(value, missing="数据缺失"):
    if value in (None, ""):
        return missing
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def render_report(snapshot):
    ticker = snapshot.get("ticker") or {}
    funding = snapshot.get("funding") or {}
    oi = snapshot.get("open_interest") or {}
    ob = snapshot.get("order_book_summary") or {}
    trades = snapshot.get("trades_summary") or {}
    account = snapshot.get("account") or {}
    positions = snapshot.get("positions") or []
    risk = snapshot.get("risk_config") or {}
    pos = positions[0] if positions else {}

    lines = [
        "# OKX HYPE-USDT-SWAP Market Snapshot", "",
        "## 1. Basic Info",
        f"- Timestamp: {fmt(snapshot.get('timestamp'))}",
        f"- Symbol: {fmt(snapshot.get('symbol'))}",
        f"- Current Price: {fmt(ticker.get('last'))}",
        f"- 24H High: {fmt(ticker.get('high24h'))}",
        f"- 24H Low: {fmt(ticker.get('low24h'))}",
        f"- 24H Volume: {fmt(ticker.get('vol24h'))}",
        f"- Funding Rate: {fmt(funding.get('fundingRate'))}",
        f"- Open Interest: {fmt(oi.get('oi'))}", "",
        "## 2. Multi-Timeframe Structure", "",
    ]
    for label, key in (("1M", "1m"), ("5M", "5m"), ("15M", "15m"), ("1H", "1h")):
        tf = (snapshot.get("timeframes") or {}).get(key, {}).get("indicators", {})
        lines += [
            f"### {label}",
            f"- Trend: {fmt(tf.get('trend'))}",
            f"- EMA20: {fmt(tf.get('ema20'))}",
            f"- EMA50: {fmt(tf.get('ema50'))}",
            f"- EMA200: {fmt(tf.get('ema200'))}",
            f"- VWAP: {fmt(tf.get('vwap'))}",
            f"- ATR14: {fmt(tf.get('atr14'))}",
            f"- RSI14: {fmt(tf.get('rsi14'))}",
            f"- Recent High: {fmt(tf.get('recent_swing_high'))}",
            f"- Recent Low: {fmt(tf.get('recent_swing_low'))}",
            f"- Volume Spike Ratio: {fmt(tf.get('volume_spike_ratio'))}", "",
        ]
    lines += [
        "## 3. Order Book",
        f"- Best Bid: {fmt(ob.get('best_bid'))}",
        f"- Best Ask: {fmt(ob.get('best_ask'))}",
        f"- Spread: {fmt(ob.get('spread'))}",
        f"- Top 20 Bid Notional: {fmt(ob.get('top_20_bid_notional'))}",
        f"- Top 20 Ask Notional: {fmt(ob.get('top_20_ask_notional'))}",
        f"- Bid/Ask Imbalance: {fmt(ob.get('bid_ask_imbalance'))}",
        f"- Large Bid Walls: {fmt(ob.get('large_bid_walls'))}",
        f"- Large Ask Walls: {fmt(ob.get('large_ask_walls'))}", "",
        "## 4. Recent Trades",
        f"- Buy Volume: {fmt(trades.get('recent_buy_volume'))}",
        f"- Sell Volume: {fmt(trades.get('recent_sell_volume'))}",
        f"- Buy/Sell Ratio: {fmt(trades.get('aggressive_buy_sell_ratio'))}",
        f"- Approx OKX CVD: {fmt(trades.get('approx_okx_cvd'))}",
        "  - Note: This is an OKX single-exchange approximate CVD from recent trades, not global market CVD.",
        f"- Large Trades: {fmt(trades.get('large_trades'))}", "",
        "## 5. Account / Position",
        f"- Account Equity: {fmt(account.get('account_equity'))}",
        f"- Available Balance: {fmt(account.get('available_balance'))}",
        f"- Current Position: {fmt(pos.get('pos') or pos.get('position'))}",
        f"- Side: {fmt(pos.get('posSide') or pos.get('side'))}",
        f"- Entry: {fmt(pos.get('avgPx') or pos.get('entry_price'))}",
        f"- Leverage: {fmt(pos.get('lever') or pos.get('leverage'))}",
        f"- Margin Mode: {fmt(pos.get('mgnMode') or pos.get('margin_mode'))}",
        f"- Liquidation Price: {fmt(pos.get('liqPx') or pos.get('liquidation_price'))}",
        f"- Unrealized PnL: {fmt(pos.get('upl') or pos.get('unrealized_pnl'))}", "",
        "## 6. Risk Config",
        f"- Max Loss Per Trade: {fmt(risk.get('max_loss_per_trade'))}",
        f"- Max Daily Loss: {fmt(risk.get('max_daily_loss'))}",
        f"- Preferred Leverage: {fmt(risk.get('preferred_leverage'))}",
        f"- Leverage Cap: {fmt(risk.get('leverage_cap'))}",
        f"- Margin Mode: {fmt(risk.get('margin_mode'))}", "",
        "## 7. Missing Data",
        "- Liquidation heatmap: missing",
        "- Global CVD: missing",
        "- Cross-exchange long/short ratio: missing",
        "- External liquidation map: missing",
    ]
    for item in snapshot.get("missing_data", []):
        lines.append(f"- {item}")
    reliability = "OKX-only; partial" if snapshot.get("missing_data") else "OKX-only; complete for requested OKX endpoints"
    lines += ["", "## 8. Data Quality", f"- Reliability: {reliability}", "- Notes: No automatic orders are placed. Missing external analytics are intentionally marked missing.", ""]
    return "\n".join(lines)
