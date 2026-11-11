#!/usr/bin/env python3
"""Measure, with REAL option prices, whether option buyers overpaid.

    python3 measure_option_cost.py          # fetch (a few minutes) and report
    python3 measure_option_cost.py --cached # report from option_cost_samples.csv

The backtest has to assume how expensive options are (IV_MULT). This script
measures it instead. Alpaca keeps real daily prices of expired option
contracts back to February 2024, so for every stock in the bot's universe and
every monthly expiry since then it:

  1. goes to the trading day about three weeks before expiry (the bot's horizon),
  2. takes the real closing prices of the at-the-money call and put,
  3. sees what the pair (a "straddle") actually paid out at expiry.

A straddle pays off if the stock moves a lot in either direction, so its
price is the market's bet on how much the stock will move. If buyers of
straddles lose money on average, options were overpriced, and the gap is what
an option seller collects. No pricing model is needed for that comparison.

It also backs out the implied volatility of each straddle and compares it
with the stock's recent volatility, which is exactly the IV_MULT number the
backtest assumes.
"""
import csv
import datetime as dt
import math
import statistics
import sys
from pathlib import Path

import config as C
from alpaca import DATA, Alpaca, ApiError
from backtest_signal import bs

OUT = Path(__file__).with_name("option_cost_samples.csv")
FIRST = "2024-03-01"   # Alpaca's option history starts in February 2024
HORIZON = 21           # calendar days before expiry, like the bot's entries
FIELDS = ["symbol", "entry", "expiry", "days", "spot", "strike", "call", "put",
          "final", "payoff", "buyer_ret", "iv", "rv_before", "rv_after"]


def stock_bars(api, start, adjustment):
    out, token = {}, None
    while True:
        page = api._req("GET", f"{DATA}/v2/stocks/bars", {
            "symbols": ",".join(C.UNIVERSE), "timeframe": "1Day", "start": start,
            "end": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
            "feed": "sip", "adjustment": adjustment, "limit": 10000, "page_token": token,
        })
        for sym, bars in (page.get("bars") or {}).items():
            out.setdefault(sym, {}).update({b["t"][:10]: b["c"] for b in bars})
        token = page.get("next_page_token")
        if not token:
            return out


def monthly_expiries(sessions, first):
    """Third Friday of each month, or the session before it on a holiday."""
    have, out = set(sessions), []
    year, month = int(first[:4]), int(first[5:7])
    while True:
        d = dt.date(year, month, 1)
        d += dt.timedelta(days=(4 - d.weekday()) % 7 + 14)
        while d.isoformat() not in have and d.isoformat() > sessions[0]:
            d -= dt.timedelta(days=1)
            if d.day < 12:
                break
        if d.isoformat() > sessions[-1]:
            return out
        if d.isoformat() in have:
            out.append(d.isoformat())
        month += 1
        if month == 13:
            year, month = year + 1, 1


def implied_vol(price, spot, strike, days):
    lo, hi = 0.01, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if bs(spot, strike, days, mid, "call") + bs(spot, strike, days, mid, "put") > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def realised(closes, sessions, a, b):
    """Annualised volatility of daily returns over sessions[a..b]."""
    rets = [math.log(closes[sessions[i]] / closes[sessions[i - 1]])
            for i in range(a + 1, b + 1) if sessions[i] in closes and sessions[i - 1] in closes]
    return statistics.stdev(rets) * math.sqrt(252) if len(rets) > 5 else None


