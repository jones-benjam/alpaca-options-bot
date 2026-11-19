#!/usr/bin/env python3
"""Aggressive options bot for an Alpaca PAPER account.

Two engines share a $25k "sleeve" of the account:

  core  Short-dated (about 3 weeks) at-the-money calls or puts on the
        strongest / weakest names in a high-beta universe. Direction follows
        the market regime, so the bot can profit in a falling market too.
  odte  Same-day-expiry SPY/QQQ options bought on a break of the first
        30 minutes' range. Small, frequent lottery tickets.

The bot only ever sells contracts it bought itself. It finds them by the
"optbot-" prefix on its own order ids, so teammates can trade anything else
in the same account. Its book is rebuilt from Alpaca's order history every
loop, which means it survives restarts with no local database.

    python3 bot.py run --dry-run --once   # show what it would do, place nothing
    python3 bot.py run                    # trade (paper) until stopped
    python3 bot.py status                 # sleeve P&L, positions, recent trades
    python3 bot.py journal                # record the day in STRATEGY_LOG.md
    python3 bot.py memory                 # refresh the trade table and review in memory/
"""
import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import re
import time
import traceback
import urllib.request
import uuid
from collections import defaultdict
from pathlib import Path

import config as C
import live
from alpaca import Alpaca, ApiError

OCC = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")
STATE_PATH = Path(C.STATE_FILE) if C.STATE_FILE else Path(__file__).with_name("state.json")
LOG_PATH = Path(__file__).with_name("STRATEGY_LOG.md")
LEGACY_PATH = Path(__file__).with_name("memory") / "legacy_tags.json"
AI_PICKS_PATH = Path(__file__).with_name("memory") / "shadow_picks.csv"
AI_FREE_UP_PATH = Path(__file__).with_name("memory") / "free_up.csv"
# Why an order was placed is written into its id, so the record lives at the
# broker and survives restarts. Entries: e_<regime>_<signal in 1/100 of a %>,
# plus _ai<conviction> when Dionysus (the AI trader) suggested it.
# Exits: x_<one of the codes below>.
EXIT_CODES = {
    "stop loss": "stop", "trailing stop": "trail", "breakeven stop": "be",
    "trend flipped": "flip", "time stop": "time", "earnings report tonight": "earn",
    "take profit on half": "half", "expiry-day time exit": "exp", "flatten": "flat",
    "freed cash for Dionysus's pick": "fund",
}
try:  # reasons for orders placed before ids carried them, reconstructed from the logs
    LEGACY = json.loads(LEGACY_PATH.read_text()) if LEGACY_PATH.exists() else {}
except (ValueError, OSError):
    LEGACY = {}


def order_meta(client_order_id):
    parts = client_order_id.split("-")
    if len(parts) >= 4 and parts[2][:2] in ("e_", "x_"):
        return parts[2]
    return LEGACY.get(client_order_id, "")


def _ai_file(path, url):
    """One of Dionysus's files as text. On the Mac mini it is on disk; on a
    cloud host it is read from GitHub, where the Mac mini saves it."""
    if path.exists():
        return path.read_text()
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.read().decode()


def fetch_ai_picks():
    return _ai_file(AI_PICKS_PATH, C.AI_PICKS_URL)


def fetch_free_up():
    return _ai_file(AI_FREE_UP_PATH, C.AI_FREE_UP_URL)


def parse_free_up(text, today):
    """The open bets Dionysus said may be sold to fund his picks, from his latest
    list made before `today`, in his order: [(symbol, call|put)]."""
    rows = [r for r in csv.DictReader(io.StringIO(text))
            if r.get("symbol") and (r.get("date") or "") < today and (r.get("name") or C.AI_TRADER) in C.ai_names()]
    if not rows:
        return []
    day = max(r["date"] for r in rows)
    try:
        if (dt.date.fromisoformat(today) - dt.date.fromisoformat(day)).days > C.AI_MAX_AGE_DAYS:
            return []
    except ValueError:
        return []
    out = []
    for r in rows:
        key = (r["symbol"].strip().upper(), (r.get("direction") or "").strip())
        if r["date"] == day and key not in out:
            out.append(key)
    return out[:2]


def parse_ai_picks(text, today):
    """The AI trader's latest picks made before `today` (YYYY-MM-DD), as
    ({(symbol, call|put): conviction}, pick date). A pick another persona also
    made gets one extra point; picks under AI_MIN_CONVICTION are dropped."""
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r.get("symbol") and (r.get("date") or "") < today]
    if not rows:
        return {}, ""
    day = max(r["date"] for r in rows)
    try:
        if (dt.date.fromisoformat(today) - dt.date.fromisoformat(day)).days > C.AI_MAX_AGE_DAYS:
            return {}, day
    except ValueError:
        return {}, ""
    mine, others = {}, set()
    for r in rows:
        if r["date"] != day:
            continue
        key = (r["symbol"].strip().upper(), (r.get("direction") or "").strip())
        try:
            conv = int(r.get("conviction") or 0)
        except ValueError:
            continue
        if (r.get("name") or C.AI_TRADER) in C.ai_names():
            mine[key] = max(mine.get(key, 0), conv)
        else:
            others.add(key)
    picks = {k: min(5, c + (k in others)) for k, c in mine.items()}
    return {k: c for k, c in picks.items() if c >= C.AI_MIN_CONVICTION}, day


TERMINAL = {"filled", "canceled", "expired", "rejected", "done_for_day", "replaced"}


try:  # log in market time when the host has timezone data
    from zoneinfo import ZoneInfo

    ET = ZoneInfo("America/New_York")
except Exception:
    ET = None


def log(msg):
    now = dt.datetime.now(ET) if ET else dt.datetime.now()
    line = f"{now:%Y-%m-%d %H:%M:%S}{' ET' if ET else ''}  {msg}"
    print(line, flush=True)
    live.remember(line)  # shown on the live dashboard


def parse_ts(text):
    """Parse Alpaca timestamps (nanoseconds, trailing Z) on any Python 3.9+."""
    return dt.datetime.fromisoformat(re.sub(r"\.\d+", "", text).replace("Z", "+00:00"))


def parse_occ(symbol):
    m = OCC.match(symbol)
    if not m:
        return None
    root, yy, mm, dd, cp, strike = m.groups()
    expiry = dt.date(2000 + int(yy), int(mm), int(dd))
    return root, expiry, "call" if cp == "C" else "put", int(strike) / 1000


def ema(values, n):
    k = 2 / (n + 1)
    e = sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def est_delta(spot, strike, days, sigma, kind):
    """Black-Scholes delta, used when the data feed supplies no greeks."""
    sd = max(sigma, 0.05) * math.sqrt(max(days, 0.5) / 365)
    d1 = (math.log(spot / strike) + 0.5 * sd * sd) / sd
    n = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    return n if kind == "call" else n - 1


def read_quote(snap, now=None):
    """Return (bid, ask, mid) or None. With `now`, also reject stale quotes."""
    q = (snap or {}).get("latestQuote") or {}
    bid, ask = float(q.get("bp") or 0), float(q.get("ap") or 0)
    if ask <= 0 or ask < bid:
        return None
    if now is not None and q.get("t"):
        if (now - parse_ts(q["t"])).total_seconds() > C.QUOTE_MAX_AGE_SEC:
            return None
    return bid, ask, (bid + ask) / 2


