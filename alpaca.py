"""Minimal Alpaca REST client using only the standard library.

The trading host is hard-coded to the PAPER endpoint, so this code cannot
place orders in a live account.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PAPER = "https://paper-api.alpaca.markets"
DATA = "https://data.alpaca.markets"


class ApiError(Exception):
    def __init__(self, code, body, url):
        super().__init__(f"{code} {url.split('?')[0]}: {body}")
        self.code = code
        self.body = body


def load_keys():
    env_file = Path(__file__).with_name(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        sys.exit("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY (set them in .env or the environment).")
    return key, secret


class Alpaca:
    def __init__(self):
        key, secret = load_keys()
        self.headers = {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _req(self, method, url, params=None, body=None):
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode() if body is not None else None
        last = None
        for attempt in range(4):
            req = urllib.request.Request(url, data=data, method=method, headers=self.headers)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as err:
                text = err.read().decode(errors="replace")[:400]
                last = ApiError(err.code, text, url)
                if err.code == 429 or err.code >= 500:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last
            except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
                last = ApiError(0, str(err), url)
                time.sleep(2 * (attempt + 1))
        raise last

    # ---- trading ------------------------------------------------------------
    def clock(self):
        return self._req("GET", f"{PAPER}/v2/clock")

    def account(self):
        return self._req("GET", f"{PAPER}/v2/account")

    def positions(self):
        return self._req("GET", f"{PAPER}/v2/positions")

    def official_closes(self):
        """Alpaca's own end-of-day account values, {YYYY-MM-DD: equity}. Each
        point is stamped at midnight Eastern at the END of its trading day."""
        import datetime as dt

        h = self._req("GET", f"{PAPER}/v2/account/portfolio/history", {"period": "1M", "timeframe": "1D"})
        out = {}
        for ts, equity in zip(h.get("timestamp") or [], h.get("equity") or []):
            if equity:
                day = (dt.datetime.fromtimestamp(ts, dt.timezone.utc) - dt.timedelta(hours=12)).date()
                out[day.isoformat()] = float(equity)
        return out

    def orders(self, status="all", after=None, limit=500, direction="asc"):
        return self._req(
            "GET",
            f"{PAPER}/v2/orders",
            {"status": status, "after": after, "limit": limit, "direction": direction},
        )

    def order(self, order_id):
        return self._req("GET", f"{PAPER}/v2/orders/{order_id}")

    def submit(self, symbol, qty, side, client_order_id, limit_price=None):
        body = {
            "symbol": symbol,
            "qty": str(int(qty)),
            "side": side,
            "type": "limit" if limit_price is not None else "market",
            "time_in_force": "day",
            "client_order_id": client_order_id,
            "position_intent": "buy_to_open" if side == "buy" else "sell_to_close",
        }
        if limit_price is not None:
            body["limit_price"] = f"{limit_price:.2f}"
        try:
            return self._req("POST", f"{PAPER}/v2/orders", body=body)
        except ApiError as err:
            # A retried POST can collide with its own first attempt.
            if err.code == 422 and "client_order_id" in err.body:
                return self._req(
                    "GET",
                    f"{PAPER}/v2/orders:by_client_order_id",
                    {"client_order_id": client_order_id},
                )
            raise

    def cancel(self, order_id):
        try:
            self._req("DELETE", f"{PAPER}/v2/orders/{order_id}")
        except ApiError as err:
            if err.code not in (404, 422):  # already filled or gone
                raise

    # ---- market data --------------------------------------------------------
    def _bars(self, symbols, timeframe, start, end=None):
        out, token = {}, None
        while True:
            page = self._req(
                "GET",
                f"{DATA}/v2/stocks/bars",
                {
                    "symbols": ",".join(symbols),
                    "timeframe": timeframe,
                    "start": start,
                    "end": end,
                    "feed": "iex",
                    "adjustment": "all",
                    "limit": 10000,
                    "page_token": token,
                },
            )
            for sym, bars in (page.get("bars") or {}).items():
                out.setdefault(sym, []).extend(bars)
            token = page.get("next_page_token")
            if not token:
                return out

    def daily_bars(self, symbols, start):
        return self._bars(symbols, "1Day", start)

    def minute_bars(self, symbols, start, end):
        return self._bars(symbols, "1Min", start, end)

    def stock_snapshots(self, symbols):
        return self._req(
            "GET", f"{DATA}/v2/stocks/snapshots", {"symbols": ",".join(symbols), "feed": "iex"}
        )

    def option_snapshots(self, symbols):
        out = {}
        symbols = list(symbols)
        for i in range(0, len(symbols), 100):
            page = self._req(
                "GET",
                f"{DATA}/v1beta1/options/snapshots",
                {"symbols": ",".join(symbols[i : i + 100]), "feed": "indicative"},
            )
            out.update(page.get("snapshots") or {})
        return out

    def option_chain(self, underlying, **filters):
        out, token = {}, None
        while True:
            params = {"feed": "indicative", "limit": 1000, "page_token": token}
            params.update(filters)
            page = self._req("GET", f"{DATA}/v1beta1/options/snapshots/{underlying}", params)
            out.update(page.get("snapshots") or {})
            token = page.get("next_page_token")
            if not token:
                return out
