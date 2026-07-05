"""Local market indicators for OKX candle data."""

from __future__ import annotations


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ema(values, period):
    nums = [_to_float(v) for v in values]
    nums = [v for v in nums if v is not None]
    if not nums:
        return None
    alpha = 2 / (period + 1)
    result = nums[0]
    for value in nums[1:]:
        result = (value * alpha) + (result * (1 - alpha))
    return result


def sma(values, period=None):
    nums = [_to_float(v) for v in values]
    nums = [v for v in nums if v is not None]
    if not nums:
        return None
    sample = nums[-period:] if period else nums
    return sum(sample) / len(sample) if sample else None


def vwap(candles):
    total_pv = 0.0
    total_volume = 0.0
    for candle in candles:
        high = _to_float(candle.get("high"))
        low = _to_float(candle.get("low"))
        close = _to_float(candle.get("close"))
        volume = _to_float(candle.get("volume"))
        if None in (high, low, close, volume):
            continue
        typical = (high + low + close) / 3
        total_pv += typical * volume
        total_volume += volume
    return total_pv / total_volume if total_volume else None


def atr(candles, period=14):
    if len(candles) < 2:
        return None
    true_ranges = []
    previous_close = None
    for candle in candles:
        high = _to_float(candle.get("high"))
        low = _to_float(candle.get("low"))
        close = _to_float(candle.get("close"))
        if None in (high, low, close):
            continue
        if previous_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(tr)
        previous_close = close
    return sma(true_ranges, period)


def rsi(values, period=14):
    closes = [_to_float(v) for v in values]
    closes = [v for v in closes if v is not None]
    if len(closes) <= period:
        return None
    gains = []
    losses = []
    for current, previous in zip(closes[1:], closes[:-1]):
        change = current - previous
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sma(gains[-period:])
    avg_loss = sma(losses[-period:])
    if avg_gain is None or avg_loss is None:
        return None
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_timeframe_indicators(candles):
    closes = [_to_float(c.get("close")) for c in candles]
    volumes = [_to_float(c.get("volume")) for c in candles]
    highs = [_to_float(c.get("high")) for c in candles]
    lows = [_to_float(c.get("low")) for c in candles]
    closes = [v for v in closes if v is not None]
    volumes = [v for v in volumes if v is not None]
    highs = [v for v in highs if v is not None]
    lows = [v for v in lows if v is not None]
    volume_ma = sma(volumes, 20)
    latest_volume = volumes[-1] if volumes else None
    volume_spike_ratio = latest_volume / volume_ma if volume_ma else None
    recent_window = 20
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    trend = "data_missing"
    if closes and ema20 is not None and ema50 is not None:
        trend = "bullish" if closes[-1] > ema20 > ema50 else "bearish" if closes[-1] < ema20 < ema50 else "mixed"
    return {
        "candle_count": len(candles),
        "trend": trend,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "vwap": vwap(candles),
        "atr14": atr(candles, 14),
        "rsi14": rsi(closes, 14),
        "volume_ma": volume_ma,
        "volume_spike_ratio": volume_spike_ratio,
        "recent_swing_high": max(highs[-recent_window:]) if highs else None,
        "recent_swing_low": min(lows[-recent_window:]) if lows else None,
        "range_high": max(highs) if highs else None,
        "range_low": min(lows) if lows else None,
    }
