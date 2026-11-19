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
    track_cash = False  # when True, fills move the account's cash (the free-up test needs it)

    def __init__(self):
        self.now = dt.datetime(2026, 11, 10, 10, 30, tzinfo=TZ)
        self.o, self.pos, self.ids = [], {}, itertools.count(1)
        self.mult = {s: 1.0 for s in C.UNIVERSE}  # option price multiplier per underlying
        self.growth = {s: 0.001 * self.trend for s in C.UNIVERSE}
        self.growth.update(NVDA=0.006 * self.trend, TSLA=0.005 * self.trend, COIN=0.004 * self.trend)
        self.glitch = set()  # underlyings whose option quotes are currently garbage
        self.range = (99.9, 99.0)  # the first 30 minutes' high and low, every symbol
        self.cash = 100_000.0      # the account's real cash
        self.equity = 1e9          # the whole account (very large: the lead lock stays out of the way)
        self.history = {}          # underlying -> past option closes, for peak recovery

    def iso(self):
        return self.now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")

    def clock(self):
        return {"timestamp": self.now.isoformat(), "is_open": True, "next_open": ""}

    def account(self):
        return {"options_buying_power": "100000", "cash": str(self.cash), "equity": str(self.equity)}

    def option_bars(self, symbol, start, timeframe="15Min", end=None):
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
            if self.track_cash:
                self.cash += (-1 if side == "buy" else 1) * px * qty * 100
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
    led, _ = step(f"default settings (${C.SLEEVE_START:,.0f} sleeve): expect bets until the cash runs out")
    core = [p for p in led.pos.values() if p.tag == "core"]
    assert 4 <= len(core) <= C.CORE_SLOTS, "cash, not a fixed slot count, sets how many bets"
    assert all(p.cost >= C.CORE_MIN_BET_SHARE * C.CORE_SLOT_PCT * C.SLEEVE_START * 0.9 for p in core), "no dribble bets"
    odte = [p for p in led.pos.values() if p.tag == "odte"]
    assert odte and odte[0].cost >= C.ODTE_RISK_PCT * C.SLEEVE_START * 0.9, "cash is kept back for a full same-day bet"
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


def test_shadow_scoring():
    """The persona's picks and the rules' top picks are scored on later days only."""
    import csv
    import tempfile

    import memory

    b, f, step = harness(trend=1)
    tmp = Path(tempfile.mkdtemp())
    memory.PICKS, memory.CANDIDATES, memory.SCORES = tmp / "p.csv", tmp / "c.csv", tmp / "s.csv"
    day, last = "2026-09-10", "2026-10-30"   # dates inside the fake price history
    memory.write_csv(memory.PICKS, ["date", "symbol", "direction", "conviction", "why"], [
        {"date": day, "symbol": "NVDA", "direction": "call", "conviction": 5, "why": "rising"},
        {"date": day, "symbol": "TSLA", "direction": "put", "conviction": 2, "why": "contrarian"},
        {"date": last, "symbol": "NVDA", "direction": "call", "conviction": 3, "why": "too new to score"},
    ])
    memory.write_csv(memory.CANDIDATE_FIELDS and memory.CANDIDATES, memory.CANDIDATE_FIELDS, [
        {"date": day, "rank": r, "symbol": sym, "direction": "call", "strength_pct": 5, "price": 100}
        for r, sym in enumerate(["NVDA", "TSLA", "COIN", "SPY"], 1)
    ])
    rows = memory.score_shadow(b)
    get = lambda who, sym, d=day: next(r for r in rows if (r["who"], r["symbol"], r["date"]) == (who, sym, d))
    assert get("trader", "NVDA")["move_1d_pct"] > 0, "a call on a rising stock scores positive"
    assert get("trader", "TSLA")["move_1d_pct"] < 0, "a put on a rising stock scores negative"
    assert get("trader", "NVDA")["move_5d_pct"] > get("trader", "NVDA")["move_1d_pct"], "longer horizon, bigger move"
    assert get("trader", "NVDA", last)["move_1d_pct"] == "", "a pick with no later day is not scored yet"
    assert {r["symbol"] for r in rows if r["who"] == "rules"} == {"NVDA", "TSLA", "COIN"}, "rules = top three only"
    text = "\n".join(memory.shadow_section(rows))
    assert "| trader (AI persona) | 2 | 1 of 2" in text, "the review counts only scored picks"
    print("\n--- shadow picks scored: persona 1 of 2 right, rules judged on their top three ---")


