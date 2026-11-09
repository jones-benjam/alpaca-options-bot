#!/usr/bin/env python3
"""Offline simulation of the bot against a fake broker. No keys, no network.

    python3 sim_test.py

The fake fills marketable orders instantly, which lets us exercise the paths
a dry run never reaches: fills, the ledger, every exit rule, restart recovery
and the kill switch. Prices are made up; this tests the plumbing, not the
strategy's profitability.
"""
import datetime as dt
import itertools
import tempfile
from pathlib import Path

import bot
import config as C

TZ = dt.timezone(dt.timedelta(hours=-5))


class FakeAlpaca:
    def __init__(self):
        self.now = dt.datetime(2026, 11, 10, 10, 30, tzinfo=TZ)
        self.o, self.pos, self.ids = [], {}, itertools.count(1)
        self.px = {s: 100.0 for s in C.UNIVERSE}
        self.mult = {s: 1.0 for s in C.UNIVERSE}  # option price multiplier per underlying
        self.growth = {s: 0.001 for s in C.UNIVERSE}
        self.growth.update(NVDA=0.006, TSLA=0.005, COIN=0.004)

    def iso(self):
        return self.now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")

    def clock(self):
        return {"timestamp": self.now.isoformat(), "is_open": True, "next_open": ""}

    def account(self):
        return {"options_buying_power": "100000"}

    def positions(self):
        return [{"symbol": s, "qty": str(q)} for s, q in self.pos.items() if q]

    def orders(self, status="all", after=None, limit=500, direction="asc"):
        return [] if status == "open" else list(self.o)

    def order(self, oid):
        return next(o for o in self.o if o["id"] == oid)

    def cancel(self, oid):
        pass

    def quote(self, sym):
        root, exp, _, _ = bot.parse_occ(sym)
        base = 0.5 if exp == self.now.date() else 5.0
        mid = round(base * self.mult[root], 2)
        return {"bp": round(mid - 0.02, 2), "ap": round(mid + 0.02, 2), "t": self.iso()}

    def submit(self, symbol, qty, side, client_order_id, limit_price=None):
        q = self.quote(symbol)
        px = limit_price if limit_price is not None else q["bp"]
        ok = limit_price is None or (px >= q["ap"] if side == "buy" else px <= q["bp"])
        order = {
            "id": str(next(self.ids)), "client_order_id": client_order_id, "symbol": symbol,
            "side": side, "submitted_at": self.iso(), "updated_at": self.iso(),
            "filled_at": self.iso() if ok else None,
            "filled_qty": str(qty if ok else 0),
            "filled_avg_price": str(px) if ok else None,
            "status": "filled" if ok else "canceled",
        }
        if ok:
            self.pos[symbol] = self.pos.get(symbol, 0) + (qty if side == "buy" else -qty)
        self.o.append(order)
        self.now += dt.timedelta(seconds=1)
        return order

    def spot(self, s):
        return 100 * (1 + self.growth.get(s, 0.001)) ** 60 * self.px[s] / 100

    def daily_bars(self, symbols, start):
        d0 = dt.date(2026, 9, 1)
        return {
            s: [
                {"c": 100 * (1 + self.growth.get(s, 0.001)) ** i, "t": f"{d0 + dt.timedelta(days=i)}T04:00:00Z"}
                for i in range(60)
            ]
            for s in symbols
        }

    def minute_bars(self, symbols, start, end):
        return {s: [{"h": self.px[s] * 0.999, "l": self.px[s] * 0.99}] * 30 for s in symbols}

    def stock_snapshots(self, symbols):
        return {s: {"latestTrade": {"p": self.spot(s)}} for s in symbols}

    def option_snapshots(self, symbols):
        return {s: {"latestQuote": self.quote(s)} for s in symbols}

    def option_chain(self, und, **f):
        spot = self.spot(und)
        if "expiration_date" in f:
            exp = dt.date.fromisoformat(f["expiration_date"])
        else:
            exp = self.now.date() + dt.timedelta(days=21)
        cp = "C" if f["type"] == "call" else "P"
        out = {}
        for k in range(int(spot * 0.9), int(spot * 1.1)):
            sym = f"{und}{exp:%y%m%d}{cp}{k * 1000:08d}"
            delta = max(0.02, min(0.98, 0.5 - (k - spot) / spot * 5)) * (1 if cp == "C" else -1)
            snap = {"latestQuote": self.quote(sym)}
            if exp != self.now.date():  # like the real feed: no greeks on expiry day
                snap["greeks"] = {"delta": delta}
            out[sym] = snap
        return out


