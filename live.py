"""Live dashboard served by the bot itself.

The trading loop calls `publish(...)` after each pass; a small web server in a
background thread serves the latest snapshot. Pages and data are read-only,
nothing here can place an order, and a request never calls the broker: it only
reads the snapshot the bot already made. If the server fails to start, the bot
keeps trading and logs the reason.

    /             the dashboard page (refreshes itself every 15 seconds)
    /api/state    the snapshot as JSON
    /healthz      "ok"
"""
import datetime as dt
import json
import os
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config as C

LOG_LINES = deque(maxlen=60)        # the bot's recent log lines, newest last
_state = {"snapshot": None}          # replaced whole on each publish, so reads never see a half-built one
_intraday = {"date": None, "points": []}
_daily = {"date": None, "rows": []}
_last_publish = {"at": 0.0}


def remember(line):
    LOG_LINES.append(line)


def _daily_history(bot, today):
    """Official end-of-day account values with SPY's return since the start, fetched once a day."""
    if _daily["date"] == today:
        return _daily["rows"]
    try:
        official = bot.api.official_closes()
        start = dt.date.fromisoformat(C.START_DATE)
        bars = bot.api.daily_bars(["SPY"], (start - dt.timedelta(days=10)).isoformat()).get("SPY", [])
        spy = {b["t"][:10]: b["c"] for b in bars}
        base = [spy[d] for d in sorted(spy) if d < C.START_DATE]
        rows = []
        if base:
            rows.append({"date": "start", "account": C.LOCK_START_VALUE, "account_pct": 0.0, "spy_pct": 0.0})
            for d in sorted(official):
                if d >= C.START_DATE and d in spy:
                    rows.append({"date": d, "account": round(official[d], 2),
                                 "account_pct": round((official[d] / C.LOCK_START_VALUE - 1) * 100, 2),
                                 "spy_pct": round((spy[d] / base[-1] - 1) * 100, 2)})
        _daily.update(date=today, rows=rows)
    except Exception as err:  # history is a nice-to-have; never let it stop a publish
        LOG_LINES.append(f"(dashboard) daily history unavailable: {err}")
    return _daily["rows"]


MOODS = {"bear": "market falling", "bull": "market rising", "mixed": "market mixed"}
EXIT_TEXT = {
    "stop": "Stop loss", "trail": "Trailing stop", "be": "Breakeven stop",
    "flip": "Trend flipped", "time": "Time stop", "earn": "Earnings exit",
    "half": "Took profit on half", "exp": "Expiry-day exit", "flat": "Closed out",
    "writeoff": "Written off", "expired": "Expired worthless", "other": "Other exit",
}
ENGINES = {"odte": "same-day", "core": "three-week"}


def _reason(ev):
    """Why the bot placed this order, in plain words, from the tag on the order."""
    meta = ev.get("meta") or ""
    if meta.startswith("e_"):
        parts = meta.split("_")
        mood = MOODS.get(parts[1], parts[1]) if len(parts) > 1 else ""
        try:
            sig = int(parts[2]) / 100
        except (IndexError, ValueError):
            sig = None
        if ev.get("tag") == "odte":
            what = f"Broke the opening range by {sig:.2f}%" if sig is not None else "Opening-range breakout"
        else:
            what = f"Momentum signal {sig:.1f}%" if sig is not None else "Momentum signal"
        return f"{what}, {mood}" if mood else what
    if meta.startswith("x_"):
        return EXIT_TEXT.get(meta[2:], meta[2:].replace("_", " ").capitalize())
    return "Entry" if ev["side"] == "buy" else "Exit"


def _held(seconds):
    m = int(seconds // 60)
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h < 24 else f"{h // 24}d {h % 24}h"


def blotter(led, now):
    """Every fill the bot made, newest first, plus the win/loss record of its sales."""
    from bot import Pos  # late import: bot imports this module

    held, opened_at, trades = {}, {}, []
    for ev in led.events:
        sym, when, qty, px = ev["symbol"], ev["when"], ev["qty"], ev["px"]
        p = Pos(sym, ev.get("tag", ""))
        row = {"at": when.isoformat(), "when": when.astimezone(now.tzinfo).strftime("%b %-d %H:%M"),
               "day": when.astimezone(now.tzinfo).date().isoformat(), "side": ev["side"],
               "symbol": sym, "label": p.label(), "und": p.und, "kind": p.kind,
               "engine": ENGINES.get(ev.get("tag"), ev.get("tag") or ""), "qty": qty, "px": round(px, 2),
               "notional": round(qty * px * 100), "reason": _reason(ev)}
        if ev["side"] == "buy":
            if not held.get(sym):
                opened_at[sym] = when
            held[sym] = held.get(sym, 0) + qty
        else:
            pnl = ev.get("pnl", 0.0)
            basis = qty * px * 100 - pnl
            start = opened_at.get(sym)
            row.update(pnl=round(pnl, 2), pnl_pct=round(pnl / basis * 100, 1) if basis > 0 else None,
                       basis=round(basis), held=_held((when - start).total_seconds()) if start else None,
                       result="win" if pnl >= 0.5 else "loss" if pnl <= -0.5 else "even")
            held[sym] = max(0, held.get(sym, 0) - qty)
        trades.append(row)

    sales = [t for t in trades if t["side"] == "sell"]
    wins = [t for t in sales if t["result"] == "win"]
    losses = [t for t in sales if t["result"] == "loss"]
    gross_win, gross_loss = sum(t["pnl"] for t in wins), sum(t["pnl"] for t in losses)
    avg = lambda rows, key: round(sum(t[key] or 0 for t in rows) / len(rows), 1) if rows else None
    streak = {"result": None, "n": 0}
    for t in reversed(sales):
        if t["result"] == "even":
            continue
        if streak["result"] in (None, t["result"]):
            streak.update(result=t["result"], n=streak["n"] + 1)
        else:
            break
    brief = lambda t: t and {"label": t["label"], "pnl": t["pnl"], "pnl_pct": t["pnl_pct"], "when": t["when"]}

    def group(key):
        out = {}
        for t in sales:
            g = out.setdefault(t[key], {"name": t[key], "sales": 0, "wins": 0, "losses": 0, "pnl": 0.0})
            g["sales"] += 1
            g["wins"] += t["result"] == "win"
            g["losses"] += t["result"] == "loss"
            g["pnl"] += t["pnl"]
        for g in out.values():
            g["pnl"] = round(g["pnl"], 2)
        return sorted(out.values(), key=lambda g: -g["pnl"])

    stats = {
        "buys": len(trades) - len(sales), "sales": len(sales), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / (len(wins) + len(losses)) * 100, 1) if wins or losses else None,
        "realized": round(sum(t["pnl"] for t in sales), 2),
        "gross_win": round(gross_win, 2), "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_win / -gross_loss, 2) if gross_loss < 0 else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else None,
        "avg_loss": round(gross_loss / len(losses), 2) if losses else None,
        "avg_win_pct": avg(wins, "pnl_pct"), "avg_loss_pct": avg(losses, "pnl_pct"),
        "best": brief(max(sales, key=lambda t: t["pnl"], default=None)),
        "worst": brief(min(sales, key=lambda t: t["pnl"], default=None)),
        "streak": streak,
        "bought": sum(t["notional"] for t in trades if t["side"] == "buy"),
        "sold": sum(t["notional"] for t in sales),
        "by_ticker": group("und"), "by_engine": group("engine"), "by_reason": group("reason"),
    }
    return trades[::-1], stats


