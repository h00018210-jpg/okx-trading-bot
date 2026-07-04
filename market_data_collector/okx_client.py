"""Small OKX REST client for read-only market/account collection."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from urllib import error, parse, request


class OKXClient:
    BASE_URL = "https://www.okx.com"

    def __init__(self, api_key=None, api_secret=None, passphrase=None, simulated=False, timeout=10):
        self.api_key = api_key or os.getenv("OKX_API_KEY")
        self.api_secret = api_secret or os.getenv("OKX_API_SECRET")
        self.passphrase = passphrase or os.getenv("OKX_API_PASSPHRASE")
        self.simulated = simulated or os.getenv("OKX_SIMULATED_TRADING", "").lower() in {"1", "true", "yes"}
        self.timeout = timeout

    @property
    def has_credentials(self):
        return bool(self.api_key and self.api_secret and self.passphrase)

    def _timestamp(self):
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _sign(self, timestamp, method, path_with_query, body=""):
        message = f"{timestamp}{method.upper()}{path_with_query}{body}"
        digest = hmac.new(self.api_secret.encode(), message.encode(), hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def request(self, method, path, params=None, private=False):
        params = params or {}
        query = f"?{parse.urlencode(params)}" if params else ""
        path_with_query = f"{path}{query}"
        headers = {"Content-Type": "application/json"}
        if private:
            if not self.has_credentials:
                raise RuntimeError("OKX API credentials are not configured")
            timestamp = self._timestamp()
            headers.update({
                "OK-ACCESS-KEY": self.api_key,
                "OK-ACCESS-SIGN": self._sign(timestamp, method, path_with_query),
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": self.passphrase,
            })
            if self.simulated:
                headers["x-simulated-trading"] = "1"
        req = request.Request(self.BASE_URL + path_with_query, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode())
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"OKX request failed for {path}: {exc}") from exc
        if payload.get("code") != "0":
            raise RuntimeError(f"OKX API error for {path}: {payload.get('msg') or payload}")
        return payload.get("data", [])

    def ticker(self, inst_id):
        return self.request("GET", "/api/v5/market/ticker", {"instId": inst_id})

    def candles(self, inst_id, bar, limit=180):
        data = self.request("GET", "/api/v5/market/candles", {"instId": inst_id, "bar": bar, "limit": limit})
        rows = []
        for row in reversed(data):
            rows.append({
                "timestamp": row[0], "open": row[1], "high": row[2], "low": row[3],
                "close": row[4], "volume": row[5], "volume_ccy": row[6] if len(row) > 6 else None,
                "volume_ccy_quote": row[7] if len(row) > 7 else None, "confirm": row[8] if len(row) > 8 else None,
            })
        return rows

    def order_book(self, inst_id, depth=20):
        return self.request("GET", "/api/v5/market/books", {"instId": inst_id, "sz": depth})

    def trades(self, inst_id, limit=100):
        return self.request("GET", "/api/v5/market/trades", {"instId": inst_id, "limit": limit})

    def funding_rate(self, inst_id):
        return self.request("GET", "/api/v5/public/funding-rate", {"instId": inst_id})

    def open_interest(self, inst_id):
        return self.request("GET", "/api/v5/public/open-interest", {"instId": inst_id})

    def account_balance(self):
        return self.request("GET", "/api/v5/account/balance", private=True)

    def positions(self, inst_id=None):
        params = {"instId": inst_id} if inst_id else {}
        return self.request("GET", "/api/v5/account/positions", params, private=True)
