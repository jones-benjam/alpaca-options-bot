#!/usr/bin/env python3
"""Confirm that an Alpaca PAPER account can trade options.

Reads ALPACA_API_KEY and ALPACA_SECRET_KEY from the environment or from a
.env file next to this script. Uses only the Python standard library.

    python3 check_options.py               # read-only checks
    python3 check_options.py --test-order  # also place and cancel a $0.01 bid

The trading host is hard-coded to the paper endpoint, so this script cannot
touch a live account even if live keys are supplied (they will be rejected).
"""
import datetime as dt
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
LEVELS = {
    0: "options disabled",
    1: "covered calls and cash-secured puts",
    2: "level 1 plus buying calls and puts",
    3: "level 2 plus spreads (multi-leg orders)",
}


def load_env():
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
        sys.exit(
            "Missing keys. Copy .env.example to .env and fill in your PAPER "
            "API key and secret (Alpaca dashboard > Paper > API Keys)."
        )
    return key, secret


def call(method, url, headers, params=None, body=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:300]
        if err.code in (401, 403):
            sys.exit(
                f"{err.code} from {url}\n{detail}\n"
                "Keys were rejected. Make sure they are PAPER keys, not live."
            )
        raise RuntimeError(f"{err.code} from {url}: {detail}") from err


def main():
    key, secret = load_env()
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    ok = True

    # 1. Account-level options permission
    acct = call("GET", f"{PAPER}/v2/account", headers)
    approved = int(acct.get("options_approved_level") or 0)
    trading = int(acct.get("options_trading_level") or 0)
    print("1. Account")
    print(f"   status                 {acct.get('status')}")
    print(f"   equity                 ${float(acct.get('equity', 0)):,.2f}")
    print(f"   options approved level {approved} ({LEVELS.get(approved, '?')})")
    print(f"   options trading level  {trading} ({LEVELS.get(trading, '?')})")
    print(f"   options buying power   ${float(acct.get('options_buying_power') or 0):,.2f}")
    if trading < 2:
        ok = False
        print("   PROBLEM: need level 2+ to buy options, level 3 for spreads.")
        print("   Fix: Paper dashboard > Account > Configure > Options.")

    # 2. Can we find tradable contracts?
    trade = call("GET", f"{DATA}/v2/stocks/SPY/trades/latest", headers, {"feed": "iex"})
    spot = float(trade["trade"]["p"])
    today = dt.date.today()
    contracts = call(
        "GET",
        f"{PAPER}/v2/options/contracts",
        headers,
        {
            "underlying_symbols": "SPY",
            "status": "active",
            "type": "call",
            "expiration_date_gte": (today + dt.timedelta(days=21)).isoformat(),
            "expiration_date_lte": (today + dt.timedelta(days=45)).isoformat(),
            "strike_price_gte": f"{spot * 0.99:.2f}",
            "strike_price_lte": f"{spot * 1.01:.2f}",
            "limit": 50,
        },
    ).get("option_contracts", [])
    contracts = [c for c in contracts if c.get("tradable")]
    print(f"\n2. Contracts (SPY last trade ${spot:,.2f})")
    if not contracts:
        ok = False
        print("   PROBLEM: no tradable SPY calls returned.")
    else:
        contracts.sort(key=lambda c: (c["expiration_date"], abs(float(c["strike_price"]) - spot)))
        pick = contracts[0]
        print(f"   {len(contracts)} near-the-money calls found, e.g. {pick['symbol']}")

    # 3. Can we get option quotes on the free (indicative) feed?
    if contracts:
        print("\n3. Option quote (free 'indicative' feed)")
        try:
            snaps = call(
                "GET",
                f"{DATA}/v1beta1/options/snapshots",
                headers,
                {"symbols": pick["symbol"], "feed": "indicative"},
            ).get("snapshots", {})
            quote = snaps.get(pick["symbol"], {}).get("latestQuote", {})
            if quote:
                print(f"   {pick['symbol']} bid {quote.get('bp')} / ask {quote.get('ap')}")
            else:
                print("   No quote returned (normal outside market hours).")
        except RuntimeError as err:
            ok = False
            print(f"   PROBLEM: {err}")

    # 4. Optional: prove an options order is accepted, then cancel it
    if contracts and "--test-order" in sys.argv:
        print("\n4. Test order (1 contract, $0.01 limit bid, cancelled right away)")
        try:
            order = call(
                "POST",
                f"{PAPER}/v2/orders",
                headers,
                body={
                    "symbol": pick["symbol"],
                    "qty": "1",
                    "side": "buy",
                    "type": "limit",
                    "limit_price": "0.01",
                    "time_in_force": "day",
                },
            )
            print(f"   accepted: id {order['id']} status {order['status']}")
            time.sleep(1)
            call("DELETE", f"{PAPER}/v2/orders/{order['id']}", headers)
            print("   cancelled")
        except RuntimeError as err:
            ok = False
            print(f"   PROBLEM: {err}")

    print("\nRESULT:", "options trading is ready on this paper account." if ok else "see PROBLEM lines above.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
