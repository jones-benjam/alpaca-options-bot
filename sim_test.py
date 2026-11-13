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
    trend = 1  # +1 builds a rising market, -1 a falling one

    def __init__(self):
        self.now = dt.datetime(2026, 11, 10, 10, 30, tzinfo=TZ)
        self.o, self.pos, self.ids = [], {}, itertools.count(1)
        self.mult = {s: 1.0 for s in C.UNIVERSE}  # option price multiplier per underlying
        self.growth = {s: 0.001 * self.trend for s in C.UNIVERSE}
        self.growth.update(NVDA=0.006 * self.trend, TSLA=0.005 * self.trend, COIN=0.004 * self.trend)
        self.glitch = set()  # underlyings whose option quotes are currently garbage
        self.range = (99.9, 99.0)  # the first 30 minutes' high and low, every symbol
        self.cash = 100_000.0      # the account's real cash
        self.history = {}          # underlying -> past option closes, for peak recovery

    def iso(self):
        return self.now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")

    def clock(self):
        return {"timestamp": self.now.isoformat(), "is_open": True, "next_open": ""}

    def account(self):
        return {"options_buying_power": "100000", "cash": str(self.cash)}

    def option_bars(self, symbol, start, timeframe="15Min"):
        return [{"c": c} for c in self.history.get(bot.parse_occ(symbol)[0], [])]

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
        if root in self.glitch:
            return {"bp": 0.0, "ap": 0.3, "t": self.iso()}
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
        return 100 * (1 + self.growth.get(s, 0.001 * self.trend)) ** 60

    def daily_bars(self, symbols, start):
        d0 = dt.date(2026, 9, 1)
        return {
            s: [
                {"c": 100 * (1 + self.growth.get(s, 0.001 * self.trend)) ** i,
                 "t": f"{d0 + dt.timedelta(days=i)}T04:00:00Z"}
                for i in range(60)
            ]
            for s in symbols
        }

    def minute_bars(self, symbols, start, end):
        return {s: [{"h": self.range[0], "l": self.range[1]}] * 30 for s in symbols}

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


def harness(trend):
    """A fresh bot wired to a fresh fake broker, plus a helper to advance time."""
    FakeAlpaca.trend = trend
    bot.Alpaca = FakeAlpaca
    bot.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
    bot.time.sleep = lambda s: None
    b = bot.Bot(dry=False)
    f = b.api

    def step(label, ticks=1, to_close=None, **mult):
        f.mult.update(mult)
        print(f"\n--- {label} ---")
        b.last_beat = 0
        for _ in range(ticks):
            f.now += dt.timedelta(minutes=1)
            b.last_core_scan = 0
            fast = b.tick(f.now, True, to_close)
        led = b.build_ledger(f.now)
        equity, cash = b.sleeve(led, f.option_snapshots(led.pos))
        book = [(p.tag, p.und, p.kind, p.qty) for p in led.pos.values()]
        print(f"   => equity {equity:,.0f} cash {cash:,.0f} realized {led.realized:+,.0f} fast={fast} {book}")
        return led, fast

    return b, f, step


def unds(led, tag="core"):
    return sorted(p.und for p in led.pos.values() if p.tag == tag)