def test_ai_picks():
    """The AI trader's picks go first, but only if the rules approve them."""
    import tempfile

    import live
    import memory

    picks_csv = (
        "date,name,symbol,direction,conviction,why\n"
        "2026-11-06,Midas,QQQ,call,5,too old: replaced by the newer day below\n"
        "2026-11-09,Dionysus,SPY,call,4,rule-approved: goes first\n"
        "2026-11-09,Midas,AAPL,put,5,puts are off in a rising market: rejected\n"
        "2026-11-09,Midas,MSFT,call,2,below the minimum conviction: ignored\n"
        "2026-11-09,Midas,IWM,call,2,low, but Quill agrees: lifted to 3\n"
        "2026-11-09,Quill,IWM,call,2,agreement\n"
        "2026-11-10,Midas,AMD,call,5,made today: not used until tomorrow\n"
    )
    bot.fetch_ai_picks = lambda: picks_csv
    b, f, step = harness(trend=1)
    led, _ = step("bull market with AI picks: SPY (4/5) and IWM (2+1) take two of the three slots")
    assert unds(led) == ["IWM", "NVDA", "SPY"], "AI picks first, the rules' strongest fills the rest"
    rows = {r["underlying"]: r for r in memory.build_trades(led, TZ) if r["engine"] == "core"}
    assert (rows["SPY"]["source"], rows["SPY"]["ai_conviction"]) == ("ai", "4"), "AI trades are tagged"
    assert (rows["IWM"]["source"], rows["NVDA"]["source"]) == ("ai", "rules")
    assert rows["SPY"]["regime"] == "bull" and rows["SPY"]["signal_pct"] != "", "the rest of the tag still reads"
    status = {(p["symbol"], p["kind"]): p["status"] for p in live._ai_status(b, led, f.now)["picks"]}
    assert status == {("SPY", "call"): "bought", ("IWM", "call"): "bought",
                      ("AAPL", "put"): "not bought: puts are off in a bull market"}, \
        "the live page and his desk notes get the bot's verdict on each pick"
    said = {(u, k): why for _, u, k, why in b.ai_said}
    assert said.get(("AAPL", "put")) == "puts are off in a bull market", "a rejected pick is explained"
    ev = next(e for e in led.events if e["side"] == "buy" and parse_und(e["symbol"]) == "SPY" and e["tag"] == "core")
    assert live._reason(ev).endswith("Dionysus's pick 4/5"), "the dashboard says Dionysus chose it"
    b.room = 0.0
    assert b.short_of(50_000).startswith("the lead lock"), "a full lead lock is named as the limit"
    b.room = float("inf")
    assert b.short_of(50_000) == "not enough cash for a proper-size bet", "otherwise it is cash"

    tmp = Path(tempfile.mkdtemp())
    memory.PICKS, memory.CANDIDATES = tmp / "p.csv", tmp / "c.csv"
    memory.PICKS.write_text(picks_csv)
    memory.write_csv(memory.CANDIDATES, memory.CANDIDATE_FIELDS, [
        {"date": "2026-11-10", "rank": 1, "symbol": "NVDA", "direction": "call", "strength_pct": 5, "price": 100}])
    text = "\n".join(memory.ai_section(memory.build_trades(led, TZ)))
    assert "| 2026-11-09 | SPY call | 4/5 | Bought, trade #" in text, "the review shows what was bought"
    assert "| 2026-11-09 | AAPL put | 5/5 | Not bought; the rules no longer approved it |" in text
    assert "MSFT" not in text, "picks under the minimum are not listed as suggestions"

    stale = picks_csv.replace("2026-11-09", "2026-11-01").replace("2026-11-06", "2026-11-01")
    for label, fetch in [("stale picks", lambda: stale),
                         ("GitHub unreachable", lambda: (_ for _ in ()).throw(OSError("offline")))]:
        bot.fetch_ai_picks = fetch
        b, f, step = harness(trend=1)
        led, _ = step(f"{label}: the rules trade alone")
        assert unds(led) == ["COIN", "NVDA", "TSLA"], f"{label}: falls back to the rules"
    C.AI_PICKS = False
    bot.fetch_ai_picks = lambda: picks_csv
    b, f, step = harness(trend=1)
    led, _ = step("AI_PICKS off: the rules trade alone")
    assert unds(led) == ["COIN", "NVDA", "TSLA"], "the switch turns it off"
    C.AI_PICKS = True
    bot.fetch_ai_picks = lambda: ""
    print("\n--- AI picks: approved ones first and tagged, rejected ones explained, safe fallbacks ---")