def quote_ok(q):
    """A quote good enough to act on or value with: a real bid and a spread
    that is not absurd. The free feed is approximate and can glitch."""
    return bool(q) and q[0] > 0 and (q[1] - q[0] <= 0.05 or (q[1] - q[0]) / q[2] <= C.MAX_TRIGGER_SPREAD)


def earnings_days(underlying, today):
    """Days until the last safe session before this stock's earnings report,
    if that is within the blackout window; otherwise None. 0 means the report
    comes out after today's close."""
    if C.HOLD_THROUGH_EARNINGS or underlying not in C.EARNINGS_EXIT_BY:
        return None
    days = (dt.date.fromisoformat(C.EARNINGS_EXIT_BY[underlying]) - today).days
    return days if 0 <= days <= C.EARNINGS_BLACKOUT_DAYS else None


def tick_for(underlying, price):
    return 0.01 if underlying in C.PENNY_ALL or price < 3 else 0.05


def round_to(price, tick, up):
    n = price / tick
    n = math.ceil(n - 1e-9) if up else math.floor(n + 1e-9)
    return round(max(tick, n * tick), 2)


class Pos:
    def __init__(self, symbol, tag):
        self.symbol, self.tag = symbol, tag
        self.und, self.expiry, self.kind, self.strike = parse_occ(symbol)
        self.qty = 0          # contracts held
        self.cost = 0.0       # dollars paid for what is still held
        self.sold = 0         # contracts sold since this position was opened
        self.last_buy = None

    @property
    def avg(self):            # average premium per share
        return self.cost / self.qty / 100

    def label(self):
        return f"{self.und} {self.expiry:%m/%d} {self.strike:g}{self.kind[0].upper()}"


class Ledger:
    def __init__(self):
        self.pos = {}         # option symbol -> Pos
        self.realized = 0.0
        self.today = set()    # (tag, underlying) pairs with a fill today
        self.closed = []      # (time, symbol, qty, price, pnl dollars)
        self.opened = []      # (time, symbol, qty, price)
        self.events = []      # every fill, with the reason it was placed (the trade memory)