def test_lifecycle():
    b, f, step = harness(trend=1)

    led, fast = step("bull market, SPY and QQQ both break out upward: expect 3 core calls + ONE 0DTE call")
    assert unds(led) == ["COIN", "NVDA", "TSLA"], "core picks"
    assert unds(led, "odte") == ["SPY"], "only one 0DTE trade a day, even when both indexes break out"
    assert fast, "loop should speed up while a 0DTE position is open"
    start_qty = {p.und: p.qty for p in led.pos.values() if p.tag == "core"}

    led, _ = step("another pass: expect no second 0DTE trade")
    assert unds(led, "odte") == ["SPY"], "0DTE daily limit"

    led, _ = step("NVDA option -60%, first sighting: expect NO sale yet", NVDA=0.4)
    assert "NVDA" in unds(led), "a stop must be confirmed on a second pass"
    led, _ = step("NVDA still -60% on the next pass: expect stop loss")
    assert "NVDA" not in unds(led), "stop loss"

    led, _ = step("TSLA option +120%: expect half sold", TSLA=2.2)
    assert [p.qty for p in led.pos.values() if p.und == "TSLA"] == [start_qty["TSLA"] - start_qty["TSLA"] // 2], "half"

    led, _ = step("TSLA 35% off its peak for two passes: expect trailing stop", ticks=2, TSLA=1.4)
    assert "TSLA" not in unds(led), "trailing stop"

    step("COIN +60% ...", COIN=1.6)
    led, _ = step("... then back to entry for two passes: expect breakeven stop", ticks=2, COIN=1.0)
    assert "COIN" not in unds(led), "breakeven stop"

    before = {s: p.qty for s, p in led.pos.items()}
    equity_before = b.sleeve(led, f.option_snapshots(led.pos))[0]
    f.glitch = {"SPY"}
    led, _ = step("SPY option quotes glitch to a zero bid for three passes: expect no sale", ticks=3)
    assert {s: p.qty for s, p in led.pos.items()} == before, "garbage quotes must not trigger exits"
    assert abs(b.sleeve(led, f.option_snapshots(led.pos))[0] - equity_before) < 1, "glitch must not move sleeve value"
    f.glitch = set()

    led, fast = step("half day, 50 minutes to the close: expect the 0DTE position closed", to_close=50)
    assert not unds(led, "odte"), "0DTE early-close exit"
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

    floor = C.KILL_FLOOR_PCT
    C.KILL_FLOOR_PCT = 2.0
    held = set(led.pos)
    led, _ = step("under the kill floor for two passes: expect no sales yet and no new entries", ticks=2)
    assert set(led.pos) == held, "kill switch must be confirmed before selling"
    led, _ = step("third pass under the floor: expect everything closed")
    assert not led.pos, "kill switch"
    C.KILL_FLOOR_PCT = floor


def test_odte_follows_regime():
    b, f, step = harness(trend=-1)  # falling market: the bot should read "bear"

    f.range = (90.0, 89.0)  # price is far above the morning range: an upside breakout
    led, _ = step("bear market, upside breakout: expect core puts and NO 0DTE call")
    assert all(p.kind == "put" for p in led.pos.values()), "bear market means puts only"
    assert not unds(led, "odte"), "0DTE must not trade against the regime"

    f.range = (99.9, 99.0)  # now price is below the morning range: a downside breakout
    b.range_cache = {}
    led, _ = step("bear market, downside breakout: expect exactly one 0DTE put")
    odte = [p for p in led.pos.values() if p.tag == "odte"]
    assert len(odte) == 1 and odte[0].kind == "put", "0DTE put with the regime"


def test_default_sizing():
    b, f, step = harness(trend=1)
    led, _ = step(f"default settings (${C.SLEEVE_START:,.0f} sleeve): expect {C.CORE_SLOTS} core positions")
    core = [p for p in led.pos.values() if p.tag == "core"]
    assert len(core) == C.CORE_SLOTS, "every core slot should fill"
    assert all(p.cost <= C.CORE_SLOT_PCT * C.SLEEVE_START * 1.01 for p in core), "position size cap"
    assert b.sleeve(led, f.option_snapshots(led.pos))[1] >= 0, "the sleeve must never overspend"


def test_earnings_guard():
    saved = dict(C.EARNINGS_EXIT_BY)
    C.EARNINGS_EXIT_BY.clear()
    C.EARNINGS_EXIT_BY.update({"NVDA": "2026-11-13", "COIN": "2026-11-25"})  # the fake "today" is Nov 10
    b, f, step = harness(trend=1)

    led, _ = step("NVDA reports in 3 days, COIN in 15: expect NVDA skipped, COIN allowed")
    assert "NVDA" not in unds(led), "no new bet inside the earnings blackout"
    assert "COIN" in unds(led) and "TSLA" in unds(led), "names outside the blackout still trade"

    C.EARNINGS_EXIT_BY["TSLA"] = "2026-11-10"  # TSLA now reports tonight
    led, _ = step("TSLA reports tonight, mid-morning: expect it is still held")
    assert "TSLA" in unds(led), "the earnings exit waits for the last half hour"
    f.now = f.now.replace(hour=15, minute=34)
    led, _ = step("TSLA reports tonight, 3:35 pm: expect it sold and not re-bought")
    assert "TSLA" not in unds(led), "sold before the report"

    C.EARNINGS_EXIT_BY.clear()
    C.EARNINGS_EXIT_BY.update(saved)


def test_cash_cap():
    b, f, step = harness(trend=1)
    f.cash = 30.0  # teammates have spent the account's cash
    led, _ = step("account has only $30 of real cash: expect the bot to buy nothing")
    assert not led.pos, "the bot must not borrow"
    f.cash = 300.0
    led, _ = step("account has $300: expect it to spend no more than that")
    assert sum(p.cost for p in led.pos.values()) <= 300, "spending stays inside real cash"
    f.cash = 100_000.0
    led, _ = step("cash is back: expect it to buy")
    assert unds(led), "entries resume once real cash is available"


def test_peak_survives_restart():
    b, f, step = harness(trend=1)
    led, _ = step("open positions, then the bot is redeployed and its disk is wiped")
    assert "TSLA" in unds(led)
    bot.STATE_PATH.unlink(missing_ok=True)       # the host does not keep the disk
    f.history = {"TSLA": [5.0, 8.4, 6.0]}        # TSLA's option was up 68% at its best
    fresh = bot.Bot(dry=False)
    fresh.api = f
    for _ in range(2):                            # price exits need two passes
        f.now += dt.timedelta(minutes=1)
        fresh.tick(f.now, True)
    led = fresh.build_ledger(f.now)
    print(f"\n--- after restart: {[(p.und, p.qty) for p in led.pos.values() if p.tag == 'core']} ---")
    assert "TSLA" not in unds(led), "a winner that fell back to entry is sold even after a restart"
    assert "NVDA" in unds(led) and "COIN" in unds(led), "positions with no big past gain are kept"


def test_trade_memory():
    import memory

    b, f, step = harness(trend=1)
    step("open positions")
    led, _ = step("NVDA option -60% for two passes: stop loss", ticks=2, NVDA=0.4)
    rows = memory.build_trades(led, TZ)
    nvda = next(r for r in rows if r["underlying"] == "NVDA" and r["engine"] == "core")
    assert nvda["status"] == "closed" and nvda["exit"] == "stop", "exit reason is remembered"
    assert nvda["regime"] == "bull" and nvda["signal_pct"] > 0, "entry reason is remembered"
    assert nvda["profit"] < 0 and nvda["profit_pct"] < -50, "result is remembered"
    still = [r for r in rows if r["status"] == "open"]
    assert still and all(r["regime"] == "bull" for r in still), "open trades carry their entry reason"
    fresh = bot.Bot(dry=False)   # a restart must not lose any of it
    fresh.api = f
    assert memory.build_trades(fresh.build_ledger(f.now), TZ) == rows, "memory survives a restart"
    print(f"\n--- trade memory: {len(rows)} trades rebuilt from order ids alone ---")


def main():
    C.CORE_MIN_STRENGTH = 0.0  # let the slow synthetic names qualify as replacements
    test_default_sizing()
    # The scenarios below use the original, smaller setup to stay short.
    C.SLEEVE_START, C.CORE_SLOTS, C.CORE_SLOT_PCT = 25_000.0, 3, 0.28
    test_lifecycle()
    test_odte_follows_regime()
    test_earnings_guard()
    test_cash_cap()
    test_peak_survives_restart()
    test_trade_memory()
    print("\nALL SIMULATION CHECKS PASSED")


if __name__ == "__main__":
    main()