def publish(bot, now, market_open, led, view, regime, quotes=None, min_gap=15):
    """Build and store the snapshot the page shows. Cheap and failure-proof."""
    import time

    if time.time() - _last_publish["at"] < min_gap:
        return
    _last_publish["at"] = time.time()
    try:
        from bot import read_quote  # late import: bot imports this module

        quotes = quotes if quotes is not None else (bot.api.option_snapshots(led.pos) if led.pos else {})
        sleeve_value, sleeve_cash = bot.sleeve(led, quotes)
        acct = bot.api.account()
        account = float(acct.get("equity") or 0)
        last_close = float(acct.get("last_equity") or 0)
        spy_px = (view.get("SPY") or {}).get("px")
        spy_pct = (spy_px / bot.spy_base - 1) * 100 if spy_px and bot.spy_base else None
        account_pct = (account / C.LOCK_START_VALUE - 1) * 100
        floor = C.LOCK_START_VALUE * (1 + (spy_pct or 0) / 100 + C.LOCK_MARGIN_PCT) if spy_pct is not None else None

        trades, stats = blotter(led, now)
        first_buy = {}
        for t in trades:  # newest first, so the last one seen is the oldest buy still in the book
            if t["side"] == "buy" and t["symbol"] in led.pos:
                first_buy[t["symbol"]] = t["when"]
        positions = []
        for symbol, p in sorted(led.pos.items(), key=lambda kv: kv[1].expiry):
            q = read_quote(quotes.get(symbol))
            mark = q[2] if q else None
            value = p.qty * mark * 100 if mark else None
            positions.append({
                "label": p.label(), "symbol": symbol, "und": p.und,
                "engine": "same-day" if p.tag == "odte" else "three-week",
                "kind": p.kind, "qty": p.qty, "paid": round(p.avg, 2), "cost": round(p.cost),
                "now": round(mark, 2) if mark else None,
                "value": round(value) if value is not None else None,
                "upnl": round(value - p.cost) if value is not None else None,
                "pnl_pct": round((mark / p.avg - 1) * 100, 1) if mark else None,
                "expires": p.expiry.isoformat(), "dte": (p.expiry - now.date()).days,
                "opened": first_buy.get(symbol),
            })
        unrealized = sum(p["upnl"] for p in positions if p["upnl"] is not None)
        market = []
        for s in C.UNIVERSE:
            v, hist = view.get(s), bot.closes.get(s) or []
            if v and hist:
                market.append({"symbol": s, "px": round(v["px"], 2), "chg_pct": round((v["px"] / hist[-1] - 1) * 100, 2),
                               "r5_pct": round(v["r5"] * 100, 1), "above_trend": v["px"] > v["ema20"]})
        closed = [{"when": w.astimezone(now.tzinfo).strftime("%b %-d %H:%M"), "symbol": s, "qty": q,
                   "price": round(px, 2), "pnl": round(pnl)} for w, s, q, px, pnl in led.closed[-12:]][::-1]

        today = now.date().isoformat()
        if _intraday["date"] != today:
            _intraday.update(date=today, points=[])
        if market_open and account > 0:
            pts = _intraday["points"]
            stamp = now.strftime("%H:%M")
            if not pts or pts[-1]["t"] != stamp:
                pts.append({"t": stamp, "account": round(account, 2)})

        _state["snapshot"] = {
            "as_of": now.isoformat(), "as_of_text": now.strftime("%a %b %-d, %-I:%M:%S %p ET"),
            "market_open": bool(market_open), "regime": regime,
            "account": {"value": round(account, 2), "start": C.LOCK_START_VALUE,
                        "return_pct": round(account_pct, 2),
                        "today_pct": round((account / last_close - 1) * 100, 2) if last_close else None,
                        "spy_return_pct": round(spy_pct, 2) if spy_pct is not None else None,
                        "lead_pts": round(account_pct - spy_pct, 1) if spy_pct is not None else None},
            "sleeve": {"value": round(sleeve_value, 2), "cash": round(sleeve_cash, 2),
                       "profit": round(sleeve_value - C.SLEEVE_START, 2), "capital": C.SLEEVE_START,
                       "realized": round(led.realized, 2), "unrealized": round(unrealized, 2)},
            "trades": trades, "stats": stats, "market": market,
            "lock": {"enabled": C.LOCK_ENABLED, "floor": round(floor, 2) if floor else None,
                     "room": None if bot.room == float("inf") else round(bot.room, 2),
                     "multiplier": C.LOCK_MULTIPLIER},
            "positions": positions, "closed": closed,
            "signals": [{"symbol": s, "kind": k, "strength_pct": round(x * 100, 1)}
                        for x, s, k in bot.candidates(view, regime)[:6]],
            "daily": _daily_history(bot, today), "intraday": list(_intraday["points"]),
            "log": list(LOG_LINES)[-25:], "end_date": C.END_DATE,
        }
    except Exception as err:
        LOG_LINES.append(f"(dashboard) snapshot failed: {err}")


class _Handler(BaseHTTPRequestHandler):
    server_version = "optbot"

    def log_message(self, *args):  # keep request noise out of the trading log
        pass

    def _send(self, code, body, kind, extra=None):
        raw = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":
            self._send(200, "ok", "text/plain")
        elif path == "/api/state":
            snap = _state["snapshot"]
            # Read-only and public, so any page (the GitHub copy of the dashboard) may read it.
            self._send(200, json.dumps(snap or {"waiting": True}), "application/json",
                       {"Access-Control-Allow-Origin": "*"})
        elif path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")


def start_server(port=None):
    """Serve the dashboard in a background thread. Returns the server, or None."""
    port = int(port or os.environ.get("PORT", "8080"))
    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    except OSError as err:
        LOG_LINES.append(f"(dashboard) could not start on port {port}: {err}")
        return None
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="dashboard", daemon=True).start()
    return server


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Options Bot Live</title>
<style>
/* A trading-terminal layout: black screen, amber labels, monospace figures.
   Green and red are kept for wins and losses only; buys are blue, sells amber.
   Every win or loss also carries a word (WIN / LOSS) and an arrow, so colour is never the only cue. */