class Bot:
    def __init__(self, dry):
        self.api = Alpaca()
        self.dry = dry
        self.closes, self.bars_at, self.bars_day = {}, 0.0, ""
        self.range_cache = {}
        self.attempts = defaultdict(int)
        self.last_beat = 0.0
        self.last_core_scan = 0.0
        self.to_close = 24 * 60.0          # minutes until today's close
        self.exit_hits = defaultdict(int)  # consecutive passes a price exit was seen
        self.halt_hits = 0                 # consecutive passes under the kill floor
        self.marks = {}                    # last believable price per held option
        self.peak_tried = set()            # positions whose best price was looked up
        self.spy_base = None               # SPY's last close before the contest began
        self.room = float("inf")           # how much more the lead lock lets the bot invest
        self.qnow = None      # set while the market is open, to age-check quotes
        self.ai = {"for": "", "at": 0.0, "picks": {}, "day": None}  # Dionysus's picks for today
        self.ai_said = set()  # (day, symbol, direction, reason) already logged
        self.fu = {"for": "", "at": 0.0, "list": []}  # bets Dionysus said may be sold to fund a pick
        self.freed = {}       # day -> [(pick symbol, kind, what was sold)], at most AI_FREE_UP_MAX_PER_DAY
        self.fu_said = set()  # (day, symbol, direction, reason) already logged for free-up checks
        self.state = {"peaks": {}, "synthetic": []}
        if STATE_PATH.exists():
            try:
                self.state.update(json.loads(STATE_PATH.read_text()))
            except (ValueError, OSError):
                log("state.json unreadable, starting fresh")

    # ---- bookkeeping ---------------------------------------------------------
    def save_state(self):
        if self.dry:
            return
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        tmp.replace(STATE_PATH)

    def cid(self, tag, meta=""):
        """Order id. `meta` records why the order exists (see EXIT_CODES)."""
        return f"{C.BOT_TAG}-{tag}-{meta + '-' if meta else ''}{uuid.uuid4().hex[:16]}"

    def bot_orders(self):
        found, after = {}, f"{C.START_DATE}T00:00:00Z"
        while True:
            page = self.api.orders(status="all", after=after, limit=500, direction="asc")
            for o in page:
                if (o.get("client_order_id") or "").startswith(C.BOT_TAG + "-"):
                    found[o["id"]] = o
            if len(page) < 500 or page[-1]["submitted_at"] == after:
                return list(found.values())
            after = page[-1]["submitted_at"]

    def build_ledger(self, now, until=None):
        """Rebuild the bot's positions and realized P&L from its own fills.
        `until` (YYYY-MM-DD) rebuilds the book as it stood at that day's close."""
        fills = []
        for o in self.bot_orders():
            qty = int(float(o.get("filled_qty") or 0))
            if qty > 0 and o.get("filled_avg_price") and parse_occ(o["symbol"]):
                when = parse_ts(o.get("filled_at") or o.get("updated_at") or o["submitted_at"])
                tag = o["client_order_id"].split("-")[1]
                meta = order_meta(o["client_order_id"])
                fills.append((when, o["symbol"], o["side"], qty, float(o["filled_avg_price"]), tag, meta))
        for s in self.state["synthetic"]:
            fills.append((parse_ts(s["at"]), s["symbol"], "sell", s["qty"], s["px"], "writeoff", "x_writeoff"))
        fills.sort(key=lambda f: f[0])

        led, today = Ledger(), now.date()
        if until:
            today = dt.date.fromisoformat(until)
            fills = [f for f in fills if f[0].astimezone(now.tzinfo).date() <= today]
        for when, symbol, side, qty, px, tag, meta in fills:
            if side == "buy":
                p = led.pos.setdefault(symbol, Pos(symbol, tag))
                p.qty += qty
                p.cost += qty * px * 100
                p.last_buy = when
                led.opened.append((when, symbol, qty, px))
                led.events.append({"when": when, "symbol": symbol, "side": "buy", "qty": qty,
                                   "px": px, "tag": tag, "meta": meta})
                if when.astimezone(now.tzinfo).date() == today:
                    led.today.add((tag, p.und))
            else:
                p = led.pos.get(symbol)
                if not p:
                    continue
                qty = min(qty, p.qty)
                per = p.cost / p.qty
                pnl = qty * (px * 100 - per)
                led.realized += pnl
                led.closed.append((when, symbol, qty, px, pnl))
                led.events.append({"when": when, "symbol": symbol, "side": "sell", "qty": qty,
                                   "px": px, "tag": p.tag, "meta": meta, "pnl": pnl})
                p.cost -= per * qty
                p.qty -= qty
                p.sold += qty
                if p.qty == 0:
                    del led.pos[symbol]
        for symbol, p in list(led.pos.items()):
            if p.expiry < today:  # should never happen: exits run before expiry
                log(f"WARNING {symbol} expired while held; booking it as a total loss")
                led.realized -= p.cost
                led.closed.append((now, symbol, p.qty, 0.0, -p.cost))
                led.events.append({"when": now, "symbol": symbol, "side": "sell", "qty": p.qty,
                                   "px": 0.0, "tag": p.tag, "meta": "x_expired", "pnl": -p.cost})
                del led.pos[symbol]
        return led

    def sleeve(self, led, quotes):
        cost = sum(p.cost for p in led.pos.values())
        value = 0.0
        for symbol, p in led.pos.items():
            q = read_quote(quotes.get(symbol))
            if quote_ok(q):
                self.marks[symbol] = q[2]
            # A bad quote is valued at the last good mark, so a feed glitch
            # cannot fake a collapse of the sleeve and trip the kill switch.
            mark = self.marks.get(symbol)
            value += p.qty * mark * 100 if mark is not None else p.cost
        cash = C.SLEEVE_START + led.realized - cost
        return cash + value, cash

    # ---- signals -------------------------------------------------------------
    def market_view(self, now):
        today = now.date().isoformat()
        symbols = sorted(set(C.UNIVERSE) | set(C.INDEX) | set(C.ODTE_SYMBOLS))
        if time.time() - self.bars_at > 1800 or self.bars_day != today:
            start = (now.date() - dt.timedelta(days=75)).isoformat()
            bars = self.api.daily_bars(symbols, start)
            self.closes = {s: [b["c"] for b in bs if b["t"][:10] < today] for s, bs in bars.items()}
            before = [b["c"] for b in bars.get("SPY", []) if b["t"][:10] < C.START_DATE]
            self.spy_base = before[-1] if before else None  # SPY's close before the contest
            self.bars_at, self.bars_day = time.time(), today
        snaps = self.api.stock_snapshots(symbols)
        view = {}
        for s in symbols:
            hist = self.closes.get(s) or []
            px = ((snaps.get(s) or {}).get("latestTrade") or {}).get("p")
            if not px or len(hist) < 25:
                continue
            c = hist + [float(px)]
            rets = [math.log(c[i] / c[i - 1]) for i in range(len(c) - 20, len(c))]
            mean = sum(rets) / len(rets)
            rv = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) * 252)
            r5, r20 = c[-1] / c[-6] - 1, c[-1] / c[-21] - 1
            view[s] = {
                "px": c[-1], "ema10": ema(c, 10), "ema20": ema(c, 20),
                "r5": r5, "r20": r20, "score": 0.6 * r5 + 0.4 * r20, "rv": rv,
            }
        idx = [view[s] for s in C.INDEX if s in view]
        if len(idx) < len(C.INDEX):
            regime = "unknown"
        elif all(v["px"] > v["ema20"] for v in idx):
            regime = "bull"
        elif all(v["px"] < v["ema20"] for v in idx):
            regime = "bear"
        else:
            regime = "mixed"
        return view, regime

    def candidates(self, view, regime):
        """Ranked (strength, symbol, call|put). Calls on leaders, puts on laggards."""
        out = []
        for s in C.UNIVERSE:
            v = view.get(s)
            if not v:
                continue
            if v["px"] > v["ema10"] and v["r5"] > 0 and v["score"] > 0:
                out.append((v["score"], s, "call"))
            elif v["px"] < v["ema10"] and v["r5"] < 0 and v["score"] < 0:
                out.append((-v["score"], s, "put"))
        if regime == "bull":
            out = [c for c in out if c[2] == "call"]
        elif regime == "bear":
            out = [c for c in out if c[2] == "put"]
        elif regime == "unknown":
            out = []
        return sorted(c for c in out if c[0] >= C.CORE_MIN_STRENGTH)[::-1]

    # ---- contract selection ----------------------------------------------------
    def pick_core(self, und, kind, v, today):
        chain = self.api.option_chain(
            und,
            type=kind,
            expiration_date_gte=(today + dt.timedelta(days=C.CORE_DTE_MIN)).isoformat(),
            expiration_date_lte=(today + dt.timedelta(days=C.CORE_DTE_MAX)).isoformat(),
            strike_price_gte=f"{v['px'] * 0.85:.2f}",
            strike_price_lte=f"{v['px'] * 1.15:.2f}",
        )
        by_expiry = defaultdict(list)
        for symbol, snap in chain.items():
            occ = parse_occ(symbol)
            q = read_quote(snap, self.qnow)
            if not occ or occ[0] != und or occ[2] != kind or not q:
                continue
            bid, ask, mid = q
            if bid <= 0 or ask < C.MIN_OPTION_ASK or (ask - bid) / mid > C.CORE_MAX_SPREAD:
                continue
            _, expiry, _, strike = occ
            dte = (expiry - today).days
            delta = (snap.get("greeks") or {}).get("delta")
            if delta is None:
                sigma = snap.get("impliedVolatility") or v["rv"] * 1.2
                delta = est_delta(v["px"], strike, dte, sigma, kind)
            by_expiry[expiry].append(
                {"symbol": symbol, "ask": ask, "bid": bid, "delta": delta, "dte": dte}
            )
        for expiry in sorted(by_expiry, key=lambda e: abs((e - today).days - C.CORE_DTE_TARGET)):
            best = min(by_expiry[expiry], key=lambda c: abs(abs(c["delta"]) - C.CORE_DELTA))
            if abs(abs(best["delta"]) - C.CORE_DELTA) <= C.CORE_DELTA_TOL:
                return best
        return None

    def pick_odte(self, und, kind, px, today):
        chain = self.api.option_chain(
            und,
            type=kind,
            expiration_date=today.isoformat(),
            strike_price_gte=f"{px * 0.98:.2f}",
            strike_price_lte=f"{px * 1.02:.2f}",
        )
        target = px * (1 + C.ODTE_OTM) if kind == "call" else px * (1 - C.ODTE_OTM)
        best = None
        for symbol, snap in chain.items():
            occ = parse_occ(symbol)
            q = read_quote(snap, self.qnow)
            if not occ or occ[0] != und or occ[1] != today or occ[2] != kind or not q:
                continue
            bid, ask, mid = q
            if bid <= 0 or ask < C.MIN_OPTION_ASK or (ask - bid) / mid > C.ODTE_MAX_SPREAD:
                continue
            gap = abs(occ[3] - target)
            if best is None or gap < best["gap"]:
                best = {"symbol": symbol, "ask": ask, "bid": bid, "gap": gap, "strike": occ[3]}
        return best

    def opening_range(self, now):
        day = now.date()
        if day not in self.range_cache:
            off = now.strftime("%z")
            off = off[:3] + ":" + off[3:]
            bars = self.api.minute_bars(
                C.ODTE_SYMBOLS, f"{day}T09:30:00{off}", f"{day}T09:59:00{off}"
            )
            ranges = {
                s: (max(b["h"] for b in bs), min(b["l"] for b in bs))
                for s, bs in bars.items()
                if len(bs) >= 15
            }
            if len(ranges) < len(C.ODTE_SYMBOLS):
                return ranges  # incomplete data: do not cache, ask again next pass
            self.range_cache = {day: ranges}
        return self.range_cache[day]

    # ---- execution -----------------------------------------------------------
    def wait(self, order, seconds):
        """Poll an order; cancel what is left at the deadline. -> (filled, avg)."""
        deadline = time.time() + seconds
        o = order
        while time.time() < deadline:
            o = self.api.order(order["id"])
            if o["status"] in TERMINAL:
                break
            time.sleep(1.5)
        else:
            self.api.cancel(order["id"])
            for _ in range(6):
                o = self.api.order(order["id"])
                if o["status"] in TERMINAL:
                    break
                time.sleep(1)
        return int(float(o.get("filled_qty") or 0)), float(o.get("filled_avg_price") or 0)

    def buy(self, und, symbol, qty, tag, note, meta=""):
        log(f"BUY  {qty} x {symbol} [{tag}] {note}" + (" (dry run, not sent)" if self.dry else ""))
        if self.dry:
            return qty
        got, left = 0, qty
        for frac in (0.5, 1.0, 1.0):  # half-way to the ask, then the ask
            q = read_quote(self.api.option_snapshots([symbol]).get(symbol), self.qnow)
            if not q:
                break
            bid, ask, mid = q
            price = round_to(mid + frac * (ask - mid), tick_for(und, ask), up=True)
            try:
                order = self.api.submit(symbol, left, "buy", self.cid(tag, meta), limit_price=price)
            except ApiError as err:
                log(f"     buy rejected: {err}")
                break
            filled, avg = self.wait(order, 8)
            if filled:
                log(f"     filled {filled} @ ${avg:.2f}")
            got, left = got + filled, left - filled
            if left <= 0:
                break
        if left > 0:
            log(f"     {left} unfilled, cancelled")
        return got

    def sell(self, p, qty, reason, mid):
        pnl = f"{mid / p.avg - 1:+.0%}" if mid else "n/a"
        log(
            f"SELL {qty} x {p.symbol} [{p.tag}] {reason}, P&L {pnl}"
            + (" (dry run, not sent)" if self.dry else "")
        )
        if self.dry or qty <= 0:
            return 0
        why = "x_" + EXIT_CODES.get(reason, "other")
        done, left = 0, qty
        for attempt in range(3):  # at the bid, one tick lower, then market
            q = read_quote(self.api.option_snapshots([p.symbol]).get(p.symbol))
            bid = q[0] if q else 0
            tick = tick_for(p.und, bid or 1)
            try:
                if attempt < 2 and bid > 0:
                    price = round_to(bid - attempt * tick, tick, up=False)
                    order = self.api.submit(p.symbol, left, "sell", self.cid(p.tag, why), limit_price=price)
                else:
                    order = self.api.submit(p.symbol, left, "sell", self.cid(p.tag, why))
            except ApiError as err:
                log(f"     sell rejected: {err}")
                break
            filled, avg = self.wait(order, 8)
            if filled:
                log(f"     sold {filled} @ ${avg:.2f}")
            done, left = done + filled, left - filled
            if left <= 0:
                break
        if left > 0:
            log(f"     {left} still unsold, will retry next loop")
        return done

    def cancel_stale(self):
        for o in self.api.orders(status="open", limit=500, direction="desc"):
            if (o.get("client_order_id") or "").startswith(C.BOT_TAG + "-"):
                self.api.cancel(o["id"])

    # ---- position management ---------------------------------------------------
    def restore_peaks(self, led):
        """Recover each position's best price since entry from Alpaca's price
        history. The trailing and breakeven stops depend on it, and the local
        copy is lost whenever the bot is redeployed (the host's disk is not
        kept), so without this a restart would quietly disarm those stops."""
        peaks = self.state["peaks"]
        for symbol, p in led.pos.items():
            if symbol in peaks or symbol in self.peak_tried:
                continue
            self.peak_tried.add(symbol)
            until = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16)  # free-plan delay
            if p.last_buy.astimezone(dt.timezone.utc) >= until:
                peaks[symbol] = p.avg  # bought minutes ago: no history yet, and none needed
                continue
            try:
                since = p.last_buy.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                bars = self.api.option_bars(symbol, since, end=until.strftime("%Y-%m-%dT%H:%M:%SZ"))
            except ApiError as err:
                log(f"could not restore best price for {symbol}: {err}")
                continue
            best = max([p.avg] + [float(b["c"]) for b in bars])
            peaks[symbol] = best
            if best > p.avg * 1.01:
                log(f"restored best price for {p.label()}: ${best:.2f} ({best / p.avg - 1:+.0%} vs entry)")

    def manage(self, now, led, quotes, view, flatten):
        """Apply exit rules to every position the bot holds. True if it traded."""
        if not led.pos:
            if self.state["peaks"]:
                self.state["peaks"] = {}
                self.save_state()
            return False
        today, hhmm = now.date(), now.strftime("%H:%M")
        held = {x["symbol"]: int(float(x["qty"])) for x in self.api.positions()}
        self.restore_peaks(led)
        peaks, acted = self.state["peaks"], False
        for symbol, p in list(led.pos.items()):
            q = read_quote(quotes.get(symbol))
            mid = q[2] if q else None

            # Someone else closed contracts the bot owned: book them at the mark.
            have = held.get(symbol, 0)
            if have < p.qty and not self.dry and (now - p.last_buy).total_seconds() > 120:
                gone = p.qty - have
                log(f"WARNING {gone} x {symbol} left the account outside the bot; writing off at mark")
                self.state["synthetic"].append(
                    {"symbol": symbol, "qty": gone, "px": mid or 0.0, "at": now.isoformat()}
                )
                self.save_state()
                acted = True
                continue

            odte = p.tag == "odte"
            stop, tp1, trail = (
                (C.ODTE_STOP, C.ODTE_TP1, C.ODTE_TRAIL) if odte else (C.CORE_STOP, C.CORE_TP1, C.CORE_TRAIL)
            )
            dte = (p.expiry - today).days
            reason, qty = None, p.qty
            sane = quote_ok(q)  # price rules only act on a believable quote
            if flatten:
                reason = "flatten"
            elif dte <= 0 and (hhmm >= C.ODTE_EXIT_AT or self.to_close <= C.ODTE_EXIT_MIN_TO_CLOSE):
                reason = "expiry-day time exit"
            elif not odte and dte <= C.CORE_MIN_DTE_EXIT:
                reason = "time stop"
            elif (
                not odte
                and earnings_days(p.und, today) == 0
                and (hhmm >= C.FLIP_CHECK_FROM or self.to_close <= C.FLIP_MIN_TO_CLOSE)
            ):
                reason = "earnings report tonight"  # do not hold through the report
            elif sane:
                peak = max(peaks.get(symbol, p.avg), mid)
                peaks[symbol] = peak
                pnl = mid / p.avg - 1
                v = view.get(p.und)
                price_exit = None
                if pnl <= stop:
                    price_exit = "stop loss"
                elif peak >= p.avg * (1 + (tp1 if odte else C.CORE_TRAIL_FROM)) and mid <= peak * (1 - trail):
                    price_exit = "trailing stop"
                elif peak >= p.avg * 1.5 and mid <= p.avg * 1.05:
                    price_exit = "breakeven stop"
                # A price exit must show on consecutive passes, so one bad tick
                # cannot close a position.
                self.exit_hits[symbol] = self.exit_hits[symbol] + 1 if price_exit else 0
                near_close = hhmm >= C.FLIP_CHECK_FROM or self.to_close <= C.FLIP_MIN_TO_CLOSE
                if price_exit:
                    if self.exit_hits[symbol] >= C.EXIT_CONFIRMATIONS:
                        reason = price_exit
                elif not odte and v and near_close and (
                    (p.kind == "call" and v["px"] < v["ema10"])
                    or (p.kind == "put" and v["px"] > v["ema10"])
                ):
                    reason = "trend flipped"
                elif p.sold == 0 and p.qty >= 2 and pnl >= tp1:
                    reason, qty = "take profit on half", p.qty // 2
            if reason:
                try:
                    self.sell(p, qty, reason, mid)
                except ApiError as err:  # keep managing the other positions
                    log(f"     sell of {symbol} failed, will retry next pass: {err}")
                acted = True
        for symbol in [s for s in peaks if s not in led.pos]:
            del peaks[symbol]
        for symbol in [s for s in self.exit_hits if s not in led.pos]:
            del self.exit_hits[symbol]
        self.save_state()
        return acted

    # ---- entries -------------------------------------------------------------
    def lead_lock(self, view, equity, cash):
        """Keep the whole account ahead of SPY. Returns (note for the log, breached).

        floor   = the account's start value grown by SPY's return, plus a margin
        cushion = the account's value above that floor
        The bot may hold options worth up to LOCK_MULTIPLIER x cushion. Self.room
        is what is left of that allowance for new bets."""
        self.room = float("inf")
        if not C.LOCK_ENABLED or not self.spy_base or "SPY" not in view:
            return "", False
        acct = float(self.api.account().get("equity") or 0)
        if acct <= 0:
            return "", False
        spy_ret = view["SPY"]["px"] / self.spy_base - 1
        floor = C.LOCK_START_VALUE * (1 + spy_ret + C.LOCK_MARGIN_PCT)
        cushion = acct - floor
        exposure = max(0.0, equity - cash)  # what the bot's open options are worth
        self.room = max(0.0, C.LOCK_MULTIPLIER * cushion - exposure)
        note = (f" | lead lock: account ${acct:,.0f}, floor ${floor:,.0f}, "
                f"room for new bets ${self.room:,.0f}")
        return note, cushion <= 0

    def budget(self, pct, equity, cash):
        """Dollars available for one new position. Never more than the account's
        real cash: the account is shared, and if teammates have spent it the
        broker would otherwise lend the difference on margin without asking."""
        acct = self.api.account()
        power = float(acct.get("options_buying_power") or 0)
        real_cash = float(acct.get("cash") or 0)
        return max(0.0, min(pct * equity, cash * 0.98, power, real_cash * 0.98, self.room))

    # ---- Dionysus's suggestions ---------------------------------------------------
    def ai_picks(self, today):
        """Dionysus's picks to try first today, {(symbol, kind): conviction}.
        Read once a day; until they arrive, looked for again every 15 minutes.
        Any failure means no picks: Midas then trades on its rules alone."""
        if not C.AI_PICKS:
            return {}
        a = self.ai
        if a["for"] == today and (a["picks"] or time.time() - a["at"] < C.AI_REFRESH_SECONDS):
            return a["picks"]
        try:
            picks, day = parse_ai_picks(fetch_ai_picks(), today)
        except Exception as err:
            picks, day = {}, None
            if a["for"] != today:
                log(f"Dionysus's picks unavailable ({err}); trading on the rules alone")
        if picks and picks != a["picks"]:
            log(f"Dionysus's picks from {day}, tried first if the rules agree: " + ", ".join(
                f"{s} {k} ({c}/5)" for (s, k), c in sorted(picks.items(), key=lambda x: -x[1])))
        elif day is not None and a["for"] != today:
            log(f"no usable picks from Dionysus for today (latest from {day or 'never'}); trading on the rules alone")
        self.ai = {"for": today, "at": time.time(), "picks": picks, "day": day}
        return picks

    def free_up_list(self, today):
        """The open bets Dionysus said may be sold to fund his picks today."""
        f = self.fu
        if f["for"] == today and (f["list"] or time.time() - f["at"] < C.AI_REFRESH_SECONDS):
            return f["list"]
        try:
            names = parse_free_up(fetch_free_up(), today)
        except Exception:
            names = []
        if names and names != f["list"]:
            log("Dionysus says these may be sold to fund his picks: " + ", ".join(f"{s} {k}" for s, k in names))
        self.fu = {"for": today, "at": time.time(), "list": names}
        return names

    def ai_note(self, today, und, kind, why):
        """Log, once a day, why one of Dionysus's picks was not bought."""
        if (today, und, kind, why) not in self.ai_said:
            self.ai_said.add((today, und, kind, why))
            log(f"Dionysus's pick {und} {kind} not bought: {why}")

    def fu_note(self, today, und, kind, why):
        """Log, once a day, why a bet Dionysus named was not sold to fund his pick."""
        if (today, und, kind, why) not in self.fu_said:
            self.fu_said.add((today, und, kind, why))
            log(f"{und} {kind} not sold to fund Dionysus's pick: {why}")

    def free_up(self, today, led, und, kind, conv, short):
        """Sell part of a winning bet Dionysus named, just enough to cover `short`
        dollars so his pick can be bought. Returns True once something sold."""
        if not (C.AI_FREE_UP and conv >= C.AI_FREE_UP_MIN_CONVICTION):
            return False
        if len(self.freed.get(today, [])) >= C.AI_FREE_UP_MAX_PER_DAY:
            return False
        named = self.free_up_list(today.isoformat())
        if not named:
            return False
        quotes = self.api.option_snapshots(list(led.pos))
        for s, k in named:
            p = next((p for p in led.pos.values() if p.tag == "core" and (p.und, p.kind) == (s, k)), None)
            if p is None or p.und == und:
                continue
            q = read_quote(quotes.get(p.symbol), self.qnow)
            if not quote_ok(q):
                self.fu_note(today, s, k, "no believable quote")
                continue
            bid, _, mid = q
            gain = mid / p.avg - 1
            if gain < C.AI_FREE_UP_MIN_GAIN:
                self.fu_note(today, s, k, f"up only {gain:+.0%}, under {C.AI_FREE_UP_MIN_GAIN:+.0%}")
                continue
            n = min(p.qty, math.ceil(short / (bid * 100)) + 1)   # one extra for slippage
            if n * bid * 100 < short:
                self.fu_note(today, s, k, "even all of it would not fund the pick")
                continue
            log(f"FREE UP for Dionysus's {und} {kind} ({conv}/5): selling {n} of {p.qty} {p.label()} "
                f"({gain:+.0%}), a winner he named, to free about ${n * bid * 100:,.0f}")
            self.freed.setdefault(today, []).append((und, kind, f"{n} of {p.label()}"))
            return self.sell(p, n, "freed cash for Dionysus's pick", mid) > 0
        return False

    def money_gap(self, need, equity, cash):
        """Dollars a sale must raise so a bet of `need` fits. Every limit a sale
        raises counts (sleeve cash after the same-day reserve, the account's real
        cash, buying power, lead-lock room), unclipped, with 5% to spare. None if
        a sale cannot help (the bet is bigger than one slot allows)."""
        if C.CORE_SLOT_PCT * equity < need:
            return None
        acct = self.api.account()
        limits = [cash * 0.98, float(acct.get("options_buying_power") or 0),
                  float(acct.get("cash") or 0) * 0.98, self.room]
        if C.ODTE_ENABLED:
            limits.append(cash - C.ODTE_RISK_PCT * equity)
        return max(0.0, need - min(limits)) * 1.05

    def core_money(self, equity, cash):
        money = self.budget(C.CORE_SLOT_PCT, equity, cash)
        if C.ODTE_ENABLED:  # always keep enough back for one same-day bet
            money = min(money, max(0.0, cash - C.ODTE_RISK_PCT * equity))
        return money

    def short_of(self, equity):
        """Why there is no money for a proper-size bet. The lead lock is named when
        it is what binds, so the AI trader learns the real limit, not 'cash'."""
        if self.room < C.CORE_MIN_BET_SHARE * C.CORE_SLOT_PCT * equity:
            return "the lead lock leaves no room for new bets (the lead over SPY is being protected)"
        return "not enough cash for a proper-size bet"

    def ai_rejection(self, und, kind, view, regime):
        """Why the rules do not approve an AI pick right now, in plain words."""
        v = view.get(und)
        if und not in C.UNIVERSE or not v:
            return "not in the bot's list of stocks"
        if regime == "unknown":
            return "the market's mood is unknown"
        if (regime, kind) in (("bull", "put"), ("bear", "call")):
            return f"{kind}s are off in a {regime} market"
        up = v["px"] > v["ema10"] and v["r5"] > 0 and v["score"] > 0
        down = v["px"] < v["ema10"] and v["r5"] < 0 and v["score"] < 0
        if not (up if kind == "call" else down):
            return "the trend no longer confirms it"
        return "momentum is below the minimum"

    def core_entries(self, now, led, view, regime, equity, cash):
        hhmm, today = now.strftime("%H:%M"), now.date()
        if not (C.CORE_ENTRY_FROM <= hhmm < C.CORE_ENTRY_TO) or self.to_close <= C.CORE_ENTRY_MIN_TO_CLOSE:
            return led, equity, cash
        # Scan for entries at most once a minute, even when the loop runs fast
        # for an open 0DTE position; a scan can cost many API calls.
        if time.time() - self.last_core_scan < C.LOOP_SECONDS - 1:
            return led, equity, cash
        self.last_core_scan = time.time()
        core =[p for p in led.pos.values() if p.tag == "core"]
        free = C.CORE_SLOTS - len(core)
        held = {p.und for p in core}
        count = {"call": sum(p.kind == "call" for p in core), "put": sum(p.kind == "put" for p in core)}
        # The AI trader's picks go first, highest conviction first; the rest
        # keep the rules' momentum order. Only rule-approved candidates are in
        # this list, so an AI pick can change the order but never add a trade.
        ai = self.ai_picks(today.isoformat())
        ranked = self.candidates(view, regime)
        approved = {(und, kind) for _, und, kind in ranked}
        for und, kind in ai:
            if (und, kind) not in approved:
                self.ai_note(today, und, kind, self.ai_rejection(und, kind, view, regime))
        ranked = sorted(ranked, key=lambda c: -ai.get((c[1], c[2]), 0))
        for strength, und, kind in ranked:
            conv = ai.get((und, kind), 0)
            if free <= 0:
                if conv:
                    self.ai_note(today, und, kind, "every slot is full")
                break
            key = (today, "core", und)
            if und in held or ("core", und) in led.today or self.attempts[key] >= C.MAX_ENTRY_ATTEMPTS:
                if conv:
                    self.ai_note(today, und, kind, "already held or tried today")
                continue
            if regime == "mixed" and count[kind] >= max(2, C.CORE_SLOTS * 2 // 3):
                continue
            if earnings_days(und, today) is not None:  # too close to an earnings report
                if conv:
                    self.ai_note(today, und, kind, "too close to its earnings report")
                continue
            pick = self.pick_core(und, kind, view[und], today)
            if not pick:
                if conv:
                    self.ai_note(today, und, kind, "no option contract passed the spread and delta checks")
                continue
            money = self.core_money(equity, cash)
            need = C.CORE_MIN_BET_SHARE * C.CORE_SLOT_PCT * equity
            gap = self.money_gap(need, equity, cash) if money < need and conv else None
            if gap and self.free_up(today, led, und, kind, conv, gap) and not self.dry:
                # Part of a winner Dionysus named was sold for this pick: look again.
                led = self.build_ledger(now)
                equity, cash = self.sleeve(led, self.api.option_snapshots(led.pos))
                self.lead_lock(view, equity, cash)
                money, need = self.core_money(equity, cash), C.CORE_MIN_BET_SHARE * C.CORE_SLOT_PCT * equity
            if money < need:
                if conv:
                    self.ai_note(today, und, kind, self.short_of(equity))
                break  # not enough cash (or lead-lock room) left for a proper-size bet
            qty = int(money // (pick["ask"] * 100))
            if qty < 1:
                continue
            self.attempts[key] += 1
            note = (
                f"{kind} on {und}, momentum {strength:+.1%}, delta {pick['delta']:+.2f}, "
                f"{pick['dte']} DTE, ask ${pick['ask']:.2f}, about ${qty * pick['ask'] * 100:,.0f}"
                + (f", Dionysus's pick {conv}/5" if conv else "")
            )
            meta = f"e_{regime}_{int(round(strength * 10000))}" + (f"_ai{conv}" if conv else "")
            if self.buy(und, pick["symbol"], qty, "core", note, meta):
                free -= 1
                held.add(und)
                count[kind] += 1
                if not self.dry:
                    led = self.build_ledger(now)
                    equity, cash = self.sleeve(led, self.api.option_snapshots(led.pos))
        return led, equity, cash

    def odte_entries(self, now, led, view, regime, equity, cash):
        hhmm, today = now.strftime("%H:%M"), now.date()
        if not C.ODTE_ENABLED or not (C.ODTE_ENTRY_FROM <= hhmm < C.ODTE_ENTRY_TO):
            return led
        if self.to_close <= C.ODTE_ENTRY_MIN_TO_CLOSE:  # early-close days
            return led
        if regime == "unknown":
            return led
        taken = sum(1 for tag, _ in led.today if tag == "odte")
        ranges = self.opening_range(now)
        for und in C.ODTE_SYMBOLS:
            if taken >= C.ODTE_MAX_PER_DAY:  # SPY and QQQ move together: one bet a day
                break
            key = (today, "odte", und)
            if ("odte", und) in led.today or self.attempts[key] >= C.MAX_ENTRY_ATTEMPTS:
                continue
            if und not in ranges or und not in view:
                continue
            high, low = ranges[und]
            px = view[und]["px"]
            if px > high * (1 + C.ODTE_BREAK_BUFFER):
                kind = "call"
            elif px < low * (1 - C.ODTE_BREAK_BUFFER):
                kind = "put"
            else:
                continue
            # Trade only with the market's trend, never against the core book:
            # no calls in a bear market, no puts in a bull market.
            against = (regime == "bear" and kind == "call") or (regime == "bull" and kind == "put")
            if C.ODTE_WITH_REGIME and against:
                continue
            pick = self.pick_odte(und, kind, px, today)
            if not pick:
                continue
            qty = int(self.budget(C.ODTE_RISK_PCT, equity, cash) // (pick["ask"] * 100))
            if qty < 1:
                continue
            self.attempts[key] += 1
            note = (
                f"0DTE {kind} on {und}: ${px:.2f} broke the opening range "
                f"${low:.2f}-${high:.2f}, strike {pick['strike']:g}, ask ${pick['ask']:.2f}"
            )
            edge = px / high - 1 if kind == "call" else 1 - px / low  # how far past the range
            meta = f"e_{regime}_{int(round(edge * 10000))}"
            if self.buy(und, pick["symbol"], qty, "odte", note, meta):
                taken += 1
                if not self.dry:
                    led = self.build_ledger(now)
                    equity, cash = self.sleeve(led, self.api.option_snapshots(led.pos))
        return led

    # ---- main loop -----------------------------------------------------------
    def tick(self, now, market_open, to_close=None):
        """One pass. Returns True while a 0DTE position is open, so the caller
        can loop faster: same-day options can move through a stop in seconds.
        `to_close` is minutes until today's close (matters on half days)."""
        self.qnow = now if market_open else None
        self.to_close = 24 * 60.0 if to_close is None else to_close
        today, hhmm = now.date().isoformat(), now.strftime("%H:%M")
        if not self.dry:
            self.cancel_stale()
        led = self.build_ledger(now)
        view, regime = self.market_view(now)
        quotes = self.api.option_snapshots(led.pos) if led.pos else {}
        equity, cash = self.sleeve(led, quotes)
        lock_note, lock_breach = self.lead_lock(view, equity, cash)

        if time.time() - self.last_beat >= C.HEARTBEAT_SECONDS:
            self.last_beat = time.time()
            book = ", ".join(
                f"{p.qty} {p.label()}"
                + (f" {read_quote(quotes.get(s))[2] / p.avg - 1:+.0%}" if read_quote(quotes.get(s)) else "")
                for s, p in led.pos.items()
            )
            top = ", ".join(f"{s} {k} {x:+.1%}" for x, s, k in self.candidates(view, regime)[:5])
            log(
                f"sleeve ${equity:,.0f} ({equity / C.SLEEVE_START - 1:+.1%} on ${C.SLEEVE_START:,.0f}) cash ${cash:,.0f} | "
                f"regime {regime} | holding: {book or 'nothing'} | signals: {top or 'none'}{lock_note}"
            )

        # The kill switch needs the breach on consecutive passes before it
        # sells, but new entries stop on the first sign of it.
        breach = equity <= C.KILL_FLOOR_PCT * C.SLEEVE_START or lock_breach
        self.halt_hits = self.halt_hits + 1 if breach else 0
        halted = self.halt_hits >= C.KILL_CONFIRMATIONS
        last_day = bool(C.END_DATE) and today >= C.END_DATE
        end_flat = bool(C.END_DATE) and (
            today > C.END_DATE
            or (today == C.END_DATE and (hhmm >= "15:00" or self.to_close <= C.ODTE_EXIT_MIN_TO_CLOSE))
        )
        flatten = halted or end_flat
        if halted and led.pos:
            why = "the lead over SPY is nearly gone" if lock_breach else f"sleeve at ${equity:,.0f}"
            log(f"KILL SWITCH: {why}, closing everything and standing down")
        if self.manage(now, led, quotes, view, flatten) and not self.dry:
            led = self.build_ledger(now)
            equity, cash = self.sleeve(led, self.api.option_snapshots(led.pos) if led.pos else {})
        if not (breach or last_day):
            led, equity, cash = self.core_entries(now, led, view, regime, equity, cash)
            led = self.odte_entries(now, led, view, regime, equity, cash)
        live.publish(self, now, market_open, led, view, regime)
        return any(p.tag == "odte" for p in led.pos.values())

    def run(self, once):
        log(
            f"optbot starting ({'DRY RUN' if self.dry else 'PAPER TRADING'}), "
            f"sleeve ${C.SLEEVE_START:,.0f}, 0DTE {'on' if C.ODTE_ENABLED else 'off'}, "
            f"end date {C.END_DATE or 'not set'}"
        )
        if not once and live.start_server():
            log(f"live dashboard serving on port {os.environ.get('PORT', '8080')}")
        told_closed = False
        while True:
            fast = False
            try:
                clock = self.api.clock()
                now = parse_ts(clock["timestamp"])
                if clock["is_open"]:
                    told_closed = False
                    to_close = (parse_ts(clock["next_close"]) - now).total_seconds() / 60
                    fast = self.tick(now, True, to_close)
                elif once:
                    log("market is closed: evaluating on last prices, nothing will be sent")
                    self.dry = True
                    self.tick(now, False)
                else:
                    if not told_closed:
                        log(f"market closed, next open {clock['next_open']}")
                        told_closed = True
                    try:  # keep the dashboard current overnight and at weekends
                        led = self.build_ledger(now)
                        view, regime = self.market_view(now)
                        live.publish(self, now, False, led, view, regime, min_gap=240)
                    except Exception as err:
                        log(f"(dashboard) could not refresh while closed: {err}")
                    wait = (parse_ts(clock["next_open"]) - now).total_seconds()
                    time.sleep(max(5, min(300, wait)))
                    continue
            except ApiError as err:
                log(f"API error: {err}")
            except Exception:  # keep the loop alive; the next pass rebuilds from Alpaca
                log("unexpected error:\n" + traceback.format_exc())
            if once:
                return
            time.sleep(C.ODTE_LOOP_SECONDS if fast else C.LOOP_SECONDS)

    def status(self):
        now = parse_ts(self.api.clock()["timestamp"])
        led = self.build_ledger(now)
        quotes = self.api.option_snapshots(led.pos) if led.pos else {}
        equity, cash = self.sleeve(led, quotes)
        print(f"Sleeve equity   ${equity:,.2f}  (profit ${equity - C.SLEEVE_START:+,.2f} on ${C.SLEEVE_START:,.0f} of capital)")
        print(f"Sleeve cash     ${cash:,.2f}")
        print(f"Realized P&L    ${led.realized:+,.2f} over {len(led.closed)} closing trades")
        start = dt.date.fromisoformat(C.START_DATE)
        bars = self.api.daily_bars(["SPY"], (start - dt.timedelta(days=10)).isoformat()).get("SPY", [])
        base = [b["c"] for b in bars if b["t"][:10] < C.START_DATE]
        spy = (self.api.stock_snapshots(["SPY"]).get("SPY") or {}).get("latestTrade", {}).get("p")
        if base and spy:
            print(f"SPY since {C.START_DATE}  {spy / base[-1] - 1:+.2%}")
        print("\nOpen positions")
        for symbol, p in led.pos.items():
            q = read_quote(quotes.get(symbol))
            mark = f"${q[2]:.2f} ({q[2] / p.avg - 1:+.0%})" if q else "no quote"
            print(f"  [{p.tag}] {p.qty} x {p.label():<22} paid ${p.avg:.2f}  now {mark}")
        if not led.pos:
            print("  none")
        print("\nLast closing trades")
        for when, symbol, qty, px, pnl in led.closed[-15:]:
            print(f"  {when.astimezone(now.tzinfo):%m/%d %H:%M}  {qty} x {symbol} @ ${px:.2f}  {pnl:+,.0f}")
        if not led.closed:
            print("  none")


def capital_on(day):
    """How much money the sleeve had been given as of a date (YYYY-MM-DD)."""
    amount = C.SLEEVE_STEPS[0][1]
    for start, value in C.SLEEVE_STEPS:
        if start <= day:
            amount = value
    return amount


def journal(bot, day=None):
    """Add or refresh a trading day's row in STRATEGY_LOG.md.

    Right after the close Alpaca's option prices are stale, so a row written
    then is marked "preliminary". Once Alpaca has published its official
    end-of-day account value, any later run replaces the row with the official
    figures, which are the ones the class is graded on. It does not matter when
    that later run happens: every earlier row still marked preliminary is
    finalised first. `day` rewrites one past day's row from official figures.
    Safe to run any number of times: a day's row is replaced, never duplicated."""
    api = bot.api
    if not LOG_PATH.exists():
        raise SystemExit(f"{LOG_PATH.name} not found next to bot.py")
    clock = api.clock()
    now = parse_ts(clock["timestamp"])
    start = dt.date.fromisoformat(C.START_DATE)
    bars = api.daily_bars(["SPY"], (start - dt.timedelta(days=10)).isoformat()).get("SPY", [])
    closes = {b["t"][:10]: b["c"] for b in bars}
    sessions = sorted(closes)
    latest = sessions[-1]
    past = day is not None and day != latest
    day = day or latest
    if day not in closes or sessions.index(day) == 0:
        raise SystemExit(f"{day} is not a trading day on record")
    before = sessions[sessions.index(day) - 1]
    official = api.official_closes()
    final = day in official
    if past and not final:
        raise SystemExit(f"Alpaca has no official close for {day} yet")

    if not past:  # first bring every earlier unfinished row up to official figures
        text = LOG_PATH.read_text().splitlines()
        unfinished = sorted({
            line[2:12] for line in text
            if re.match(r"^\| \d{4}-\d{2}-\d{2} \(", line) and line[2:12] < day and line[2:12] in official
        })
        for earlier_day in unfinished:
            journal(bot, earlier_day)

    spy_day = closes[day] / closes[before] - 1
    base = [closes[d] for d in sessions if d < C.START_DATE]
    spy_total = f"{closes[day] / base[-1] - 1:+.2%}" if base else "n/a"

    # An official row describes the book as it stood at that day's close.
    led = bot.build_ledger(now, until=day if final else None)
    held = {x["symbol"]: x for x in api.positions()}
    quotes = api.option_snapshots(led.pos) if led.pos and not final else {}
    if final:
        equity = official[day]
        account_day = f"{equity / official[before] - 1:+.2%}" if before in official else "n/a"
    else:
        acct = api.account()
        equity = float(acct["equity"])
        account_day = f"{equity / float(acct['last_equity']) - 1:+.2%}"

    def mark(symbol, p):
        if final:
            # Alpaca values an option at its last traded price of the day,
            # which is the close of the option's own daily bar.
            daily = [b for b in api.option_bars(symbol, f"{C.START_DATE}T00:00:00Z", "1Day") if b["t"][:10] <= day]
            if daily:
                return float(daily[-1]["c"])
            print(f"note: no closing price for {symbol} on {day}; valued at cost")
            return p.avg
        px = float((held.get(symbol) or {}).get("current_price") or 0)
        if not px:
            q = read_quote(quotes.get(symbol))
            px = q[2] if q else p.avg
        return px

    value, book = 0.0, []
    for symbol, p in led.pos.items():
        px = mark(symbol, p)
        value += p.qty * px * 100
        book.append(f"{p.qty} {p.label()} ({px / p.avg - 1:+.0%})")
    profit = led.realized - sum(p.cost for p in led.pos.values()) + value
    capital = capital_on(day)        # the sleeve's size has changed over time
    sleeve = capital + profit

    def on_day(when):
        return when.astimezone(now.tzinfo).date().isoformat() == day

    events = [(w, f"Bought {q} {Pos(s, '').label()} at ${px:.2f}") for w, s, q, px in led.opened if on_day(w)]
    events += [
        (w, f"Sold {q} {Pos(s, '').label()} at ${px:.2f} ({'+' if pnl >= 0 else '-'}${abs(pnl):,.0f})")
        for w, s, q, px, pnl in led.closed
        if on_day(w)
    ]
    trades = "; ".join(text for _, text in sorted(events, key=lambda e: e[0])) or "No trades"

    lines = LOG_PATH.read_text().splitlines()
    rows = [i for i, line in enumerate(lines) if re.match(r"^\| \d{4}-\d{2}-\d{2}", line)]
    earlier = [lines[i] for i in rows if lines[i][2:12] < day]
    sleeve_day = "n/a"
    if earlier:
        m = re.search(r"\$([\d,]+)", earlier[-1].split("|")[4])
        if m:
            # Money added to the sleeve is not a gain: measure the day's
            # profit against what the sleeve had to work with that morning.
            opening = float(m.group(1).replace(",", "")) + capital - capital_on(earlier[-1][2:12])
            sleeve_day = f"{sleeve / opening - 1:+.2%}"
    if final:
        label = day
    else:
        label = day + (f" (as of {now:%H:%M} ET)" if clock["is_open"] else " (preliminary)")
    row = (
        f"| {label} | ${equity:,.0f} | {account_day} | ${sleeve:,.0f} | {sleeve_day} | "
        f"{'+' if profit >= 0 else '-'}${abs(profit):,.0f} | {spy_day:+.2%} | {spy_total} | "
        f"{', '.join(book) or 'Nothing'} | {trades} |"
    )
    same = [i for i in rows if lines[i][2:12] == day]
    if same:
        lines[same[0]] = row
    else:
        later = [i for i in rows if lines[i][2:12] > day]
        lines.insert(later[0], row) if later else lines.append(row)
    LOG_PATH.write_text("\n".join(lines) + "\n")
    print(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run the trading loop")
    run.add_argument("--dry-run", action="store_true", help="log decisions, send no orders")
    run.add_argument("--once", action="store_true", help="one pass, then exit")
    sub.add_parser("status", help="print the sleeve's P&L and positions")
    jr = sub.add_parser("journal", help="record the day's results in STRATEGY_LOG.md")
    jr.add_argument("--date", help="rewrite one past day's row from official figures (YYYY-MM-DD)")
    sub.add_parser("memory", help="refresh memory/: the trade table, market snapshot and review")
    args = parser.parse_args()
    if args.cmd == "status":
        Bot(dry=True).status()
    elif args.cmd == "journal":
        journal(Bot(dry=True), args.date)
    elif args.cmd == "memory":
        import memory

        memory.update(Bot(dry=True))
    else:
        dry = args.dry_run or C._env("DRY_RUN", False, bool)
        Bot(dry=dry).run(args.once)


if __name__ == "__main__":
    main()
