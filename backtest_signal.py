#!/usr/bin/env python3
"""Backtest of the bot's stock-picking rules on free daily price history.

    python3 backtest_signal.py            # about five years, all variants
    python3 backtest_signal.py 2023-01-01 # from a later start date

What is real and what is modelled
---------------------------------
Real:     daily closing prices of the 16 names (Alpaca, split-adjusted), the
          regime rule, the ranking rule, the slot limits and the exit rules.
Modelled: option prices. Each option is priced with Black-Scholes at a
          volatility set from the stock's recent realised volatility, held
          constant for the life of the trade, plus a fixed trading cost. The
          level (how expensive options are relative to recent volatility) is
          not assumed: it was measured from real option prices for 2024-2026
          by measure_option_cost.py. Positions are checked once a day at the
          close, not every minute.

So treat the option returns as a rough guide for COMPARING rule variants, not
as a forecast of what the bot will earn. The "stock moved our way" columns use
no option model at all.
"""
import datetime as dt
import math
import random
import statistics
import sys

import config as C
from alpaca import DATA, Alpaca

DTE = C.CORE_DTE_TARGET          # calendar days to expiry at entry
SLIP = 0.015                     # cost paid on the way in and again on the way out
IV_MULT = "measured"             # option price level: "measured" (see IV_MEASURED) or a number
SLOTS, SLOT_PCT = C.CORE_SLOTS, C.CORE_SLOT_PCT
# Measured with real option prices, Feb 2024 to Oct 2026 (measure_option_cost.py):
# implied volatility divided by the prior 20 days' realised volatility.
IV_MEASURED = {"index": 1.09, "stock": 0.99}