def test_free_up():
    """Short of cash, Midas sells part of a winner Dionysus named, just enough to buy his strong pick."""
    C.CORE_SLOTS = 4
    bot.fetch_ai_picks, bot.fetch_free_up = (lambda: ""), (lambda: "")
    b, f, step = harness(trend=1)
    f.track_cash = True
    led, _ = step("rules fill the slots")
    held = unds(led)
    target = next(s for s in C.UNIVERSE if s not in held and s not in ("SPY", "QQQ"))
    nvda = next(p for p in led.pos.values() if p.und == "NVDA" and p.tag == "core")
    before = nvda.qty
    C.CORE_SLOTS = len(held) + 1   # one slot free, so cash is the only thing in the way
    f.cash = 300.0   # the shared account is out of cash
    bot.fetch_ai_picks = lambda: f"date,name,symbol,direction,conviction,why\n2026-11-09,Dionysus,{target},call,5,strong\n"
    bot.fetch_free_up = lambda: ("date,name,symbol,direction,why\n2026-11-09,Dionysus,TSLA,call,up a little only\n"
                                 "2026-11-09,Dionysus,NVDA,call,biggest winner\n")
    b.ai["for"] = b.fu["for"] = ""
    led, _ = step(f"cash gone, Dionysus rates {target} 5/5 and names TSLA and NVDA: NVDA is up 50%, TSLA only 5%",
                  NVDA=1.5, TSLA=1.05)
    after = next(p for p in led.pos.values() if p.und == "NVDA" and p.tag == "core").qty
    sold = [e for e in led.events if e["side"] == "sell" and e["meta"] == "x_fund"]
    assert target in unds(led), "the strong pick was bought with the freed cash"
    assert sold and parse_und(sold[0]["symbol"]) == "NVDA", "only the named winner in profit was sold"
    assert 0 < before - after < before, "only part of the winner was sold, not all of it"
    assert any(why.startswith("up only") for _, u, _, why in b.fu_said if u == "TSLA"), "TSLA (+5%) was spared"
    status = {p["symbol"]: p["status"] for p in live_status(b, led, f)["picks"]}
    assert status[target].startswith("bought after selling"), "the page says what was sold for it"
    second = next(s for s in C.UNIVERSE if s not in unds(led) and s not in ("SPY", "QQQ"))
    C.CORE_SLOTS += 1
    f.cash = 300.0
    bot.fetch_ai_picks = lambda: f"date,name,symbol,direction,conviction,why\n2026-11-09,Dionysus,{second},call,5,again\n"
    b.ai["for"] = ""
    led, _ = step("cash gone again the same day: no second sale")
    assert len([e for e in led.events if e["meta"] == "x_fund"]) == len(sold), "at most one free-up a day"
    assert second not in unds(led), "so the second pick waits"
    C.AI_FREE_UP = False
    f.cash, b.freed, b.ai["for"], b.fu_said = 300.0, {}, "", set()
    led, _ = step("free-up switched off")
    assert len([e for e in led.events if e["meta"] == "x_fund"]) == len(sold), "AI_FREE_UP=0 stops it"
    C.AI_FREE_UP, C.CORE_SLOTS = True, 3
    bot.fetch_ai_picks = bot.fetch_free_up = lambda: ""
    print(f"\n--- free-up: sold {before - after} of {before} NVDA (+50%) to buy {target}; TSLA (+5%) spared; once a day ---")