def collect():
    api = Alpaca()
    raw = stock_bars(api, "2024-01-01", "raw")
    adj = stock_bars(api, "2024-01-01", "all")
    sessions = sorted(raw["SPY"])
    index = {d: i for i, d in enumerate(sessions)}
    rows = []
    for expiry in monthly_expiries(sessions, FIRST):
        target = (dt.date.fromisoformat(expiry) - dt.timedelta(days=HORIZON)).isoformat()
        entry = max(d for d in sessions if d <= target)
        days = (dt.date.fromisoformat(expiry) - dt.date.fromisoformat(entry)).days
        code = dt.date.fromisoformat(expiry).strftime("%y%m%d")
        for sym in C.UNIVERSE:
            r, a = raw.get(sym, {}), adj.get(sym, {})
            if entry not in r or expiry not in r or index[entry] < 25:
                continue
            if abs(r[entry] / a[entry] / (r[expiry] / a[expiry]) - 1) > 0.02:
                continue  # a stock split inside the window changes the contract
            spot = r[entry]
            strikes = sorted({round(spot / inc) * inc for inc in (0.5, 1, 2.5, 5, 10)},
                             key=lambda k: abs(k - spot))[:5]
            symbols = [f"{sym}{code}{cp}{int(round(k * 1000)):08d}" for k in strikes for cp in "CP"]
            try:
                page = api._req("GET", f"{DATA}/v1beta1/options/bars", {
                    "symbols": ",".join(symbols), "timeframe": "1Day",
                    "start": entry, "end": entry, "limit": 1000})
            except ApiError:
                continue
            bars = page.get("bars") or {}
            for k in strikes:  # nearest strike where both sides really traded that day
                call = bars.get(f"{sym}{code}C{int(round(k * 1000)):08d}")
                put = bars.get(f"{sym}{code}P{int(round(k * 1000)):08d}")
                if call and put and call[0]["v"] >= 5 and put[0]["v"] >= 5:
                    price = call[0]["c"] + put[0]["c"]
                    payoff = abs(r[expiry] - k)
                    i0, i1 = index[entry], index[expiry]
                    rows.append({
                        "symbol": sym, "entry": entry, "expiry": expiry, "days": days,
                        "spot": spot, "strike": k, "call": call[0]["c"], "put": put[0]["c"],
                        "final": r[expiry], "payoff": round(payoff, 4),
                        "buyer_ret": round(payoff / price - 1, 4),
                        "iv": round(implied_vol(price, spot, k, days), 4),
                        "rv_before": round(realised(a, sessions, i0 - 20, i0) or 0, 4),
                        "rv_after": round(realised(a, sessions, i0, i1) or 0, 4),
                    })
                    break
        print(f"  {expiry}: {len(rows)} samples so far", flush=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return rows


def load():
    with OUT.open() as f:
        return [{k: (v if k in ("symbol", "entry", "expiry") else float(v)) for k, v in row.items()}
                for row in csv.DictReader(f)]


def line(name, rows):
    rets = [r["buyer_ret"] for r in rows]
    mult = [r["iv"] / r["rv_before"] for r in rows if r["rv_before"] > 0]
    prem = [r["iv"] / r["rv_after"] for r in rows if r["rv_after"] > 0]
    se = statistics.stdev(rets) / math.sqrt(len(rets)) if len(rets) > 2 else 0
    return (f"{name:<10}{len(rets):>6}{statistics.mean(rets):>11.1%}{se:>8.1%}"
            f"{statistics.median(rets):>10.1%}{sum(x > 0 for x in rets) / len(rets):>9.0%}"
            f"{statistics.median(mult):>12.2f}{statistics.median(prem):>12.2f}")


def report(rows):
    print(f"\n{len(rows)} real at-the-money straddles, bought about {HORIZON} days before a monthly "
          f"expiry, {rows[0]['entry']} to {rows[-1]['expiry']}")
    head = (f"{'':<10}{'count':>6}{'buyer avg':>11}{'+/-':>8}{'median':>10}{'won':>9}"
            f"{'IV / recent':>12}{'IV / actual':>12}")
    print(head + "\n" + "-" * len(head))
    for sym in C.UNIVERSE:
        mine = [r for r in rows if r["symbol"] == sym]
        if len(mine) >= 5:
            print(line(sym, mine))
    print("-" * len(head))
    print(line("ALL", rows))
    for label, pick in (("Index funds", lambda r: r["symbol"] in C.PENNY_ALL),
                        ("Stocks", lambda r: r["symbol"] not in C.PENNY_ALL)):
        print(line(label, [r for r in rows if pick(r)]))
    years = sorted({r["expiry"][:4] for r in rows})
    for y in years:
        print(line(y, [r for r in rows if r["expiry"][:4] == y]))
    print("""
buyer avg    average profit of buying the straddle and holding to expiry, before
             trading costs. Negative means options were overpriced on average.
+/-          one standard error. Samples in the same month are not independent,
             so the true uncertainty is larger than this.
IV / recent  implied volatility divided by the stock's volatility over the prior
             20 days. This is the IV_MULT the backtest assumes (1.2).
IV / actual  implied volatility divided by what the stock then actually did.
             Above 1.00 means buyers paid for more movement than they got.""")


def main():
    rows = load() if "--cached" in sys.argv and OUT.exists() else collect()
    report(rows)


if __name__ == "__main__":
    main()