def main():
    bot.Alpaca = FakeAlpaca
    bot.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
    bot.time.sleep = lambda s: None
    C.CORE_MIN_STRENGTH = 0.0  # let the slow synthetic names qualify as replacements
    b = bot.Bot(dry=False)
    f = b.api

    def step(label, **mult):
        f.mult.update(mult)
        f.now += dt.timedelta(minutes=1)
        print(f"\n--- {label} ({f.now:%H:%M}) ---")
        b.last_beat = 0
        fast = b.tick(f.now, True)
        led = b.build_ledger(f.now)
        equity, cash = b.sleeve(led, f.option_snapshots(led.pos))
        book = [(p.tag, p.und, p.qty) for p in led.pos.values()]
        print(f"   => equity {equity:,.0f} cash {cash:,.0f} realized {led.realized:+,.0f} fast={fast} {book}")
        return led, fast

    def unds(led, tag="core"):
        return sorted(p.und for p in led.pos.values() if p.tag == tag)

    led, fast = step("bull market: expect 3 core calls + SPY/QQQ 0DTE calls")
    assert unds(led) == ["COIN", "NVDA", "TSLA"], "core picks"
    assert unds(led, "odte") == ["QQQ", "SPY"], "0DTE picks"
    assert fast, "loop should speed up while a 0DTE position is open"
    start_qty = {p.und: p.qty for p in led.pos.values() if p.tag == "core"}

    led, _ = step("NVDA option -60%: expect stop loss", NVDA=0.4)
    assert "NVDA" not in unds(led), "stop loss"

    led, _ = step("TSLA option +120%: expect half sold", TSLA=2.2)
    assert [p.qty for p in led.pos.values() if p.und == "TSLA"] == [start_qty["TSLA"] - start_qty["TSLA"] // 2], "half"

    led, _ = step("TSLA 35% off its peak: expect trailing stop", TSLA=1.4)
    assert "TSLA" not in unds(led), "trailing stop"

    step("COIN +60% ...", COIN=1.6)
    led, _ = step("... then back to entry: expect breakeven stop", COIN=1.0)
    assert "COIN" not in unds(led), "breakeven stop"

    led, _ = step("SPY 0DTE -60%: expect stop loss on the 0DTE position", SPY=0.4)
    assert unds(led, "odte") == ["QQQ"], "0DTE stop"

    f.now = f.now.replace(hour=15, minute=0)
    led, fast = step("15:01: expect the remaining 0DTE position closed on time")
    assert not unds(led, "odte"), "0DTE time exit"
    assert not fast, "loop should slow down once no 0DTE position is open"

    victim = next(iter(led.pos))
    f.pos[victim] = 0
    f.now += dt.timedelta(minutes=3)
    led, _ = step("teammate sold a bot position: expect write-off")
    assert victim not in led.pos, "write-off"

    fresh = bot.Bot(dry=False)
    fresh.api = f
    again = fresh.build_ledger(f.now)
    assert abs(again.realized - led.realized) < 1e-6 and set(again.pos) == set(led.pos), "restart"
    print("\n--- restart: a new process rebuilt the same book from order history ---")

    C.KILL_FLOOR_PCT = 2.0
    led, _ = step("kill switch forced on: expect everything closed, nothing opened")
    assert not led.pos, "kill switch"

    print("\nALL SIMULATION CHECKS PASSED")


if __name__ == "__main__":
    main()