def test_dials():
    """Midas applies Dionysus's settings once a day, only inside the hard limits, and can be switched off."""
    import json
    stop0, slots0 = C.CORE_STOP, C.CORE_SLOTS
    hist = [
        {"dial": "CORE_STOP", "from": stop0, "to": round(stop0 * 0.9, 4), "effective": "2026-11-10", "status": "pending"},
        {"dial": "CORE_SLOTS", "from": slots0, "to": slots0 + 9, "effective": "2026-11-09", "status": "active"},
        {"dial": "KILL_FLOOR_PCT", "from": 0.3, "to": 0.0, "effective": "2026-11-09", "status": "active"},
        {"dial": "CORE_TP1", "from": C.CORE_TP1, "to": C.CORE_TP1 * 0.8, "effective": "2026-11-09", "status": "vetoed"},
    ]
    bot.fetch_dials = lambda: json.dumps({"history": hist})
    b, f, step = harness(trend=1)
    step("Dionysus set the stop loss; he also tried 9 more slots, the kill switch, and a vetoed change")
    assert C.CORE_STOP == round(stop0 * 0.9, 4), "a change inside the limits is in force"
    assert C.CORE_SLOTS == slots0 and C.KILL_FLOOR_PCT == 0.30, "too big a step and off-list dials are ignored"
    settings = live_status(b, b.build_ledger(f.now), f)["settings"]
    assert settings == [{"dial": "CORE_STOP", "value": C.CORE_STOP, "was": stop0}], "the page shows what is in force"
    hist[1:] = [{"dial": "CORE_DELTA", "from": C.CORE_DELTA, "to": C.CORE_DELTA * 1.1, "effective": "2026-11-11", "status": "pending"},
                {"dial": "CORE_TRAIL", "from": C.CORE_TRAIL, "to": C.CORE_TRAIL * 1.1, "effective": "2026-11-11", "status": "pending"}]
    delta0, trail0 = C.CORE_DELTA, C.CORE_TRAIL
    step("same day, file changes: nothing moves mid-session")
    assert C.CORE_DELTA == delta0, "settings change only between trading days"
    f.now += bot.dt.timedelta(days=1)
    step("next day: two changes would start at once, so neither does")
    assert (C.CORE_DELTA, C.CORE_TRAIL) == (delta0, trail0) and C.CORE_STOP == round(stop0 * 0.9, 4)
    hist[0]["status"] = "vetoed"
    f.now += bot.dt.timedelta(days=1)
    step("a person vetoed the stop-loss change")
    assert C.CORE_STOP == stop0, "a veto restores Midas's own value"
    hist[0]["status"] = "active"
    C.AI_TUNING = False
    f.now += bot.dt.timedelta(days=1)
    step("AI_TUNING=0")
    assert C.CORE_STOP == stop0, "the switch restores every value"
    C.AI_TUNING = True
    bot.fetch_dials = lambda: ""
    print("\n--- settings: limits enforced by Midas, once a day, one change at a time, veto and switch work ---")


def live_status(b, led, f):
    import live
    return live._ai_status(b, led, f.now)


def parse_und(symbol):
    return bot.parse_occ(symbol)[0]


def test_lead_lock():
    b, f, step = harness(trend=1)
    f.now += dt.timedelta(minutes=1)
    b.tick(f.now, True)                      # first pass learns SPY's starting close
    led = b.build_ledger(f.now)
    for s, p in list(led.pos.items()):       # start from an empty book
        f.pos[s] = 0
    spy_ret = b.market_view(f.now)[0]["SPY"]["px"] / b.spy_base - 1
    floor = C.LOCK_START_VALUE * (1 + spy_ret + C.LOCK_MARGIN_PCT)

    b2, f2, step2 = harness(trend=1)
    f2.equity = floor + 1_000                # a $1,000 cushion: room for $2,000 of options
    led, _ = step2("lead over SPY nearly gone: expect at most $2,000 of new bets")
    spent = sum(p.cost for p in led.pos.values())
    assert spent <= 2_000 * 1.01, f"the lock caps new bets (spent {spent:,.0f})"

    b3, f3, step3 = harness(trend=1)
    led, _ = step3("plenty of lead: expect a full book")
    assert len([p for p in led.pos.values() if p.tag == "core"]) >= 4
    f3.equity = floor - 5_000                # the account has fallen behind the floor
    led, _ = step3("lead gone for three passes: expect everything closed", ticks=3)
    assert not led.pos, "the lock closes everything once the lead is gone"
    print("\n--- lead lock: caps new bets as the lead shrinks, closes everything when it is gone ---")


