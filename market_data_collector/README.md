# OKX HYPE Market Data Collector

Read-only OKX-only collector for `HYPE-USDT-SWAP`. The module gathers public market data, optionally reads account/position information when API credentials are configured, calculates local indicators, and writes files for human or ChatGPT analysis.

> This module is **not** an auto-trading system. It never places, amends, or cancels orders.

## Files

- `collect_hype_snapshot.py` — main entry point.
- `okx_client.py` — small read-only OKX REST client.
- `indicators.py` — EMA, VWAP, ATR, RSI, volume, range, and swing calculations.
- `risk_calculator.py` — position-size reference calculator.
- `report_generator.py` — Markdown report renderer.
- `config.yaml` — symbol, collection, and risk defaults.
- `.env.example` — environment variable names only.
- `output/latest_snapshot.json` — generated JSON snapshot.
- `output/latest_report.md` — generated Markdown report.

## Requirements

- Python 3.9+ on macOS or Linux.
- Network access to `https://www.okx.com`.
- No third-party Python packages are required for the first version.

## Configuration

Copy the example file if you want private account/position reads:

```bash
cd market_data_collector
cp .env.example .env
```

Then fill in `.env` locally:

```bash
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_API_PASSPHRASE=your_passphrase
OKX_SIMULATED_TRADING=1
```

Do not commit `.env`. If these variables are absent, the collector skips account reads and reports:

```text
账户数据：缺失，未配置 API Key。
```

## Running

From the repository root:

```bash
python3 market_data_collector/collect_hype_snapshot.py
```

Outputs are written to:

```text
market_data_collector/output/latest_snapshot.json
market_data_collector/output/latest_report.md
```

## Data Collected

Public OKX data:

- Ticker/current price, 24h high/low/volume.
- 1m, 5m, 15m, and 1h candles; default 180 rows each.
- Order book; default top 20 levels.
- Recent trades; default 100 rows.
- Funding rate.
- Open interest when available from OKX.

Optional private OKX account data:

- Account equity.
- Available USDT balance.
- Current positions, side, entry price, leverage, margin mode, liquidation price, and unrealized PnL when returned by OKX.

Unavailable external analytics are intentionally marked as missing:

- Liquidation heatmap.
- Global CVD.
- Cross-exchange long/short ratio.
- External liquidation map.

## Local Indicators

For each configured timeframe, the collector calculates:

- EMA20, EMA50, EMA200.
- VWAP.
- ATR14.
- RSI14.
- Volume moving average.
- Volume spike ratio.
- Recent swing high/low.
- Full range high/low.

## Risk Defaults

`config.yaml` defaults:

- `account_equity`: `100` USDT.
- `max_loss_per_trade`: `2` USDT.
- `max_daily_loss`: `5` USDT.
- `leverage_cap`: `15`.
- `preferred_leverage`: `10`.
- `margin_mode`: `isolated`.

The sizing helper is only a reference calculator:

```python
calculate_position_size(entry_price, stop_price, max_loss_usdt, leverage)
```

If `entry_price` or `stop_price` is missing, it returns a template payload instead of raising.

## Failure Behavior

Each OKX endpoint is collected independently. If an endpoint fails, the script records the item in `missing_data`, continues collecting the rest of the snapshot, and still writes both output files.