:root { color-scheme: dark;
  --bg:#000; --panel:#0a0a0a; --head:#161616; --line:#242424; --rule:#353535;
  --amber:#ffa028; --ink:#ececec; --ink2:#b8b8b8; --muted:#7c7c7c;
  --blue:#58a6ff; --gain:#26d07c; --loss:#ff5c5c; --warn:#ffd23f;
  --gain-bg:rgba(38,208,124,.10); --loss-bg:rgba(255,92,92,.11);
  --acc:#ffa028; --spy:#58a6ff; --wash:rgba(255,160,40,.10); }
* { box-sizing:border-box; }
html, body { background:var(--bg); }
body { margin:0; color:var(--ink); font:13px/1.4 ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
  font-variant-numeric:tabular-nums; -webkit-text-size-adjust:100%; }
a { color:var(--amber); }
button, select { font:inherit; }
.top { position:sticky; top:0; z-index:5; display:flex; flex-wrap:wrap; align-items:center; gap:6px 14px; background:#000;
  border-bottom:1px solid var(--rule); padding:6px max(12px, env(safe-area-inset-right, 0px)) 6px max(12px, env(safe-area-inset-left, 0px)); }
.logo { background:var(--amber); color:#000; font-weight:800; padding:2px 8px; letter-spacing:.08em; }
.cmd { color:var(--amber); white-space:nowrap; } .cmd b { color:var(--ink); font-weight:600; }
.go { color:#000; background:var(--gain); font-weight:800; padding:0 5px; margin-left:4px; font-size:11px; }
.fkeys { display:flex; gap:4px; flex-wrap:wrap; }
.fkeys a { text-decoration:none; color:var(--ink2); border:1px solid var(--rule); padding:1px 7px 1px 0; white-space:nowrap; }
.fkeys a b { background:var(--amber); color:#000; padding:1px 5px; margin-right:6px; }
.fkeys a:hover, .fkeys a:focus-visible { color:var(--ink); border-color:var(--amber); }
.status { margin-left:auto; display:flex; align-items:center; gap:8px; color:var(--ink2); white-space:nowrap; }
.dot { width:8px; height:8px; border-radius:50%; background:var(--muted); display:inline-block; }
.dot.live { background:var(--gain); box-shadow:0 0 6px var(--gain); } .dot.stale { background:var(--warn); }
#clock { color:var(--amber); }
.tape { overflow:hidden; white-space:nowrap; border-bottom:1px solid var(--rule); background:#050505; }
.tape-track { display:inline-flex; padding:5px 0; animation:tape 80s linear infinite; }
.tape:hover .tape-track { animation-play-state:paused; }
.tk { padding-right:26px; color:var(--ink2); } .tk b { color:var(--amber); margin-right:6px; }
@keyframes tape { from { transform:translateX(0); } to { transform:translateX(-50%); } }
@media (prefers-reduced-motion: reduce) { .tape { overflow-x:auto; } .tape-track { animation:none; } }
main { display:grid; gap:8px; padding:8px max(12px, env(safe-area-inset-right, 0px)) 32px max(12px, env(safe-area-inset-left, 0px)); max-width:1600px; margin:0 auto; }
.row { display:grid; gap:8px; grid-template-columns:minmax(0, 1fr); }
@media (min-width: 960px) { .r3 { grid-template-columns:minmax(0, 1.25fr) minmax(0, 1.25fr) minmax(0, 1fr); }
  .r2 { grid-template-columns:minmax(0, 1fr) minmax(0, 1fr); } }
.panel { background:var(--panel); border:1px solid var(--line); min-width:0; scroll-margin-top:84px; }
.ph { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:4px 10px; background:var(--head);
  border-bottom:1px solid var(--line); padding:4px 8px; color:var(--amber); font-weight:700; letter-spacing:.05em; font-size:12px; }
.ph .sub { color:var(--muted); font-weight:400; letter-spacing:0; }
.pb { padding:8px; }
.kpis { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:1px; background:var(--line); border:1px solid var(--line); }
@media (min-width: 1280px) { .kpis { grid-template-columns:repeat(8, minmax(0, 1fr)); } }
@media (max-width: 560px) { .kpis { grid-template-columns:repeat(2, minmax(0, 1fr)); } .kv { font-size:18px; }
  .top { position:static; } .kvlist dd { white-space:normal; } }
.kpi { background:var(--panel); padding:6px 9px; min-width:0; }
.kl { color:var(--amber); font-size:11px; letter-spacing:.05em; }
.kv { font-size:21px; font-weight:700; line-height:1.25; white-space:nowrap; }
.ks { color:var(--ink2); font-size:11.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.up { color:var(--gain); } .dn { color:var(--loss); } .warn { color:var(--warn); } .mut { color:var(--muted); }
.legend { display:flex; gap:14px; flex-wrap:wrap; color:var(--ink2); font-size:12px; margin-bottom:4px; }
.key { display:inline-block; width:14px; border-top:2px solid; vertical-align:middle; margin-right:6px; }
svg { width:100%; height:auto; display:block; overflow:visible; }
.gridline { stroke:#1d1d1d; stroke-width:1; } .zero { stroke:#4a4a4a; stroke-width:1; }
.tick { fill:var(--muted); font-size:11px; font-family:inherit; }
.lineacc { fill:none; stroke:var(--acc); stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }
.linespy { fill:none; stroke:var(--spy); stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }
.area { fill:var(--wash); } .enddot { stroke:var(--panel); stroke-width:2; }
.endlabel { fill:var(--ink); font-size:12px; font-weight:700; font-family:inherit; }
.barw { fill:var(--gain); } .barl { fill:var(--loss); }
.kvlist { display:grid; grid-template-columns:auto 1fr; gap:3px 12px; margin:0; }
.kvlist dt { color:var(--amber); font-size:11.5px; letter-spacing:.04em; padding-top:1px; }
.kvlist dd { margin:0; text-align:right; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.meter { height:10px; background:#1b1b1b; border:1px solid var(--rule); margin:8px 0 2px; position:relative; }
.meter > div { position:absolute; inset:0 auto 0 0; background:var(--amber); }
.sigs { display:flex; flex-wrap:wrap; gap:4px; margin-top:4px; }
.sig { border:1px solid var(--rule); padding:1px 6px; color:var(--ink2); }
.sig b { color:var(--ink); }
.scroll { overflow:auto; -webkit-overflow-scrolling:touch; } .tall { max-height:520px; }
table { border-collapse:collapse; width:100%; font-size:12.5px; }
th { position:sticky; top:0; z-index:1; background:var(--head); color:var(--amber); text-align:left; font-weight:600; font-size:11px;
  letter-spacing:.04em; padding:4px 8px; border-bottom:1px solid var(--rule); white-space:nowrap; }
td { padding:4px 8px; border-bottom:1px solid #171717; white-space:nowrap; }
.n { text-align:right; }
tbody tr:hover td { background:#141414; }
tr.win td { background:var(--gain-bg); } tr.loss td { background:var(--loss-bg); }
tr.win td:first-child { box-shadow:inset 3px 0 var(--gain); } tr.loss td:first-child { box-shadow:inset 3px 0 var(--loss); }
tr.win:hover td { background:rgba(38,208,124,.17); } tr.loss:hover td { background:rgba(255,92,92,.18); }
tr.dayrow td { background:#111; color:var(--amber); font-size:11px; letter-spacing:.05em; padding-top:6px; }
tr.total td { border-top:1px solid var(--rule); font-weight:700; background:#0f0f0f; }
.tag { display:inline-block; min-width:62px; text-align:center; font-weight:800; font-size:11px; padding:1px 6px; letter-spacing:.06em; }
.tag.win { background:var(--gain); color:#000; } .tag.loss { background:var(--loss); color:#000; }
.tag.even { border:1px solid var(--muted); color:var(--ink2); } .tag.open { border:1px solid #2c4a6e; color:var(--blue); }
.side { font-weight:800; letter-spacing:.06em; } .side.buy { color:var(--blue); } .side.sell { color:var(--amber); }
.eng { color:var(--muted); }
.why { color:var(--ink2); max-width:300px; overflow:hidden; text-overflow:ellipsis; }
.tools { display:flex; flex-wrap:wrap; gap:6px; align-items:center; padding:6px 8px; border-bottom:1px solid var(--line); }
.seg { display:inline-flex; flex-wrap:wrap; }
.seg button { background:#111; color:var(--ink2); border:1px solid var(--rule); margin-right:-1px; padding:3px 9px; cursor:pointer; }
.seg button[aria-pressed="true"] { background:var(--amber); color:#000; border-color:var(--amber); font-weight:700; }
.seg button.fw[aria-pressed="true"] { background:var(--gain); border-color:var(--gain); }
.seg button.fl[aria-pressed="true"] { background:var(--loss); border-color:var(--loss); }
.seg button:focus-visible, select:focus-visible, .fkeys a:focus-visible { outline:2px solid var(--amber); outline-offset:1px; }
select { background:#111; color:var(--ink); border:1px solid var(--rule); padding:3px 6px; }
.score { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:1px; background:var(--line); border:1px solid var(--line); margin-bottom:8px; }
.score > div { background:#0d0d0d; padding:6px 8px; text-align:center; }
.big { font-size:30px; font-weight:800; line-height:1.1; } .lbl { font-size:11px; letter-spacing:.08em; color:var(--ink2); }
.split { display:flex; height:18px; margin:2px 0 3px; border:1px solid var(--rule); font-size:11px; font-weight:800; color:#000; overflow:hidden; }
.split > div { display:flex; align-items:center; padding:0 6px; white-space:nowrap; min-width:0; overflow:hidden; }
.split .w { background:var(--gain); } .split .l { background:var(--loss); justify-content:flex-end; }
.cap { display:flex; justify-content:space-between; color:var(--muted); font-size:11px; margin-bottom:6px; }
.drow { display:grid; grid-template-columns:52px minmax(0, 1fr) 84px 54px; align-items:center; gap:8px; padding:2px 0; }
.drow .nm { color:var(--amber); font-weight:700; }
.track { display:grid; grid-template-columns:1fr 1fr; height:12px; }
.track > div { position:relative; } .track > div:first-child { border-right:1px solid #555; }
.track .neg { position:absolute; right:0; top:1px; bottom:1px; background:var(--loss); }
.track .pos { position:absolute; left:0; top:1px; bottom:1px; background:var(--gain); }
.rec { color:var(--ink2); font-size:11.5px; }
h3 { color:var(--amber); font-size:11.5px; letter-spacing:.05em; margin:12px 0 4px; font-weight:700; }
.log { font-size:11.5px; line-height:1.5; font-family:inherit; color:var(--ink2); white-space:pre-wrap; word-break:break-word; max-height:340px; overflow:auto; margin:0; }
.empty { color:var(--muted); padding:8px 0; }
.foot { color:var(--muted); font-size:11.5px; }
</style></head><body>
<header class="top">
  <span class="logo">OPTBOT</span>
  <span class="cmd">MSBC5220 <b>OPTIONS</b> MONITOR<span class="go">GO</span></span>
  <nav class="fkeys" aria-label="Sections">
    <a href="#mon"><b>1</b>MON</a><a href="#pos"><b>2</b>POS</a><a href="#wl"><b>3</b>W/L</a><a href="#blt"><b>4</b>BLOTTER</a><a href="#log"><b>5</b>LOG</a>
  </nav>
  <span class="status"><span class="dot" id="statusdot"></span><span id="statustext">CONNECTING</span><span id="clock"></span></span>
</header>
<div class="tape" aria-label="Prices of the stocks the bot follows"><div class="tape-track" id="tape"><span class="tk">Waiting for prices</span></div></div>
<main>
<section class="kpis" id="mon" aria-label="Summary">
  <div class="kpi"><div class="kl">ACCOUNT</div><div class="kv" id="k-acct">–</div><div class="ks" id="k-acct-s"></div></div>
  <div class="kpi"><div class="kl">TODAY</div><div class="kv" id="k-today">–</div><div class="ks" id="k-today-s"></div></div>
  <div class="kpi"><div class="kl">LEAD OVER SPY</div><div class="kv" id="k-lead">–</div><div class="ks" id="k-lead-s"></div></div>
  <div class="kpi"><div class="kl">BOT P&amp;L</div><div class="kv" id="k-pnl">–</div><div class="ks" id="k-pnl-s"></div></div>
  <div class="kpi"><div class="kl">REALIZED</div><div class="kv" id="k-real">–</div><div class="ks" id="k-real-s"></div></div>
  <div class="kpi"><div class="kl">UNREALIZED</div><div class="kv" id="k-unrl">–</div><div class="ks" id="k-unrl-s"></div></div>
  <div class="kpi"><div class="kl">WIN RATE</div><div class="kv" id="k-wr">–</div><div class="ks" id="k-wr-s"></div></div>
  <div class="kpi"><div class="kl">MARKET MOOD</div><div class="kv" id="k-mood">–</div><div class="ks" id="k-mood-s"></div></div>
</section>

<div class="row r3">
  <section class="panel"><div class="ph">ACCOUNT VS SPY <span class="sub">since the start, by day</span></div><div class="pb">
    <div class="legend"><span><span class="key" style="border-color:var(--acc)"></span>Account</span><span><span class="key" style="border-color:var(--spy)"></span>SPY</span></div>
    <div id="chart-daily"><p class="empty">No closing values yet.</p></div></div></section>
  <section class="panel"><div class="ph">INTRADAY <span class="sub">whole account, minute by minute</span></div><div class="pb">
    <div class="legend"><span><span class="key" style="border-color:var(--acc)"></span>Account value</span></div>
    <div id="chart-intraday"><p class="empty">Builds up while the market is open.</p></div></div></section>
  <section class="panel"><div class="ph">RISK <span class="sub">lead lock and next bets</span></div><div class="pb">
    <dl class="kvlist" id="risk"><dt>STATUS</dt><dd>Waiting for data</dd></dl>
    <div class="meter" aria-hidden="true"><div id="lock-fill" style="width:0"></div></div>
    <div class="cap"><span>options held</span><span id="lock-cap">of allowed</span></div>
    <h3>NEXT IN LINE</h3><div class="sigs" id="signals"><span class="mut">None</span></div>
    <p class="foot" style="margin:10px 0 0">The account must stay 5 points ahead of SPY. The bot may hold options worth up to twice the cushion above that floor; no cushion closes everything.</p>
  </div></section>
</div>

<section class="panel" id="pos"><div class="ph">OPEN POSITIONS <span class="sub" id="pos-sub"></span></div>
  <div class="scroll"><table><thead><tr><th>CONTRACT</th><th>ENGINE</th><th class="n">QTY</th><th>OPENED</th><th class="n">DAYS LEFT</th><th class="n">PAID</th><th class="n">MARK</th><th class="n">COST</th><th class="n">VALUE</th><th class="n">UNRL P&amp;L</th><th class="n">UNRL %</th></tr></thead>
  <tbody id="positions"><tr><td colspan="11" class="empty">Waiting for data.</td></tr></tbody></table></div>
  <div class="pb foot">P is a put, a bet the price falls; C is a call, a bet it rises. MARK is the middle of the current bid and ask.</div>
</section>

<div class="row r2" id="wl">
  <section class="panel"><div class="ph">WIN / LOSS RECORD <span class="sub">every sale, scored against what was paid</span></div><div class="pb">
    <div class="score">
      <div><div class="big up" id="w-n">–</div><div class="lbl">▲ WINS</div></div>
      <div><div class="big dn" id="l-n">–</div><div class="lbl">▼ LOSSES</div></div>
      <div><div class="big" id="w-rate">–</div><div class="lbl">WIN RATE</div></div>
    </div>
    <div class="cap"><span>BY COUNT</span><span id="cnt-cap"></span></div>
    <div class="split" id="split-n"><div class="w" style="flex:1">–</div></div>
    <div class="cap" style="margin-top:6px"><span>BY DOLLARS</span><span id="usd-cap"></span></div>
    <div class="split" id="split-d"><div class="w" style="flex:1">–</div></div>
    <dl class="kvlist" id="wl-facts" style="margin-top:10px"></dl>
    <h3>P&amp;L OF EACH SALE <span class="mut" style="font-weight:400;letter-spacing:0">oldest on the left</span></h3>
    <div class="legend"><span><span class="key" style="border-color:var(--gain);border-top-width:8px"></span>Win</span><span><span class="key" style="border-color:var(--loss);border-top-width:8px"></span>Loss</span></div>
    <div id="chart-sales"><p class="empty">No sales yet.</p></div>
  </div></section>
  <section class="panel"><div class="ph">P&amp;L BREAKDOWN <span class="sub">realized, from sales</span></div><div class="pb">
    <h3 style="margin-top:0">BY STOCK</h3><div id="by-ticker"><p class="empty">No sales yet.</p></div>
    <h3>BY ENGINE</h3>
    <div class="scroll"><table><thead><tr><th>ENGINE</th><th class="n">SALES</th><th class="n">W</th><th class="n">L</th><th class="n">WIN %</th><th class="n">P&amp;L</th></tr></thead><tbody id="by-engine"></tbody></table></div>
    <h3>BY REASON FOR SELLING</h3>
    <div class="scroll"><table><thead><tr><th>REASON</th><th class="n">SALES</th><th class="n">W</th><th class="n">L</th><th class="n">P&amp;L</th></tr></thead><tbody id="by-reason"></tbody></table></div>
  </div></section>
</div>

<section class="panel" id="blt"><div class="ph">TRADE BLOTTER <span class="sub" id="blt-sub">every buy and sell the bot has made</span></div>
  <div class="tools">
    <div class="seg" role="group" aria-label="Show">
      <button type="button" data-f="all" aria-pressed="true">ALL</button><button type="button" data-f="buy">BUYS</button><button type="button" data-f="sell">SELLS</button><button type="button" data-f="win" class="fw">▲ WINS</button><button type="button" data-f="loss" class="fl">▼ LOSSES</button>
    </div>
    <label class="mut">STOCK <select id="f-und"><option value="">ALL</option></select></label>
  </div>
  <div class="scroll tall"><table><thead><tr><th>TIME (ET)</th><th>SIDE</th><th>CONTRACT</th><th>ENGINE</th><th class="n">QTY</th><th class="n">PRICE</th><th class="n">AMOUNT</th><th>WHY</th><th class="n">HELD</th><th class="n">P&amp;L</th><th class="n">P&amp;L %</th><th>RESULT</th></tr></thead>
  <tbody id="blotter"><tr><td colspan="12" class="empty">Waiting for data.</td></tr></tbody></table></div>
</section>

<section class="panel" id="log"><div class="ph">BOT LOG <span class="sub">newest first</span></div><div class="pb"><pre class="log" id="logtext">Waiting for data.</pre></div></section>
<p class="foot" id="fallback" hidden>The live data can't be reached right now. The <a href="report.html">daily report</a> has the figures as of the last close.</p>
<p class="foot" id="foot">Practice money on Alpaca. The goal is to finish ahead of a portfolio that holds SPY. Refreshes every 15 seconds; nothing on this page can place a trade.</p>
</main>
<!--CONFIG-->
<script>
(function () {
  var last = null, filt = "all", und = "";
  var API = window.OPTBOT_API || "", FALLBACK = !!window.OPTBOT_FALLBACK;
  function $(id) { return document.getElementById(id); }
  function money(v) { return (v < 0 ? "−$" : "$") + Math.abs(Math.round(v)).toLocaleString("en-US"); }
  function signed(v) { return (v >= 0 ? "+$" : "−$") + Math.abs(Math.round(v)).toLocaleString("en-US"); }
  function pct(v, d) { if (v === null || v === undefined) return "–"; return (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(d === undefined ? 1 : d) + "%"; }
  function cls(v) { return v === null || v === undefined || v === 0 ? "" : v > 0 ? "up" : "dn"; }
  function arrow(v) { return v > 0 ? "▲ " : v < 0 ? "▼ " : ""; }
  function set(id, text, c) { var e = $(id); e.textContent = text; if (c !== undefined) e.className = e.className.split(" ")[0] + (c ? " " + c : ""); }
  function cell(tr, text, c) { var td = document.createElement("td"); td.textContent = text; if (c) td.className = c; tr.appendChild(td); return td; }
  function span(parent, text, c) { var s = document.createElement("span"); s.textContent = text; if (c) s.className = c; parent.appendChild(s); return s; }
  function empty(tb, text, cols) { var tr = tb.insertRow(); var td = cell(tr, text, "empty"); td.colSpan = cols; }
  function facts(dl, rows) { dl.textContent = ""; rows.forEach(function (r) { var dt = document.createElement("dt"); dt.textContent = r[0]; dl.appendChild(dt);
    var dd = document.createElement("dd"); dd.textContent = r[1]; if (r[2]) dd.className = r[2]; dl.appendChild(dd); }); }
  var NS = "http://www.w3.org/2000/svg";
  function el(name, attrs, parent) { var e = document.createElementNS(NS, name); for (var k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
  function ticks(lo, hi, n) { var span = (hi - lo) || 1, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), steps = [1, 2, 2.5, 5, 10], step = mag;
    for (var i = 0; i < steps.length; i++) if (steps[i] * mag >= raw) { step = steps[i] * mag; break; }
    var out = [], v = Math.floor(lo / step) * step; while (v <= hi + step * 0.999) { out.push(+v.toFixed(6)); v += step; } return out; }
  function kfmt(v) { var a = Math.abs(v); return (v < 0 ? "−" : "") + "$" + (a >= 1000 ? (a / 1000).toFixed(a % 1000 ? 1 : 0).replace(/\.0$/, "") + "K" : Math.round(a)); }

  function lineChart(box, series, labels, fmt) {
    box.textContent = "";
    var W = 520, H = 220, L = 50, R = 72, T = 10, B = 24, pw = W - L - R, ph = H - T - B;
    var all = []; series.forEach(function (s) { s.values.forEach(function (v) { if (v !== null) all.push(v); }); });
    if (all.length < 2) { var p = document.createElement("p"); p.className = "empty"; p.textContent = "Not enough points yet."; box.appendChild(p); return; }
    var tk = ticks(Math.min.apply(null, all), Math.max.apply(null, all), 4), lo = tk[0], hi = tk[tk.length - 1];
    var n = labels.length, x = function (i) { return L + pw * (n < 2 ? 0 : i / (n - 1)); }, y = function (v) { return T + ph * (1 - (v - lo) / ((hi - lo) || 1)); };
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img" }, box);
    tk.forEach(function (t) { el("line", { "class": t === 0 ? "zero" : "gridline", x1: L, x2: L + pw, y1: y(t), y2: y(t) }, svg);
      el("text", { "class": "tick", x: L - 6, y: y(t) + 4, "text-anchor": "end" }, svg).textContent = fmt(t, true); });
    var every = Math.max(1, Math.ceil(n / 6));
    labels.forEach(function (lab, i) { if (i % every === 0 || i === n - 1) el("text", { "class": "tick", x: x(i), y: H - 5, "text-anchor": "middle" }, svg).textContent = lab; });
    series.forEach(function (s) {
      var d = "", started = false;
      s.values.forEach(function (v, i) { if (v === null) return; d += (started ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1); started = true; });
      if (s.area && started) el("path", { "class": "area", d: d + "L" + x(n - 1).toFixed(1) + "," + y(lo) + "L" + x(0) + "," + y(lo) + "Z" }, svg);
      el("path", { "class": s.cls, d: d }, svg);
      var li = s.values.length - 1; while (li >= 0 && s.values[li] === null) li--;
      if (li >= 0) { el("circle", { "class": "enddot", cx: x(li), cy: y(s.values[li]), r: 4.5, fill: s.color }, svg);
        el("text", { "class": "endlabel", x: x(li) + 9, y: y(s.values[li]) + 4 }, svg).textContent = fmt(s.values[li]); }
    });
  }

  function salesChart(box, sales) {
    box.textContent = "";
    if (!sales.length) { var p = document.createElement("p"); p.className = "empty"; p.textContent = "No sales yet."; box.appendChild(p); return; }
    var W = 520, H = 190, L = 50, R = 8, T = 8, B = 22, pw = W - L - R, ph = H - T - B;
    var vals = sales.map(function (t) { return t.pnl; });
    var tk = ticks(Math.min(0, Math.min.apply(null, vals)), Math.max(0, Math.max.apply(null, vals)), 4), lo = tk[0], hi = tk[tk.length - 1];
    var y = function (v) { return T + ph * (1 - (v - lo) / ((hi - lo) || 1)); };
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Profit or loss of each sale" }, box);
    tk.forEach(function (t) { el("line", { "class": t === 0 ? "zero" : "gridline", x1: L, x2: L + pw, y1: y(t), y2: y(t) }, svg);
      el("text", { "class": "tick", x: L - 6, y: y(t) + 4, "text-anchor": "end" }, svg).textContent = kfmt(t); });
    var slot = pw / sales.length, bw = Math.max(2, Math.min(28, slot * 0.72));
    sales.forEach(function (t, i) {
      var cx = L + slot * (i + 0.5), top = y(Math.max(0, t.pnl)), h = Math.max(1, Math.abs(y(t.pnl) - y(0)));
      var r = el("rect", { "class": t.pnl >= 0 ? "barw" : "barl", x: (cx - bw / 2).toFixed(1), y: top.toFixed(1), width: bw.toFixed(1), height: h.toFixed(1) }, svg);
      el("title", {}, r).textContent = t.when + "  " + t.label + "  " + signed(t.pnl) + " (" + pct(t.pnl_pct, 0) + ")  " + t.reason;
    });
    el("text", { "class": "tick", x: L, y: H - 4 }, svg).textContent = sales[0].when.split(" ").slice(0, 2).join(" ");
    el("text", { "class": "tick", x: L + pw, y: H - 4, "text-anchor": "end" }, svg).textContent = sales[sales.length - 1].when.split(" ").slice(0, 2).join(" ");
  }

  function splitBar(box, a, b, la, lb) {
    box.textContent = "";
    var tot = a + b; if (!tot) { span(box, "No sales yet", "").style.color = "var(--muted)"; return; }
    var w = document.createElement("div"); w.className = "w"; w.style.flex = String(a); w.textContent = a ? la : ""; box.appendChild(w);
    var l = document.createElement("div"); l.className = "l"; l.style.flex = String(b); l.textContent = b ? lb : ""; box.appendChild(l);
  }

  function renderTape(m) {
    var tape = $("tape"); tape.textContent = "";
    if (!m || !m.length) { span(tape, "No prices yet", "tk"); return; }
    for (var rep = 0; rep < 2; rep++) m.forEach(function (q) {
      var s = span(tape, "", "tk"); var b = document.createElement("b"); b.textContent = q.symbol; s.appendChild(b);
      span(s, q.px.toFixed(2) + " "); span(s, arrow(q.chg_pct) + pct(q.chg_pct, 2), cls(q.chg_pct));
      span(s, "  5D " + pct(q.r5_pct), "mut");
    });
  }

  function renderBlotter() {
    var s = last; if (!s) return;
    var tb = $("blotter"); tb.textContent = "";
    var rows = (s.trades || []).filter(function (t) {
      if (und && t.und !== und) return false;
      if (filt === "buy" || filt === "sell") return t.side === filt;
      if (filt === "win" || filt === "loss") return t.side === "sell" && t.result === filt;
      return true;
    });
    if (!rows.length) { empty(tb, "Nothing matches this filter.", 12); return; }
    var day = null;
    rows.forEach(function (t) {
      if (t.day !== day) {
        day = t.day;
        var same = (s.trades || []).filter(function (r) { return r.day === day; });  // the whole day, whatever the filter
        var real = same.reduce(function (a, r) { return a + (r.pnl || 0); }, 0), sold = same.filter(function (r) { return r.side === "sell"; }).length;
        var hr = tb.insertRow(); hr.className = "dayrow";
        var td = cell(hr, new Date(day + "T12:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }).toUpperCase() +
          "  ·  " + same.length + (same.length === 1 ? " FILL" : " FILLS") + (sold ? "  ·  REALIZED " + signed(real) : ""));
        td.colSpan = 12;
      }
      var tr = tb.insertRow(); if (t.side === "sell") tr.className = t.result;
      cell(tr, t.when); cell(tr, t.side.toUpperCase(), "side " + t.side); cell(tr, t.label); cell(tr, t.engine, "eng");
      cell(tr, t.qty, "n"); cell(tr, "$" + t.px.toFixed(2), "n"); cell(tr, money(t.notional), "n");
      var why = cell(tr, t.reason, "why"); why.title = t.reason;
      if (t.side === "sell") {
        cell(tr, t.held || "–", "n"); cell(tr, signed(t.pnl), "n " + cls(t.pnl)); cell(tr, pct(t.pnl_pct, 0), "n " + cls(t.pnl_pct));
        var rc = document.createElement("td"); span(rc, t.result === "win" ? "▲ WIN" : t.result === "loss" ? "▼ LOSS" : "EVEN", "tag " + t.result); tr.appendChild(rc);
      } else {
        cell(tr, ""); cell(tr, ""); cell(tr, "");
        var oc = document.createElement("td"); span(oc, "BOUGHT", "tag open"); tr.appendChild(oc);
      }
    });
  }

  function render(s) {
    if (!s || s.waiting) return;
    last = s;
    var a = s.account, sl = s.sleeve, st = s.stats || {};
    set("k-acct", money(a.value)); set("k-acct-s", pct(a.return_pct) + " since the start", "");
    set("k-today", a.today_pct === null ? "–" : arrow(a.today_pct) + pct(a.today_pct, 2), cls(a.today_pct));
    set("k-today-s", "vs the last official close");
    set("k-lead", a.lead_pts === null ? "–" : (a.lead_pts >= 0 ? "+" : "−") + Math.abs(a.lead_pts).toFixed(1) + " PTS", cls(a.lead_pts));
    set("k-lead-s", a.spy_return_pct === null ? "" : "SPY " + pct(a.spy_return_pct, 2) + " since the start");
    set("k-pnl", signed(sl.profit), cls(sl.profit)); set("k-pnl-s", "sleeve " + money(sl.value) + " on " + money(sl.capital));
    set("k-real", signed(sl.realized || 0), cls(sl.realized)); set("k-real-s", (st.sales || 0) + " sales, " + (st.buys || 0) + " buys");
    set("k-unrl", signed(sl.unrealized || 0), cls(sl.unrealized)); set("k-unrl-s", s.positions.length + " open, " + money(sl.cash) + " cash");
    set("k-wr", st.win_rate === null || st.win_rate === undefined ? "–" : st.win_rate.toFixed(0) + "%");
    set("k-wr-s", (st.wins || 0) + " W / " + (st.losses || 0) + " L" + (st.profit_factor ? ", factor " + st.profit_factor.toFixed(2) : ""));
    var moods = { bear: "FALLING", bull: "RISING", mixed: "MIXED" };
    set("k-mood", (s.regime === "bear" ? "▼ " : s.regime === "bull" ? "▲ " : "") + (moods[s.regime] || (s.regime || "–").toUpperCase()), s.regime === "bear" ? "dn" : s.regime === "bull" ? "up" : "warn");
    set("k-mood-s", s.regime === "bear" ? "buying puts" : s.regime === "bull" ? "buying calls" : "SPY and QQQ disagree");
    renderTape(s.market);

    var lk = s.lock, exposure = s.positions.reduce(function (t, p) { return t + (p.value || 0); }, 0);
    var end = new Date(s.end_date + "T12:00:00"), daysLeft = Math.max(0, Math.round((end - new Date(s.as_of.slice(0, 10) + "T12:00:00")) / 864e5));
    if (lk.enabled && lk.floor) {
      var cushion = a.value - lk.floor, allowed = Math.max(0, lk.multiplier * cushion), used = allowed ? exposure / allowed * 100 : 100;
      facts($("risk"), [["FLOOR", money(lk.floor)], ["ACCOUNT", money(a.value)], ["CUSHION", signed(cushion), cls(cushion)],
        ["OPTIONS HELD", money(exposure)], ["ALLOWED", money(allowed)], ["ROOM FOR NEW", money(lk.room || 0), lk.room > 0 ? "" : "warn"],
        ["CONTEST ENDS", end.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + " · " + daysLeft + " days"]]);
      $("lock-fill").style.width = Math.min(100, used).toFixed(1) + "%"; $("lock-fill").style.background = used > 90 ? "var(--warn)" : "var(--amber)";
      $("lock-cap").textContent = used.toFixed(0) + "% of allowed";
    } else { facts($("risk"), [["LEAD LOCK", "off"], ["OPTIONS HELD", money(exposure)]]); }
    var sg = $("signals"); sg.textContent = "";
    if (!s.signals.length) span(sg, "None", "mut");
    s.signals.forEach(function (x) { var t = span(sg, "", "sig"); var b = document.createElement("b"); b.textContent = x.symbol; t.appendChild(b);
      span(t, " " + x.kind.toUpperCase() + " ", x.kind === "put" ? "dn" : "up"); span(t, x.strength_pct.toFixed(1) + "%"); });

    var daily = s.daily || [];
    lineChart($("chart-daily"), [
      { cls: "lineacc", color: "var(--acc)", values: daily.map(function (r) { return r.account_pct; }) },
      { cls: "linespy", color: "var(--spy)", values: daily.map(function (r) { return r.spy_pct; }) }
    ], daily.map(function (r) { return r.date === "start" ? "Start" : new Date(r.date + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }); }),
      function (v, axis) { return axis ? v + "%" : pct(v); });
    var intra = s.intraday || [];
    lineChart($("chart-intraday"), [{ cls: "lineacc", color: "var(--acc)", area: true, values: intra.map(function (p) { return p.account; }) }],
      intra.map(function (p) { return p.t; }), function (v, axis) { return axis ? "$" + Math.round(v / 1000) + "K" : money(v); });

    var tb = $("positions"); tb.textContent = "";
    var tc = 0, tv = 0, tu = 0;
    if (!s.positions.length) empty(tb, "No open positions.", 11);
    s.positions.forEach(function (p) {
      var tr = tb.insertRow(); if (p.upnl !== null && p.upnl !== undefined) tr.className = p.upnl >= 0 ? "win" : "loss";
      cell(tr, p.label); cell(tr, p.engine, "eng"); cell(tr, p.qty, "n"); cell(tr, p.opened || "–");
      cell(tr, p.dte, "n" + (p.dte <= 4 ? " warn" : "")); cell(tr, "$" + p.paid.toFixed(2), "n"); cell(tr, p.now === null ? "–" : "$" + p.now.toFixed(2), "n");
      cell(tr, money(p.cost), "n"); cell(tr, p.value === null ? "–" : money(p.value), "n");
      cell(tr, p.upnl === null || p.upnl === undefined ? "–" : arrow(p.upnl) + signed(p.upnl), "n " + cls(p.upnl));
      cell(tr, pct(p.pnl_pct, 0), "n " + cls(p.pnl_pct));
      tc += p.cost || 0; tv += p.value || 0; tu += p.upnl || 0;
    });
    if (s.positions.length) { var tt = tb.insertRow(); tt.className = "total"; cell(tt, "TOTAL"); cell(tt, ""); cell(tt, ""); cell(tt, ""); cell(tt, ""); cell(tt, ""); cell(tt, "");
      cell(tt, money(tc), "n"); cell(tt, money(tv), "n"); cell(tt, arrow(tu) + signed(tu), "n " + cls(tu)); cell(tt, tc ? pct((tv / tc - 1) * 100, 0) : "–", "n " + cls(tu)); }
    $("pos-sub").textContent = s.positions.length + (s.positions.length === 1 ? " position · " : " positions · ") + money(tv) + " at market";

    set("w-n", st.wins || 0); set("l-n", st.losses || 0);
    set("w-rate", st.win_rate === null || st.win_rate === undefined ? "–" : st.win_rate.toFixed(0) + "%");
    splitBar($("split-n"), st.wins || 0, st.losses || 0, (st.wins || 0) + " W", (st.losses || 0) + " L");
    splitBar($("split-d"), st.gross_win || 0, -(st.gross_loss || 0), signed(st.gross_win || 0), signed(st.gross_loss || 0));
    $("cnt-cap").textContent = (st.sales || 0) + " sales"; $("usd-cap").textContent = "net " + signed(st.realized || 0);
    var bw = st.best, ww = st.worst, sk = st.streak || {};
    facts($("wl-facts"), [
      ["AVERAGE WIN", st.avg_win === null ? "–" : signed(st.avg_win) + "  (" + pct(st.avg_win_pct, 0) + ")", "up"],
      ["AVERAGE LOSS", st.avg_loss === null ? "–" : signed(st.avg_loss) + "  (" + pct(st.avg_loss_pct, 0) + ")", "dn"],
      ["PROFIT FACTOR", st.profit_factor ? st.profit_factor.toFixed(2) + "  ($ won per $1 lost)" : "–"],
      ["BEST SALE", bw ? bw.label + "  " + signed(bw.pnl) + "  " + bw.when : "–", "up"],
      ["WORST SALE", ww ? ww.label + "  " + signed(ww.pnl) + "  " + ww.when : "–", "dn"],
      ["CURRENT STREAK", sk.n ? sk.n + (sk.result === "win" ? " WIN" : " LOSS") + (sk.n > 1 ? (sk.result === "win" ? "S" : "ES") : "") + " IN A ROW" : "–", sk.result === "win" ? "up" : sk.result === "loss" ? "dn" : ""],
      ["TURNOVER", money(st.bought || 0) + " bought, " + money(st.sold || 0) + " sold"]
    ]);
    var sales = (s.trades || []).filter(function (t) { return t.side === "sell"; }).reverse();
    salesChart($("chart-sales"), sales);

    var bt = $("by-ticker"); bt.textContent = "";
    var tick = st.by_ticker || [], mx = tick.reduce(function (m, g) { return Math.max(m, Math.abs(g.pnl)); }, 0) || 1;
    if (!tick.length) { var e0 = document.createElement("p"); e0.className = "empty"; e0.textContent = "No sales yet."; bt.appendChild(e0); }
    tick.forEach(function (g) {
      var r = document.createElement("div"); r.className = "drow"; bt.appendChild(r);
      span(r, g.name, "nm");
      var tr = document.createElement("div"); tr.className = "track"; r.appendChild(tr);
      var left = document.createElement("div"), right = document.createElement("div"); tr.appendChild(left); tr.appendChild(right);
      var bar = document.createElement("div"); bar.className = g.pnl < 0 ? "neg" : "pos"; bar.style.width = (Math.abs(g.pnl) / mx * 100).toFixed(1) + "%";
      (g.pnl < 0 ? left : right).appendChild(bar);
      span(r, signed(g.pnl), "n " + cls(g.pnl)); span(r, g.wins + "W " + g.losses + "L", "rec");
    });
    function groupTable(id, rows, withRate) {
      var t = $(id); t.textContent = "";
      if (!rows.length) { empty(t, "No sales yet.", withRate ? 6 : 5); return; }
      rows.forEach(function (g) { var tr = t.insertRow(); cell(tr, g.name); cell(tr, g.sales, "n"); cell(tr, g.wins, "n up"); cell(tr, g.losses, "n dn");
        if (withRate) cell(tr, (g.wins + g.losses ? Math.round(g.wins / (g.wins + g.losses) * 100) : 0) + "%", "n");
        cell(tr, signed(g.pnl), "n " + cls(g.pnl)); });
    }
    groupTable("by-engine", st.by_engine || [], true); groupTable("by-reason", st.by_reason || [], false);

    var sel = $("f-und"), names = {}; (s.trades || []).forEach(function (t) { names[t.und] = 1; });
    var want = [""].concat(Object.keys(names).sort());
    if (sel.options.length !== want.length) { sel.textContent = ""; want.forEach(function (n) { var o = document.createElement("option"); o.value = n; o.textContent = n || "ALL"; sel.appendChild(o); }); sel.value = und; }
    $("blt-sub").textContent = (st.buys || 0) + " buys · " + (st.sales || 0) + " sells · " + (st.wins || 0) + " wins · " + (st.losses || 0) + " losses";
    renderBlotter();

    $("logtext").textContent = (s.log || []).slice().reverse().join("\n") || "Nothing yet.";
    $("foot").textContent = "Data as of " + s.as_of_text + ". Practice money on Alpaca; the goal is to finish ahead of a portfolio that holds SPY. Contest ends " + s.end_date + ". Refreshes every 15 seconds; nothing on this page can place a trade.";
    status();
  }

  Array.prototype.forEach.call(document.querySelectorAll(".seg button"), function (b) {
    b.addEventListener("click", function () { filt = b.getAttribute("data-f");
      Array.prototype.forEach.call(document.querySelectorAll(".seg button"), function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      renderBlotter(); });
  });
  $("f-und").addEventListener("change", function () { und = this.value; renderBlotter(); });

  function status() {
    var dot = $("statusdot"), text = $("statustext");
    if (!last) return;
    var age = (Date.now() - new Date(last.as_of).getTime()) / 1000;
    if (!last.market_open) { dot.className = "dot"; text.textContent = "MARKET CLOSED · " + ago(age); }
    else if (age < 150) { dot.className = "dot live"; text.textContent = "LIVE · " + ago(age); }
    else { dot.className = "dot stale"; text.textContent = "DELAYED · " + ago(age); }
  }
  function ago(s) { s = Math.max(0, Math.round(s)); return s < 60 ? s + "s ago" : s < 3600 ? Math.round(s / 60) + "m ago" : Math.round(s / 3600) + "h ago"; }
  function clock() { try { $("clock").textContent = new Date().toLocaleTimeString("en-US", { timeZone: "America/New_York", hour12: false }) + " ET"; } catch (e) {} }

  function poll() {
    fetch(API + "/api/state", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (s) { $("fallback").hidden = true; render(s); })
      .catch(function () { $("statusdot").className = "dot stale"; $("statustext").textContent = "CANNOT REACH THE BOT · RETRYING";
        if (FALLBACK) $("fallback").hidden = false; });
  }
  poll(); clock(); setInterval(poll, 15000); setInterval(function () { status(); clock(); }, 1000);
})();
</script></body></html>
"""
