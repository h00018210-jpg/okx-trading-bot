"""Read-only OKX market/account clients with REST and optional ccxt fallback."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import json
import os
from datetime import datetime, timezone


BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.okx.com/",
    "Origin": "https://www.okx.com",
    "Content-Type": "application/json",
}


class OKXAPIError(RuntimeError):
    """Exception that carries endpoint debug details for reports."""

    def __init__(self, source, endpoint, params=None, status_code=None, response_body=None, message=None):
        self.source = source
        self.endpoint = endpoint
        self.params = params or {}
        self.status_code = status_code
        self.response_body = (response_body or "")[:500]
        detail = message or "request failed"
        super().__init__(
            f"source={source}; endpoint={endpoint}; params={self.params}; "
            f"status_code={status_code}; response_body={self.response_body}; error={detail}"
        )


class OKXClient:
    """Small OKX REST client using requests.Session()."""

    BASE_URL = "https://www.okx.com"

    def __init__(self, api_key=None, api_secret=None, passphrase=None, simulated=False, timeout=10):
        self.api_key = api_key or os.getenv("OKX_API_KEY")
        self.api_secret = api_secret or os.getenv("OKX_API_SECRET")
        self.passphrase = passphrase or os.getenv("OKX_API_PASSPHRASE")
        self.simulated = simulated or os.getenv("OKX_SIMULATED_TRADING", "").lower() in {"1", "true", "yes"}
        self.timeout = timeout
        self.session = None
        requests_spec = importlib.util.find_spec("requests")
        if requests_spec is not None:
            requests = importlib.import_module("requests")
            self.session = requests.Session()
            self.session.headers.update(BROWSER_HEADERS)

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
        if self.session is None:
            raise OKXAPIError("okx_rest", path, params, message="Python package 'requests' is not installed")
        query = "?" + "&".join(f"{key}={value}" for key, value in params.items()) if params else ""
        path_with_query = f"{path}{query}"
        headers = {}
        if private:
            if not self.has_credentials:
                raise OKXAPIError("okx_rest", path, params, message="OKX API credentials are not configured")
            timestamp = self._timestamp()
            headers.update({
                "OK-ACCESS-KEY": self.api_key,
                "OK-ACCESS-SIGN": self._sign(timestamp, method, path_with_query),
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": self.passphrase,
            })
            if self.simulated:
                headers["x-simulated-trading"] = "1"
        try:
            response = self.session.request(method.upper(), self.BASE_URL + path, params=params, headers=headers, timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001 - converted into reportable missing_data.
            raise OKXAPIError("okx_rest", path, params, message=str(exc)) from exc
        body = response.text[:500]
        if response.status_code >= 400:
            raise OKXAPIError("okx_rest", path, params, response.status_code, body)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise OKXAPIError("okx_rest", path, params, response.status_code, body, "invalid JSON") from exc
        if payload.get("code") != "0":
            raise OKXAPIError("okx_rest", path, params, response.status_code, body, payload.get("msg") or str(payload))
        return payload.get("data", [])

    def ticker(self, inst_id):
        return self.request("GET", "/api/v5/market/ticker", {"instId": inst_id})

    def candles(self, inst_id, bar, limit=180):
        data = self.request("GET", "/api/v5/market/candles", {"instId": inst_id, "bar": bar, "limit": limit})
        return [_rest_candle(row) for row in reversed(data)]

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


def _ccxt_error(endpoint, params, exc):
    return OKXAPIError(
        "ccxt",
        endpoint,
        params,
        status_code=getattr(exc, "http_status", None),
        response_body=getattr(exc, "response", ""),
        message=str(exc),
    )


class CCXTOKXClient:
    """Read-only ccxt.okx fallback with automatic HYPE swap symbol discovery."""

    def __init__(self, timeout=10000):
        self.timeout = timeout
        self.exchange = None
        self._markets = None
        spec = importlib.util.find_spec("ccxt")
        if spec is not None:
            ccxt = importlib.import_module("ccxt")
            self.exchange = ccxt.okx({"enableRateLimit": True, "timeout": timeout})

    def _ensure_exchange(self):
        if self.exchange is None:
            raise OKXAPIError("ccxt", "init", message="Python package 'ccxt' is not installed")
        if self._markets is None:
            try:
                self._markets = self.exchange.load_markets()
            except Exception as exc:  # noqa: BLE001 - converted into reportable missing_data.
                raise _ccxt_error("load_markets", {}, exc) from exc
        return self.exchange

    def symbol_for_inst_id(self, inst_id):
        exchange = self._ensure_exchange()
        markets = self._markets or exchange.markets
        hype_markets = []
        for symbol, market in markets.items():
            base = market.get("base")
            quote = market.get("quote")
            is_swap = bool(market.get("swap"))
            if base == "HYPE" or "HYPE" in symbol:
                hype_markets.append(symbol)
            if base == "HYPE" and quote == "USDT" and is_swap:
                return symbol
        message = f"No HYPE/USDT swap market found for {inst_id}. Available HYPE markets: {hype_markets}"
        print(message)
        raise OKXAPIError("ccxt", "load_markets", {"instId": inst_id}, message=message)

    def ticker(self, inst_id):
        symbol = self.symbol_for_inst_id(inst_id)
        try:
            ticker = self.exchange.fetch_ticker(symbol)
        except Exception as exc:  # noqa: BLE001
            raise _ccxt_error("fetch_ticker", {"instId": inst_id, "symbol": symbol}, exc) from exc
        return [{"last": ticker.get("last"), "high24h": ticker.get("high"), "low24h": ticker.get("low"), "vol24h": ticker.get("baseVolume"), "ccxt_symbol": symbol}]

    def candles(self, inst_id, bar, limit=180):
        symbol = self.symbol_for_inst_id(inst_id)
        try:
            rows = self.exchange.fetch_ohlcv(symbol, timeframe=bar.lower(), limit=limit)
        except Exception as exc:  # noqa: BLE001
            raise _ccxt_error("fetch_ohlcv", {"instId": inst_id, "symbol": symbol, "bar": bar, "limit": limit}, exc) from exc
        return [{"timestamp": row[0], "open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5], "ccxt_symbol": symbol} for row in rows]

    def order_book(self, inst_id, depth=20):
        symbol = self.symbol_for_inst_id(inst_id)
        try:
            book = self.exchange.fetch_order_book(symbol, limit=depth)
        except Exception as exc:  # noqa: BLE001
            raise _ccxt_error("fetch_order_book", {"instId": inst_id, "symbol": symbol, "depth": depth}, exc) from exc
        return [{"bids": [[str(p), str(s)] for p, s in book.get("bids", [])[:depth]], "asks": [[str(p), str(s)] for p, s in book.get("asks", [])[:depth]], "ccxt_symbol": symbol}]

    def trades(self, inst_id, limit=100):
        symbol = self.symbol_for_inst_id(inst_id)
        try:
            rows = self.exchange.fetch_trades(symbol, limit=limit)
        except Exception as exc:  # noqa: BLE001
            raise _ccxt_error("fetch_trades", {"instId": inst_id, "symbol": symbol, "limit": limit}, exc) from exc
        return [{"ts": t.get("timestamp"), "px": t.get("price"), "sz": t.get("amount"), "side": t.get("side"), "ccxt_symbol": symbol} for t in rows]

    def funding_rate(self, inst_id):
        symbol = self.symbol_for_inst_id(inst_id)
        try:
            data = self.exchange.fetch_funding_rate(symbol)
        except Exception as exc:  # noqa: BLE001
            raise _ccxt_error("fetch_funding_rate", {"instId": inst_id, "symbol": symbol}, exc) from exc
        return [{"fundingRate": data.get("fundingRate"), "nextFundingTime": data.get("fundingTimestamp"), "ccxt_symbol": symbol}]

    def open_interest(self, inst_id):
        symbol = self.symbol_for_inst_id(inst_id)
        if not getattr(self.exchange, "has", {}).get("fetchOpenInterest"):
            raise OKXAPIError("ccxt", "fetch_open_interest", {"instId": inst_id, "symbol": symbol}, message="ccxt.okx does not advertise fetchOpenInterest")
        try:
            data = self.exchange.fetch_open_interest(symbol)
        except Exception as exc:  # noqa: BLE001
            raise _ccxt_error("fetch_open_interest", {"instId": inst_id, "symbol": symbol}, exc) from exc
        return [{"oi": data.get("openInterestAmount") or data.get("openInterestValue"), "ccxt_symbol": symbol}]


def _rest_candle(row):
    return {
        "timestamp": row[0], "open": row[1], "high": row[2], "low": row[3],
        "close": row[4], "volume": row[5], "volume_ccy": row[6] if len(row) > 6 else None,
        "volume_ccy_quote": row[7] if len(row) > 7 else None, "confirm": row[8] if len(row) > 8 else None,
    }
