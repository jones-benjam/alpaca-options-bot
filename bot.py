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
"""
import argparse
import datetime as dt
import json
import math
import re
import time
import traceback
import uuid
from collections import defaultdict
from pathlib import Path

import config as C
from alpaca import Alpaca, ApiError

OCC = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")
STATE_PATH = Path(C.STATE_FILE) if C.STATE_FILE else Path(__file__).with_name("state.json")
LOG_PATH = Path(__file__).with_name("STRATEGY_LOG.md")
TERMINAL = {"filled", "canceled", "expired", "rejected", "done_for_day", "replaced"}


try:  # log in market time when the host has timezone data
    from zoneinfo import ZoneInfo

    ET = ZoneInfo("America/New_York")
except Exception:
    ET = None


def log(msg):
    now = dt.datetime.now(ET) if ET else dt.datetime.now()
    print(f"{now:%Y-%m-%d %H:%M:%S}{' ET' if ET else ''}  {msg}", flush=True)


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
        self.qnow = None      # set while the market is open, to age-check quotes
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

    def cid(self, tag):
        return f"{C.BOT_TAG}-{tag}-{uuid.uuid4().hex[:16]}"

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

    def build_ledger(self, now):
        """Rebuild the bot's positions and realized P&L from its own fills."""
        fills = []
        for o in self.bot_orders():
            qty = int(float(o.get("filled_qty") or 0))
            if qty > 0 and o.get("filled_avg_price") and parse_occ(o["symbol"]):
                when = parse_ts(o.get("filled_at") or o.get("updated_at") or o["submitted_at"])
                tag = o["client_order_id"].split("-")[1]
                fills.append((when, o["symbol"], o["side"], qty, float(o["filled_avg_price"]), tag))
        for s in self.state["synthetic"]:
            fills.append((parse_ts(s["at"]), s["symbol"], "sell", s["qty"], s["px"], "writeoff"))
        fills.sort(key=lambda f: f[0])

        led, today = Ledger(), now.date()
        for when, symbol, side, qty, px, tag in fills:
            if side == "buy":
                p = led.pos.setdefault(symbol, Pos(symbol, tag))
                p.qty += qty
                p.cost += qty * px * 100
                p.last_buy = when
                led.opened.append((when, symbol, qty, px))
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

    def buy(self, und, symbol, qty, tag, note):
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
                order = self.api.submit(symbol, left, "buy", self.cid(tag), limit_price=price)
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
        done, left = 0, qty
        for attempt in range(3):  # at the bid, one tick lower, then market
            q = read_quote(self.api.option_snapshots([p.symbol]).get(p.symbol))
            bid = q[0] if q else 0
            tick = tick_for(p.und, bid or 1)
            try:
                if attempt < 2 and bid > 0:
                    price = round_to(bid - attempt * tick, tick, up=False)
                    order = self.api.submit(p.symbol, left, "sell", self.cid(p.tag), limit_price=price)
                else:
                    order = self.api.submit(p.symbol, left, "sell", self.cid(p.tag))
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
    def manage(self, now, led, quotes, view, flatten):
        """Apply exit rules to every position the bot holds. True if it traded."""
        if not led.pos:
            if self.state["peaks"]:
                self.state["peaks"] = {}
                self.save_state()
            return False
        today, hhmm = now.date(), now.strftime("%H:%M")
        held = {x["symbol"]: int(float(x["qty"])) for x in self.api.positions()}
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
            elif sane:
                peak = max(peaks.get(symbol, p.avg), mid)
                peaks[symbol] = peak
                pnl = mid / p.avg - 1
                v = view.get(p.und)
                price_exit = None
                if pnl <= stop:
                    price_exit = "stop loss"
                elif peak >= p.avg * (1 + tp1) and mid <= peak * (1 - trail):
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
    def budget(self, pct, equity, cash):
        power = float(self.api.account().get("options_buying_power") or 0)
        return max(0.0, min(pct * equity, cash * 0.98, power))

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
        for strength, und, kind in self.candidates(view, regime):
            if free <= 0:
                break
            key = (today, "core", und)
            if und in held or ("core", und) in led.today or self.attempts[key] >= C.MAX_ENTRY_ATTEMPTS:
                continue
            if regime == "mixed" and count[kind] >= 2:
                continue
            pick = self.pick_core(und, kind, view[und], today)
            if not pick:
                continue
            qty = int(self.budget(C.CORE_SLOT_PCT, equity, cash) // (pick["ask"] * 100))
            if qty < 1:
                continue
            self.attempts[key] += 1
            note = (
                f"{kind} on {und}, momentum {strength:+.1%}, delta {pick['delta']:+.2f}, "
                f"{pick['dte']} DTE, ask ${pick['ask']:.2f}, about ${qty * pick['ask'] * 100:,.0f}"
            )
            if self.buy(und, pick["symbol"], qty, "core", note):
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
            if self.buy(und, pick["symbol"], qty, "odte", note):
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

        if time.time() - self.last_beat >= C.HEARTBEAT_SECONDS:
            self.last_beat = time.time()
            book = ", ".join(
                f"{p.qty} {p.label()}"
                + (f" {read_quote(quotes.get(s))[2] / p.avg - 1:+.0%}" if read_quote(quotes.get(s)) else "")
                for s, p in led.pos.items()
            )
            top = ", ".join(f"{s} {k} {x:+.1%}" for x, s, k in self.candidates(view, regime)[:5])
            log(
                f"sleeve ${equity:,.0f} ({equity / C.SLEEVE_START - 1:+.1%}) cash ${cash:,.0f} | "
                f"regime {regime} | holding: {book or 'nothing'} | signals: {top or 'none'}"
            )

        # The kill switch needs the breach on consecutive passes before it
        # sells, but new entries stop on the first sign of it.
        breach = equity <= C.KILL_FLOOR_PCT * C.SLEEVE_START
        self.halt_hits = self.halt_hits + 1 if breach else 0
        halted = self.halt_hits >= C.KILL_CONFIRMATIONS
        last_day = bool(C.END_DATE) and today >= C.END_DATE
        end_flat = bool(C.END_DATE) and (
            today > C.END_DATE
            or (today == C.END_DATE and (hhmm >= "15:00" or self.to_close <= C.ODTE_EXIT_MIN_TO_CLOSE))
        )
        flatten = halted or end_flat
        if halted and led.pos:
            log(f"KILL SWITCH: sleeve at ${equity:,.0f}, closing everything and standing down")
        if self.manage(now, led, quotes, view, flatten) and not self.dry:
            led = self.build_ledger(now)
            equity, cash = self.sleeve(led, self.api.option_snapshots(led.pos) if led.pos else {})
        if not (breach or last_day):
            led, equity, cash = self.core_entries(now, led, view, regime, equity, cash)
            led = self.odte_entries(now, led, view, regime, equity, cash)
        return any(p.tag == "odte" for p in led.pos.values())

    def run(self, once):
        log(
            f"optbot starting ({'DRY RUN' if self.dry else 'PAPER TRADING'}), "
            f"sleeve ${C.SLEEVE_START:,.0f}, 0DTE {'on' if C.ODTE_ENABLED else 'off'}, "
            f"end date {C.END_DATE or 'not set'}"
        )
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
        print(f"Sleeve equity   ${equity:,.2f}  ({equity / C.SLEEVE_START - 1:+.2%} on ${C.SLEEVE_START:,.0f})")
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


def journal(bot):
    """Add or refresh the latest trading day's row in STRATEGY_LOG.md.

    Values come from Alpaca's own prices so the sleeve adds up with the account
    balance the class is graded on. Safe to run more than once a day: the row
    for that date is replaced, not duplicated."""
    api = bot.api
    if not LOG_PATH.exists():
        raise SystemExit(f"{LOG_PATH.name} not found next to bot.py")
    clock = api.clock()
    now = parse_ts(clock["timestamp"])
    led = bot.build_ledger(now)
    acct = api.account()
    equity, last = float(acct["equity"]), float(acct["last_equity"])
    prices = {x["symbol"]: float(x.get("current_price") or 0) for x in api.positions()}
    quotes = api.option_snapshots(led.pos) if led.pos else {}

    value, book = 0.0, []
    for symbol, p in led.pos.items():
        px = prices.get(symbol)
        if not px:
            q = read_quote(quotes.get(symbol))
            px = q[2] if q else p.avg
        value += p.qty * px * 100
        book.append(f"{p.qty} {p.label()} ({px / p.avg - 1:+.0%})")
    sleeve = C.SLEEVE_START + led.realized - sum(p.cost for p in led.pos.values()) + value

    spy = api.stock_snapshots(["SPY"])["SPY"]
    day = spy["dailyBar"]["t"][:10]  # the latest trading session
    spy_day = spy["dailyBar"]["c"] / spy["prevDailyBar"]["c"] - 1
    start = dt.date.fromisoformat(C.START_DATE)
    bars = api.daily_bars(["SPY"], (start - dt.timedelta(days=10)).isoformat()).get("SPY", [])
    base = [b["c"] for b in bars if b["t"][:10] < C.START_DATE]
    spy_total = f"{spy['dailyBar']['c'] / base[-1] - 1:+.2%}" if base else "n/a"

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
            sleeve_day = f"{sleeve / float(m.group(1).replace(',', '')) - 1:+.2%}"
    label = day + (f" (as of {now:%H:%M} ET)" if clock["is_open"] else "")
    row = (
        f"| {label} | ${equity:,.0f} | {equity / last - 1:+.2%} | ${sleeve:,.0f} | {sleeve_day} | "
        f"{sleeve / C.SLEEVE_START - 1:+.1%} | {spy_day:+.2%} | {spy_total} | "
        f"{', '.join(book) or 'Nothing'} | {trades} |"
    )
    same = [i for i in rows if lines[i][2:12] == day]
    if same:
        lines[same[0]] = row
    else:
        lines.append(row)
    LOG_PATH.write_text("\n".join(lines) + "\n")
    print(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run the trading loop")
    run.add_argument("--dry-run", action="store_true", help="log decisions, send no orders")
    run.add_argument("--once", action="store_true", help="one pass, then exit")
    sub.add_parser("status", help="print the sleeve's P&L and positions")
    sub.add_parser("journal", help="record the day's results in STRATEGY_LOG.md")
    args = parser.parse_args()
    if args.cmd == "status":
        Bot(dry=True).status()
    elif args.cmd == "journal":
        journal(Bot(dry=True))
    else:
        dry = args.dry_run or C._env("DRY_RUN", False, bool)
        Bot(dry=dry).run(args.once)


if __name__ == "__main__":
    main()