def test_live_dashboard():
    """The bot publishes a snapshot each pass and the page and JSON are served."""
    import json as _json
    import urllib.request

    import live

    b, f, step = harness(trend=1)
    live._last_publish["at"] = 0
    led, _ = step("one pass with the live dashboard on")
    snap = live._state["snapshot"]
    assert snap and snap["positions"], "a snapshot with the open positions is published"
    assert snap["sleeve"]["value"] > 0 and "lock" in snap and snap["log"], "it carries the sleeve, the lock and recent log lines"
    buys = [t for t in snap["trades"] if t["side"] == "buy"]
    assert buys and all(t["reason"] and t["label"] for t in buys), "the blotter lists each buy with why it was made"
    assert snap["stats"]["buys"] == len(buys) and "win_rate" in snap["stats"], "the win/loss record is published"
    assert all("upnl" in p and "dte" in p for p in snap["positions"]), "positions carry dollar P&L and days left"

    # Score a made-up history: a win, a loss and a partial sale.
    when = dt.datetime(2026, 11, 16, 15, 0, tzinfo=dt.timezone.utc)
    sym_a, sym_b = "NVDA261127P00180000", "AMD261211P00505000"
    led2 = bot.Ledger()
    led2.events = [  # in time order, as the ledger keeps them
        {"when": when, "symbol": sym_a, "side": "buy", "qty": 4, "px": 2.00, "tag": "core", "meta": "e_bear_1570"},
        {"when": when, "symbol": sym_b, "side": "buy", "qty": 1, "px": 10.00, "tag": "odte", "meta": "e_bear_9"},
        {"when": when + dt.timedelta(minutes=30), "symbol": sym_b, "side": "sell", "qty": 1, "px": 10.00, "tag": "odte", "meta": "x_flip", "pnl": 0.0},
        {"when": when + dt.timedelta(hours=2), "symbol": sym_a, "side": "sell", "qty": 2, "px": 6.00, "tag": "core", "meta": "x_half", "pnl": 800.0},
        {"when": when + dt.timedelta(days=1), "symbol": sym_a, "side": "sell", "qty": 2, "px": 1.00, "tag": "core", "meta": "x_stop", "pnl": -200.0},
    ]
    trades, stats = live.blotter(led2, when)
    sells = [t for t in trades if t["side"] == "sell"]
    assert [t["result"] for t in sells] == ["loss", "win", "even"], "newest first, each sale scored"
    assert sells[1]["pnl_pct"] == 200.0 and sells[0]["pnl_pct"] == -50.0, "P&L % is against what was paid"
    assert sells[1]["held"] == "2h 00m" and sells[0]["held"] == "1d 0h", "holding time runs from the first buy"
    assert sells[1]["reason"] == "Took profit on half" and trades[-1]["reason"].startswith("Momentum signal 15.7%")
    assert stats["wins"] == 1 and stats["losses"] == 1 and stats["win_rate"] == 50.0 and stats["profit_factor"] == 4.0
    assert stats["streak"] == {"result": "loss", "n": 1} and stats["realized"] == 600.0
    assert stats["trades_closed"] == 2 and stats["trades_won"] == 1, "a half sale and the rest count as one trade"
    assert stats["by_ticker"][0]["name"] == "NVDA" and stats["by_ticker"][0]["pnl"] == 600.0
    server = live.start_server(0)
    port = server.server_address[1]
    page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode()
    desk = urllib.request.urlopen(f"http://127.0.0.1:{port}/dionysus", timeout=5).read().decode()
    old = urllib.request.urlopen(f"http://127.0.0.1:{port}/midas", timeout=5).read().decode()
    assert "<title>Dionysus Desk</title>" in desk and "desk.json" in desk, "Dionysus's page is served"
    assert old == desk, "the old /midas link still works"
    assert 'href="dionysus"' in page, "the dashboard links to it"
    assert "innerHTML" not in desk, "the AI's words are set as text, never as HTML"
    state = _json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5).read())
    health = urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5).read()
    cors = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5).headers.get("Access-Control-Allow-Origin")
    assert cors == "*", "the GitHub copy of the page may read the data"
    server.shutdown()
    assert "<title>Midas Live</title>" in page and health == b"ok"
    assert state["sleeve"]["value"] == snap["sleeve"]["value"], "the JSON is the published snapshot"
    import os as _os
    secrets = [v for k, v in _os.environ.items() if ("KEY" in k or "SECRET" in k) and len(v) >= 8]
    assert not any(v in _json.dumps(state) for v in secrets), "no keys leak into the page"
    print("\n--- live dashboard: snapshot published, page and JSON served ---")


def main():
    C.CORE_MIN_STRENGTH = 0.0  # let the slow synthetic names qualify as replacements
    bot.fetch_ai_picks = bot.fetch_free_up = bot.fetch_dials = lambda: ""  # no network: nothing from Dionysus unless a test supplies it
    test_default_sizing()
    test_lead_lock()
    test_live_dashboard()
    # The scenarios below use the original, smaller setup and exits to stay short.
    C.SLEEVE_START, C.CORE_SLOTS, C.CORE_SLOT_PCT = 25_000.0, 3, 0.28
    C.CORE_TP1, C.CORE_TRAIL, C.CORE_TRAIL_FROM = 1.0, 0.30, 1.0
    test_lifecycle()
    test_odte_follows_regime()
    test_earnings_guard()
    test_cash_cap()
    test_peak_survives_restart()
    test_trade_memory()
    test_shadow_scoring()
    test_ai_picks()
    test_free_up()
    test_dials()
    print("\nALL SIMULATION CHECKS PASSED")


if __name__ == "__main__":
    main()
