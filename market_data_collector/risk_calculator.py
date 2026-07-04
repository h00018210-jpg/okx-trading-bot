"""Risk sizing helpers for manual OKX HYPE analysis.

This module never places orders. It only calculates reference values for
human review.
"""

from __future__ import annotations


def calculate_position_size(entry_price, stop_price, max_loss_usdt, leverage):
    """Calculate max notional, margin, and estimated loss from a stop distance.

    If entry or stop is missing/invalid, return a non-throwing template payload.
    """
    if entry_price in (None, "") or stop_price in (None, ""):
        return {
            "status": "template_only",
            "message": "Provide entry_price and stop_price to calculate position size.",
            "formula": {
                "stop_distance_pct": "abs(entry_price - stop_price) / entry_price",
                "max_notional": "max_loss_usdt / stop_distance_pct",
                "required_margin": "max_notional / leverage",
                "estimated_loss": "max_notional * stop_distance_pct",
            },
        }

    try:
        entry = float(entry_price)
        stop = float(stop_price)
        loss = float(max_loss_usdt)
        lev = float(leverage)
        if entry <= 0 or lev <= 0:
            raise ValueError("entry_price and leverage must be positive")
        stop_distance_pct = abs(entry - stop) / entry
        if stop_distance_pct <= 0:
            raise ValueError("stop distance must be greater than zero")
        max_notional = loss / stop_distance_pct
        required_margin = max_notional / lev
        estimated_loss = max_notional * stop_distance_pct
        return {
            "status": "calculated",
            "entry_price": entry,
            "stop_price": stop,
            "max_loss_usdt": loss,
            "leverage": lev,
            "stop_distance_pct": stop_distance_pct,
            "max_notional": max_notional,
            "required_margin": required_margin,
            "estimated_loss": estimated_loss,
        }
    except (TypeError, ValueError) as exc:
        return {"status": "template_only", "error": str(exc)}