def sigma_for(sym, v, iv_mult):
    if iv_mult == "measured":
        iv_mult = IV_MEASURED["index" if sym in C.PENNY_ALL else "stock"]
    return max(0.12, v["rv"] * iv_mult)


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(spot, strike, days, sigma, kind):
    if days <= 0:
        return max(0.0, spot - strike) if kind == "call" else max(0.0, strike - spot)
    sd = sigma * math.sqrt(days / 365)
    d1 = (math.log(spot / strike) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    if kind == "call":
        return spot * ncdf(d1) - strike * ncdf(d2)
    return strike * ncdf(-d2) - spot * ncdf(-d1)


def ema(values, n):
    k = 2 / (n + 1)
    e = sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def load(start):
    api, out, token = Alpaca(), {}, None
    end = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    while True:
        page = api._req("GET", f"{DATA}/v2/stocks/bars", {
            "symbols": ",".join(C.UNIVERSE), "timeframe": "1Day", "start": start, "end": end,
            "feed": "sip", "adjustment": "all", "limit": 10000, "page_token": token,
        })
        for sym, bars in (page.get("bars") or {}).items():
            out.setdefault(sym, {}).update({b["t"][:10]: b["c"] for b in bars})
        token = page.get("next_page_token")
        if not token:
            break
    return out


def features(prices, days):
    """Per symbol, per day index: the same numbers the live bot computes."""
    feats = {}
    for sym, by_day in prices.items():
        rows, hist = [None] * len(days), []
        for i, d in enumerate(days):
            if d not in by_day:
                continue
            hist.append(by_day[d])
            if len(hist) < 26:
                continue
            c = hist[-52:]
            rets = [math.log(c[j] / c[j - 1]) for j in range(len(c) - 20, len(c))]
            rv = statistics.stdev(rets) * math.sqrt(252)
            rows[i] = {
                "px": c[-1], "ema10": ema(c, 10), "ema20": ema(c, 20),
                "r5": c[-1] / c[-6] - 1, "r20": c[-1] / c[-21] - 1, "rv": rv,
            }
        feats[sym] = rows
    return feats


def regime(feats, i):
    idx = [feats[s][i] for s in C.INDEX]
    if any(v is None for v in idx):
        return "unknown"
    if all(v["px"] > v["ema20"] for v in idx):
        return "bull"
    if all(v["px"] < v["ema20"] for v in idx):
        return "bear"
    return "mixed"


def candidates(feats, i, reg, w5, w20, no_chase, rng):
    out = []
    for s in C.UNIVERSE:
        v = feats[s][i]
        if not v:
            continue
        score = w5 * v["r5"] + w20 * v["r20"]
        if no_chase:  # skip names that already made an unusually large 5-day move
            if abs(v["r5"]) > no_chase * v["rv"] * math.sqrt(5 / 252):
                continue
        if v["px"] > v["ema10"] and v["r5"] > 0 and score > 0:
            out.append((score, s, "call"))
        elif v["px"] < v["ema10"] and v["r5"] < 0 and score < 0:
            out.append((-score, s, "put"))
    if reg == "bull":
        out = [c for c in out if c[2] == "call"]
    elif reg == "bear":
        out = [c for c in out if c[2] == "put"]
    elif reg == "unknown":
        out = []
    out = [c for c in out if c[0] >= C.CORE_MIN_STRENGTH]
    if rng:  # baseline: same regime and filters, but pick names at random
        rng.shuffle(out)
        return out
    return sorted(out, reverse=True)


def simulate(feats, days, w5=0.6, w20=0.4, no_chase=0.0, seed=None, iv_mult=IV_MULT,
             dte=DTE, itm=0.0, puts=True, flip=True, slot_pct=SLOT_PCT, stop_exact=False,
             cooldown=0, recent_n=0, after_losses=1.0, after_wins=1.0):
    """dte: days to expiry at entry. itm: how far in the money to buy (0.05 = 5%).
    puts: allow puts at all. flip: use the trend-flip exit. slot_pct: size per slot.
    stop_exact: assume a stop sells at exactly the stop level (the live bot checks
    every minute) instead of at that day's close. The truth lies in between.

    "Learning" rules, which react to the bot's own recent results:
    cooldown: after a losing trade in a stock, skip that stock for this many trading days.
    recent_n / after_losses / after_wins: look at the last recent_n closed trades; if
    they lost money on average, multiply the next position's size by after_losses,
    otherwise by after_wins."""
    rng = random.Random(seed) if seed is not None else None
    dates = [dt.date.fromisoformat(d) for d in days]
    cash, book, trades, curve, hits = 1.0, {}, [], [], []
    blocked = {}  # symbol -> first day index it may be traded again
    for i in range(len(days)):
        # -- manage open positions at today's close --------------------------
        for sym in list(book):
            p, v = book[sym], feats[sym][i]
            if v is None:
                continue
            left = dte - (dates[i] - p["date"]).days
            price = bs(v["px"], p["strike"], left, p["sigma"], p["kind"])
            p["mark"] = price
            p["peak"] = max(p["peak"], price)
            pnl = price / p["cost"] - 1
            reason = None
            if left <= C.CORE_MIN_DTE_EXIT:
                reason = "time"
            elif pnl <= C.CORE_STOP:
                reason = "stop"
            elif p["peak"] >= p["cost"] * (1 + C.CORE_TP1) and price <= p["peak"] * (1 - C.CORE_TRAIL):
                reason = "trail"
            elif p["peak"] >= p["cost"] * 1.5 and price <= p["cost"] * 1.05:
                reason = "breakeven"
            elif flip and (
                (p["kind"] == "call" and v["px"] < v["ema10"]) or (p["kind"] == "put" and v["px"] > v["ema10"])
            ):
                reason = "flip"
            elif not p["half"] and pnl >= C.CORE_TP1:
                sold = p["units"] / 2
                cash += sold * price * (1 - SLIP)
                p["got"] += sold * price * (1 - SLIP)
                p["units"] -= sold
                p["half"] = True
            if reason:
                if reason == "stop" and stop_exact:
                    price = max(price, p["cost"] * (1 + C.CORE_STOP))
                got = p["units"] * price * (1 - SLIP)
                cash += got
                trades.append({"ret": (p["got"] + got) / p["paid"] - 1, "kind": p["kind"],
                               "why": reason, "i": p["i"], "held": i - p["i"]})
                if cooldown and trades[-1]["ret"] < 0:
                    blocked[sym] = i + cooldown
                del book[sym]
        equity = cash + sum(p["units"] * p["mark"] for p in book.values())
        curve.append(equity)

        # -- fill free slots at today's close ----------------------------------
        reg = regime(feats, i)
        count = {"call": 0, "put": 0}
        for p in book.values():
            count[p["kind"]] += 1
        for strength, sym, kind in candidates(feats, i, reg, w5, w20, no_chase, rng):
            if len(book) >= SLOTS:
                break
            if sym in book or (reg == "mixed" and count[kind] >= max(2, SLOTS * 2 // 3)):
                continue
            if kind == "put" and not puts:
                continue
            if blocked.get(sym, 0) > i:
                continue
            v = feats[sym][i]
            sigma = sigma_for(sym, v, iv_mult)
            strike = v["px"] * (1 - itm) if kind == "call" else v["px"] * (1 + itm)
            cost = bs(v["px"], strike, dte, sigma, kind) * (1 + SLIP)
            size = slot_pct
            if recent_n and len(trades) >= recent_n:
                losing = statistics.mean(t["ret"] for t in trades[-recent_n:]) < 0
                size *= after_losses if losing else after_wins
            spend = min(size * equity, cash * 0.98)
            if spend <= 0 or cost <= 0:
                continue
            cash -= spend
            book[sym] = {"kind": kind, "strike": strike, "sigma": sigma, "cost": cost, "mark": cost,
                         "peak": cost, "units": spend / cost, "paid": spend, "got": 0.0,
                         "half": False, "date": dates[i], "i": i}
            count[kind] += 1
            # model-free check: did the stock move our way over the next 10 trading days?
            if i + 10 < len(days) and feats[sym][i + 10]:
                move = feats[sym][i + 10]["px"] / v["px"] - 1
                hits.append(move if kind == "call" else -move)
    return trades, curve, hits


def simulate_seller(feats, days, dte=30, short_sd=0.6, width_sd=0.6, take=0.5, stop=2.0,
                    flip=True, slot_pct=SLOT_PCT, iv_mult="measured", names=None):
    """The other side of the trade: SELL options with a capped loss ("credit spreads").

    Same regime and stock ranking as the bot. Where the bot would buy a call, this
    sells a put spread below the price (it keeps the premium unless the stock
    falls); where the bot would buy a put, it sells a call spread above the price.
    short_sd / width_sd place the two strikes in units of the expected move.
    Each position risks slot_pct of the sleeve at most. Exits: buy back after
    keeping `take` of the premium, or when the spread costs `stop` times the
    premium, or on a trend flip, or four days before expiry."""
    dates = [dt.date.fromisoformat(d) for d in days]
    cash, book, trades, curve = 1.0, {}, [], []
    for i in range(len(days)):
        for sym in list(book):
            p, v = book[sym], feats[sym][i]
            if v is None:
                continue
            left = dte - (dates[i] - p["date"]).days
            cost = (bs(v["px"], p["ks"], left, p["sigma"], p["opt"]) * (1 + SLIP)
                    - bs(v["px"], p["kl"], left, p["sigma"], p["opt"]) * (1 - SLIP))
            cost = max(0.0, min(p["width"], cost))
            p["mark"] = cost
            reason = None
            if left <= C.CORE_MIN_DTE_EXIT:
                reason = "time"
            elif cost <= (1 - take) * p["credit"]:
                reason = "target"
            elif cost >= stop * p["credit"]:
                reason = "stop"
            elif flip and ((p["view"] == "up" and v["px"] < v["ema10"]) or (p["view"] == "down" and v["px"] > v["ema10"])):
                reason = "flip"
            if reason:
                cash += p["units"] * (p["width"] - cost)
                trades.append({"ret": (p["credit"] - cost) / (p["width"] - p["credit"]), "kind": p["opt"],
                               "why": reason, "i": p["i"], "held": i - p["i"]})
                del book[sym]
        equity = cash + sum(p["units"] * (p["width"] - p["mark"]) for p in book.values())
        curve.append(equity)

        reg = regime(feats, i)
        count = {"up": 0, "down": 0}
        for p in book.values():
            count[p["view"]] += 1
        for strength, sym, kind in candidates(feats, i, reg, 0.6, 0.4, 0.0, None):
            if len(book) >= SLOTS:
                break
            view = "up" if kind == "call" else "down"
            if sym in book or (names and sym not in names):
                continue
            if reg == "mixed" and count[view] >= max(2, SLOTS * 2 // 3):
                continue
            v = feats[sym][i]
            sigma = sigma_for(sym, v, iv_mult)
            sd = sigma * math.sqrt(dte / 365)
            sign, opt = (-1, "put") if view == "up" else (1, "call")
            ks = v["px"] * math.exp(sign * short_sd * sd)
            kl = v["px"] * math.exp(sign * (short_sd + width_sd) * sd)
            credit = bs(v["px"], ks, dte, sigma, opt) * (1 - SLIP) - bs(v["px"], kl, dte, sigma, opt) * (1 + SLIP)
            width = abs(ks - kl)
            if credit <= 0 or width - credit <= 0:
                continue
            spend = min(slot_pct * equity, cash * 0.98)
            if spend <= 0:
                continue
            cash -= spend
            book[sym] = {"opt": opt, "view": view, "ks": ks, "kl": kl, "sigma": sigma, "credit": credit,
                         "width": width, "mark": credit, "units": spend / (width - credit),
                         "date": dates[i], "i": i}
            count[view] += 1
    return trades, curve, []


def drawdown(curve):
    peak, worst = curve[0], 0.0
    for x in curve:
        peak = max(peak, x)
        worst = min(worst, x / peak - 1)
    return worst


def summarise(trades, curve, hits):
    rets = [t["ret"] for t in trades]
    wins = [r for r in rets if r > 0]
    return {
        "n": len(rets),
        "win": len(wins) / len(rets) if rets else 0,
        "avg": statistics.mean(rets) if rets else 0,
        "med": statistics.median(rets) if rets else 0,
        "hit": sum(h > 0 for h in hits) / len(hits) if hits else 0,
        "move": statistics.mean(hits) if hits else 0,
        "total": curve[-1] / curve[0] - 1,
        "dd": drawdown(curve),
    }


def contest(curve, spy, n=15):
    """Every possible n-trading-day window: what the sleeve did, and how often
    a half-sleeve / half-cash account would have beaten SPY."""
    sleeve = sorted(curve[i + n] / curve[i] - 1 for i in range(len(curve) - n))
    pairs = [(curve[i + n] / curve[i] - 1, spy[i + n] / spy[i] - 1) for i in range(len(curve) - n)]
    pick = lambda q: sleeve[int(q * (len(sleeve) - 1))]
    return {
        "p10": pick(0.10), "med": pick(0.50), "p90": pick(0.90),
        "mean": statistics.mean(sleeve),
        "beat_cash": sum(0.5 * a > b for a, b in pairs) / len(pairs),
        "beat_spy": sum(a > b for a, b in pairs) / len(pairs),
        "bust": sum(a <= -0.5 for a in sleeve) / len(sleeve),
        "boom": sum(a >= 0.5 for a in sleeve) / len(sleeve),
    }


def line(name, s):
    return (f"{name:<34}{s['n']:>6}{s['win']:>7.0%}{s['avg']:>8.1%}{s['med']:>8.1%}"
            f"{s['hit']:>8.0%}{s['move']:>8.2%}{s['total']:>10.0%}{s['dd']:>8.0%}")


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else "2021-06-01"
    prices = load(start)
    days = sorted(prices["SPY"])
    feats = features(prices, days)
    first = next(i for i in range(len(days)) if regime(feats, i) != "unknown")
    days, feats = days[first:], {s: rows[first:] for s, rows in feats.items()}
    spy = prices["SPY"][days[-1]] / prices["SPY"][days[0]] - 1
    print(f"Period {days[0]} to {days[-1]} ({len(days)} trading days). SPY buy-and-hold: {spy:+.0%}")
    print(f"Sleeve of {SLOTS} slots at {SLOT_PCT:.0%} each, {DTE}-day at-the-money options, "
          f"option prices at the measured level (IV = {IV_MEASURED['stock']} x recent vol for stocks, "
          f"{IV_MEASURED['index']} x for index funds), {SLIP:.1%} cost each way.\n")
    head = (f"{'Variant':<34}{'trades':>6}{'win%':>7}{'avg':>8}{'median':>8}"
            f"{'stock':>8}{'10d':>8}{'sleeve':>10}{'worst':>8}")
    sub = (f"{'':<34}{'':>6}{'':>7}{'/trade':>8}{'/trade':>8}"
           f"{'hit%':>8}{'move':>8}{'total':>10}{'drop':>8}")
    print(head + "\n" + sub + "\n" + "-" * len(head))

    variants = [
        ("Current: 60% 5-day, 40% 20-day", dict(w5=0.6, w20=0.4)),
        ("5-day momentum only", dict(w5=1.0, w20=0.0)),
        ("30% 5-day, 70% 20-day", dict(w5=0.3, w20=0.7)),
        ("20-day momentum only", dict(w5=0.0, w20=1.0)),
        ("Current + skip >2-sigma 5-day moves", dict(w5=0.6, w20=0.4, no_chase=2.0)),
        ("Current + skip >1.5-sigma moves", dict(w5=0.6, w20=0.4, no_chase=1.5)),
    ]
    results = {}
    for name, kw in variants:
        results[name] = simulate(feats, days, **kw)
        print(line(name, summarise(*results[name])))

    runs = [summarise(*simulate(feats, days, seed=k)) for k in range(25)]
    avg = {k: statistics.mean(r[k] for r in runs) for k in runs[0]}
    avg["n"] = round(avg["n"])
    print(line("Random names, same regime (x25)", avg))
    totals = sorted(r["total"] for r in runs)
    print(f"{'':<34}random sleeve totals: worst {totals[0]:+.0%}, median {totals[12]:+.0%}, best {totals[-1]:+.0%}")

    name = variants[0][0]
    trades, curve, hits = results[name]
    print(f"\nBreakdown of '{name}'")
    for kind in ("call", "put"):
        r = [t["ret"] for t in trades if t["kind"] == kind]
        if r:
            print(f"  {kind}s: {len(r)} trades, win {sum(x > 0 for x in r) / len(r):.0%}, avg {statistics.mean(r):+.1%}")
    for why in ("stop", "flip", "time", "trail", "breakeven"):
        r = [t["ret"] for t in trades if t["why"] == why]
        if r:
            print(f"  exit by {why:<10}{len(r):>5} trades, avg {statistics.mean(r):+.1%}")
    print(f"  average holding time: {statistics.mean(t['held'] for t in trades):.1f} trading days")
    half = len(days) // 2
    for label, lo, hi in (("first half", 0, half), ("second half", half, len(days))):
        r = [t["ret"] for t in trades if lo <= t["i"] < hi]
        seg = curve[lo:hi]
        print(f"  {label} ({days[lo]} to {days[hi - 1]}): {len(r)} trades, avg {statistics.mean(r):+.1%}, "
              f"sleeve {seg[-1] / seg[0] - 1:+.0%}")

    spy_px = [prices["SPY"][d] for d in days]
    print("\nWhat a 15-trading-day contest would have looked like (every possible start day)")
    print("'Beats SPY' columns are for the WHOLE account: half in the sleeve, other half in cash or in SPY.")
    head2 = (f"{'Variant':<34}{'10th':>8}{'median':>8}{'90th':>8}{'mean':>8}"
             f"{'lose>50%':>10}{'gain>50%':>10}{'beat SPY':>10}{'beat SPY':>10}")
    sub2 = (f"{'':<34}{'pct':>8}{'':>8}{'pct':>8}{'':>8}{'':>10}{'':>10}{'(cash)':>10}{'(SPY)':>10}")
    print(head2 + "\n" + sub2 + "\n" + "-" * len(head2))
    shapes = [
        ("Current rules", {}),
        ("Calls only (sit out bear markets)", dict(puts=False)),
        ("45-day options", dict(dte=45)),
        ("5% in the money", dict(itm=0.05)),
        ("45-day and 5% in the money", dict(dte=45, itm=0.05)),
        ("No trend-flip exit", dict(flip=False)),
        ("Half-size positions (7% each)", dict(slot_pct=SLOT_PCT / 2)),
        ("More leverage: 5% out of the money", dict(itm=-0.05)),
        ("More leverage: 10-day options", dict(dte=10)),
        ("More leverage: 10-day, 5% out", dict(dte=10, itm=-0.05)),
    ]
    for label, kw in shapes:
        t, cv, _ = simulate(feats, days, **kw)
        c = contest(cv, spy_px)
        avg = statistics.mean(x["ret"] for x in t)
        print(f"{label:<34}{c['p10']:>8.0%}{c['med']:>8.0%}{c['p90']:>8.0%}{c['mean']:>8.1%}"
              f"{c['bust']:>10.0%}{c['boom']:>10.0%}{c['beat_cash']:>10.0%}{c['beat_spy']:>10.0%}"
              f"   avg/trade {avg:+.1%}")

    print("\nBuying options vs selling them, with options priced at the level we measured")
    print(f"(implied vol = {IV_MEASURED['stock']} x recent vol for stocks, {IV_MEASURED['index']} x for index funds)")
    head3 = (f"{'Variant':<40}{'trades':>7}{'win%':>6}{'avg/':>8}{'15-day':>8}{'15-day':>8}"
             f"{'lose':>7}{'beat':>7}{'5-yr':>9}{'worst':>7}")
    sub3 = (f"{'':<40}{'':>7}{'':>6}{'trade':>8}{'median':>8}{'10th':>8}{'>50%':>7}{'SPY':>7}{'total':>9}{'drop':>7}")
    print(head3 + "\n" + sub3 + "\n" + "-" * len(head3))
    index = set(C.PENNY_ALL)
    sides = [
        ("BUY  current rules (6 x 14%)", lambda: simulate(feats, days, iv_mult="measured")),
        ("BUY  smaller bets (6 x 7%)", lambda: simulate(feats, days, iv_mult="measured", slot_pct=0.07)),
        ("BUY  small bets (6 x 4%)", lambda: simulate(feats, days, iv_mult="measured", slot_pct=0.04)),
        ("BUY  tiny bets (6 x 2%)", lambda: simulate(feats, days, iv_mult="measured", slot_pct=0.02)),
        ("SELL spreads, all names, 21-day", lambda: simulate_seller(feats, days, dte=21)),
        ("SELL spreads, all names, 45-day", lambda: simulate_seller(feats, days, dte=45)),
        ("SELL spreads, index funds only, 45-day", lambda: simulate_seller(feats, days, dte=45, names=index)),
        ("SELL index only, 45-day, small (4%)", lambda: simulate_seller(feats, days, dte=45, names=index, slot_pct=0.04)),
        ("SELL all names, 45-day, small (4%)", lambda: simulate_seller(feats, days, dte=45, slot_pct=0.04)),
    ]
    for label, run in sides:
        t, cv, _ = run()
        c = contest(cv, spy_px)
        r = [x["ret"] for x in t]
        print(f"{label:<40}{len(r):>7}{sum(x > 0 for x in r) / len(r):>6.0%}{statistics.mean(r):>8.1%}"
              f"{c['med']:>8.0%}{c['p10']:>8.0%}{c['bust']:>7.0%}{c['beat_cash']:>7.0%}"
              f"{cv[-1] / cv[0] - 1:>9.0%}{drawdown(cv):>7.0%}")
    print("For sellers, avg/trade is profit as a share of the most the trade could lose.")

    print("\nCan the bot 'learn' from its own recent results? (15-trading-day windows)")
    print(head2 + "\n" + sub2 + "\n" + "-" * len(head2))
    learners = [
        ("Current rules (no learning)", {}),
        ("Skip a stock 5 days after a loss", dict(cooldown=5)),
        ("Skip a stock 10 days after a loss", dict(cooldown=10)),
        ("Halve size after a losing streak", dict(recent_n=8, after_losses=0.5)),
        ("Quarter size after a losing streak", dict(recent_n=8, after_losses=0.25)),
        ("Bigger size after a winning streak", dict(recent_n=8, after_wins=1.15)),
        ("Bigger size after a LOSING streak", dict(recent_n=8, after_losses=1.15)),
    ]
    for label, kw in learners:
        t, cv, _ = simulate(feats, days, **kw)
        c = contest(cv, spy_px)
        t2, cv2, _ = simulate(feats, days, iv_mult=1.0, stop_exact=True, **kw)
        c2 = contest(cv2, spy_px)
        print(f"{label:<34}{c['p10']:>8.0%}{c['med']:>8.0%}{c['p90']:>8.0%}{c['mean']:>8.1%}"
              f"{c['bust']:>10.0%}{c['boom']:>10.0%}{c['beat_cash']:>10.0%}{c['beat_spy']:>10.0%}"
              f"   optimistic: median {c2['med']:+.0%}, lose>50% {c2['bust']:.0%}, beat {c2['beat_cash']:.0%}")

    print("\nHow much the answer depends on the two big assumptions (current rules)")
    print(f"{'Assumption':<52}{'avg/trade':>10}{'median 15d':>12}{'lose>50%':>10}{'beat SPY':>10}")
    for label, kw in (
        ("Cheap options (IV = 1.0x), stops fill at -50%", dict(iv_mult=1.0, stop_exact=True)),
        ("Cheap options (IV = 1.0x), stops fill at the close", dict(iv_mult=1.0)),
        ("Dear options (IV = 1.2x), stops fill at -50%", dict(iv_mult=1.2, stop_exact=True)),
        ("Measured prices, stops fill at -50%", dict(stop_exact=True)),
        ("Measured prices, stops fill at the close", dict()),
        ("Dear options (IV = 1.2x), stops fill at the close", dict(iv_mult=1.2)),
        ("Very dear options (IV = 1.4x), stops fill at the close", dict(iv_mult=1.4)),
    ):
        t, cv, _ = simulate(feats, days, **kw)
        c = contest(cv, spy_px)
        print(f"{label:<52}{statistics.mean(x['ret'] for x in t):>10.1%}{c['med']:>12.0%}"
              f"{c['bust']:>10.0%}{c['beat_cash']:>10.0%}")

    print("\nSame check for 45-day options")
    for label, kw in (
        ("Cheap options (IV = 1.0x), stops fill at -50%", dict(iv_mult=1.0, stop_exact=True, dte=45)),
        ("Measured prices, stops fill at -50%", dict(stop_exact=True, dte=45)),
        ("Measured prices, stops fill at the close", dict(dte=45)),
        ("Dear options (IV = 1.4x), stops fill at the close", dict(iv_mult=1.4, dte=45)),
    ):
        t, cv, _ = simulate(feats, days, **kw)
        c = contest(cv, spy_px)
        print(f"{label:<52}{statistics.mean(x['ret'] for x in t):>10.1%}{c['med']:>12.0%}"
              f"{c['bust']:>10.0%}{c['beat_cash']:>10.0%}")

if __name__ == "__main__":
    main()
