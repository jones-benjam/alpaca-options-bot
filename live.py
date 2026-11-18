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

        positions = []
        for symbol, p in sorted(led.pos.items(), key=lambda kv: kv[1].expiry):
            q = read_quote(quotes.get(symbol))
            mark = q[2] if q else None
            positions.append({
                "label": p.label(), "engine": "same-day" if p.tag == "odte" else "three-week",
                "kind": p.kind, "qty": p.qty, "paid": round(p.avg, 2),
                "now": round(mark, 2) if mark else None,
                "value": round(p.qty * mark * 100) if mark else None,
                "pnl_pct": round((mark / p.avg - 1) * 100, 1) if mark else None,
                "expires": p.expiry.isoformat(),
            })
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
                       "profit": round(sleeve_value - C.SLEEVE_START, 2), "capital": C.SLEEVE_START},
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
/* Layout: summary tiles, then the lead-over-SPY strip, charts, the book, activity. One column on phones. */
:root { color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10);
  --account:#2a78d6; --spy:#eb6834; --gain:#006300; --loss:#d03b3b; --warn:#9a6700; --wash:rgba(42,120,214,.10); }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --account:#3987e5; --spy:#d95926; --gain:#0ca30c; --loss:#e66767; --warn:#fab219; --wash:rgba(57,135,229,.14); } }
:root[data-theme="dark"] { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --account:#3987e5; --spy:#d95926; --gain:#0ca30c; --loss:#e66767; --warn:#fab219; --wash:rgba(57,135,229,.14); }
* { box-sizing:border-box; }
body { margin:0; background:var(--page); color:var(--ink); font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1080px; margin:0 auto; padding-block:16px 40px;
  padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); }
header { display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; gap:8px 16px; margin-bottom:14px; }
h1 { font-size:22px; margin:0; text-wrap:balance; } h2 { font-size:16px; margin:0 0 8px; }
.pill { display:inline-flex; align-items:center; gap:6px; font-size:13px; color:var(--ink2);
  border:1px solid var(--border); border-radius:999px; padding:3px 10px; background:var(--surface); }
.dot { width:8px; height:8px; border-radius:50%; background:var(--muted); }
.dot.live { background:var(--gain); } .dot.stale { background:var(--warn); }
.tiles { display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:10px; margin-bottom:12px; }
.tile, .card { background:var(--surface); border:1px solid var(--border); border-radius:10px; }
.tile { padding:12px 14px; } .card { padding:14px 16px; margin-bottom:12px; min-width:0; }
.k { color:var(--ink2); font-size:13px; } .v { font-size:26px; font-weight:650; line-height:1.2; font-variant-numeric:tabular-nums; }
.d { font-size:13px; color:var(--ink2); font-variant-numeric:tabular-nums; }
.up { color:var(--gain); } .down { color:var(--loss); }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:12px; }
.legend { display:flex; gap:16px; flex-wrap:wrap; font-size:13px; color:var(--ink2); margin-bottom:4px; }
.key { display:inline-block; width:16px; border-top:2px solid; vertical-align:middle; margin-right:6px; }
svg { width:100%; height:auto; display:block; overflow:visible; }
.gridline { stroke:var(--grid); stroke-width:1; } .zero { stroke:var(--axis); stroke-width:1; }
.tick { fill:var(--muted); font-size:11px; font-variant-numeric:tabular-nums; }
.lineacc { fill:none; stroke:var(--account); stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }
.linespy { fill:none; stroke:var(--spy); stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }
.area { fill:var(--wash); } .enddot { stroke:var(--surface); stroke-width:2; }
.endlabel { fill:var(--ink); font-size:12px; font-weight:600; }
.lockbar { position:relative; height:12px; border-radius:6px; background:var(--grid); margin:10px 0 6px; overflow:hidden; }
.lockfill { position:absolute; inset:0 auto 0 0; background:var(--account); border-radius:6px; }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:14px; }
th, td { text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--grid); white-space:nowrap; }
th { color:var(--ink2); font-weight:600; font-size:13px; } .n { text-align:right; font-variant-numeric:tabular-nums; }
.chip { display:inline-block; font-size:12px; padding:1px 8px; border-radius:999px; border:1px solid var(--border); color:var(--ink2); }
.log { font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--ink2); white-space:pre-wrap; word-break:break-word;
  max-height:320px; overflow:auto; margin:0; }
.muted { color:var(--muted); font-size:13px; }
.empty { color:var(--muted); padding:8px 0; }
</style></head><body><main>
<header>
  <h1>Options Bot Live</h1>
  <span class="pill" id="status"><span class="dot" id="statusdot"></span><span id="statustext">Waiting for the first update</span></span>
</header>
<p class="muted" style="margin:-6px 0 12px">Practice money on Alpaca. The goal is to finish ahead of a portfolio that holds SPY. This page refreshes itself every 15 seconds.</p>

<section class="tiles" aria-label="Summary">
  <div class="tile"><div class="k">Whole account</div><div class="v" id="t-account">–</div><div class="d" id="t-account-d"></div></div>
  <div class="tile"><div class="k">Lead over SPY</div><div class="v" id="t-lead">–</div><div class="d" id="t-lead-d"></div></div>
  <div class="tile"><div class="k">Bot's profit</div><div class="v" id="t-profit">–</div><div class="d" id="t-profit-d"></div></div>
  <div class="tile"><div class="k">Market mood</div><div class="v" id="t-mood">–</div><div class="d" id="t-mood-d"></div></div>
</section>

<section class="card">
  <h2>Lead lock</h2>
  <div class="d" id="lock-text">Waiting for data.</div>
  <div class="lockbar" aria-hidden="true"><div class="lockfill" id="lock-fill" style="width:0"></div></div>
  <div class="muted">The bot keeps the whole account at least 5 points ahead of SPY. It may hold options worth up to twice the lead above that line; less lead means fewer new bets, and no lead closes everything.</div>
</section>

<div class="grid2">
  <section class="card">
    <h2>Account against SPY, by day</h2>
    <div class="legend"><span><span class="key" style="border-color:var(--account)"></span>Account</span><span><span class="key" style="border-color:var(--spy)"></span>SPY</span></div>
    <div id="chart-daily"><p class="empty">No closing values yet.</p></div>
  </section>
  <section class="card">
    <h2>Today, minute by minute</h2>
    <div class="legend"><span><span class="key" style="border-color:var(--account)"></span>Whole account value</span></div>
    <div id="chart-intraday"><p class="empty">Builds up while the market is open.</p></div>
  </section>
</div>

<section class="card">
  <h2>Open positions</h2>
  <div class="scroll"><table><thead><tr><th>Position</th><th>Kind</th><th class="n">Contracts</th><th class="n">Paid</th><th class="n">Now</th><th class="n">Value</th><th class="n">Result</th></tr></thead>
  <tbody id="positions"><tr><td colspan="7" class="empty">Waiting for data.</td></tr></tbody></table></div>
  <p class="muted" style="margin:8px 0 0">P is a put, a bet the price falls. C is a call, a bet it rises.</p>
</section>

<div class="grid2">
  <section class="card">
    <h2>Recent sales</h2>
    <div class="scroll"><table><thead><tr><th>When</th><th>Contract</th><th class="n">Qty</th><th class="n">Price</th><th class="n">Profit</th></tr></thead>
    <tbody id="closed"><tr><td colspan="5" class="empty">None yet.</td></tr></tbody></table></div>
  </section>
  <section class="card">
    <h2>What the bot is saying</h2>
    <pre class="log" id="log">Waiting for data.</pre>
  </section>
</div>
<p class="muted" id="fallback" hidden>The live data can't be reached right now. The <a href="report.html">daily report</a> has the figures as of the last close.</p>
<p class="muted" id="foot"></p>
</main>
<!--CONFIG-->
<script>
(function () {
  var last = null, lastFetch = 0;
  var API = window.OPTBOT_API || "", FALLBACK = !!window.OPTBOT_FALLBACK;
  function $(id) { return document.getElementById(id); }
  function money(v) { return (v < 0 ? "−$" : "$") + Math.abs(Math.round(v)).toLocaleString("en-US"); }
  function signed(v) { return (v >= 0 ? "+$" : "−$") + Math.abs(Math.round(v)).toLocaleString("en-US"); }
  function pct(v, d) { if (v === null || v === undefined) return "–"; return (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(d === undefined ? 1 : d) + "%"; }
  function set(id, text, cls) { var e = $(id); e.textContent = text; if (cls !== undefined) e.className = e.className.split(" ")[0] + (cls ? " " + cls : ""); }
  function cell(tr, text, cls) { var td = document.createElement("td"); td.textContent = text; if (cls) td.className = cls; tr.appendChild(td); return td; }
  var NS = "http://www.w3.org/2000/svg";
  function el(name, attrs, parent) { var e = document.createElementNS(NS, name); for (var k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
  function ticks(lo, hi, n) { var span = (hi - lo) || 1, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), steps = [1, 2, 2.5, 5, 10], step = mag;
    for (var i = 0; i < steps.length; i++) if (steps[i] * mag >= raw) { step = steps[i] * mag; break; }
    var out = [], v = Math.floor(lo / step) * step; while (v <= hi + step * 0.999) { out.push(+v.toFixed(6)); v += step; } return out; }

  function lineChart(box, series, labels, fmt) {
    box.textContent = "";
    var W = 520, H = 230, L = 48, R = 70, T = 10, B = 26, pw = W - L - R, ph = H - T - B;
    var all = []; series.forEach(function (s) { s.values.forEach(function (v) { if (v !== null) all.push(v); }); });
    if (all.length < 2) { var p = document.createElement("p"); p.className = "empty"; p.textContent = "Not enough points yet."; box.appendChild(p); return; }
    var tk = ticks(Math.min.apply(null, all), Math.max.apply(null, all), 4), lo = tk[0], hi = tk[tk.length - 1];
    var n = labels.length, x = function (i) { return L + pw * (n < 2 ? 0 : i / (n - 1)); }, y = function (v) { return T + ph * (1 - (v - lo) / ((hi - lo) || 1)); };
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img" }, box);
    tk.forEach(function (t) { el("line", { "class": t === 0 ? "zero" : "gridline", x1: L, x2: L + pw, y1: y(t), y2: y(t) }, svg);
      el("text", { "class": "tick", x: L - 6, y: y(t) + 4, "text-anchor": "end" }, svg).textContent = fmt(t, true); });
    var every = Math.max(1, Math.ceil(n / 6));
    labels.forEach(function (lab, i) { if (i % every === 0 || i === n - 1) el("text", { "class": "tick", x: x(i), y: H - 6, "text-anchor": "middle" }, svg).textContent = lab; });
    series.forEach(function (s) {
      var d = "", started = false;
      s.values.forEach(function (v, i) { if (v === null) return; d += (started ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1); started = true; });
      if (s.area && started) el("path", { "class": "area", d: d + "L" + x(n - 1).toFixed(1) + "," + y(lo) + "L" + x(0) + "," + y(lo) + "Z" }, svg);
      el("path", { "class": s.cls, d: d }, svg);
      var li = s.values.length - 1; while (li >= 0 && s.values[li] === null) li--;
      if (li >= 0) { el("circle", { "class": "enddot", cx: x(li), cy: y(s.values[li]), r: 4.5, fill: s.color }, svg);
        if (!s.nolabel) el("text", { "class": "endlabel", x: x(li) + 9, y: y(s.values[li]) + 4 }, svg).textContent = fmt(s.values[li]); }
    });
  }

  function render(s) {
    if (!s || s.waiting) return;
    last = s;
    var a = s.account, sl = s.sleeve;
    set("t-account", money(a.value));
    set("t-account-d", pct(a.return_pct) + " since the start" + (a.today_pct !== null ? ", " + pct(a.today_pct, 2) + " today" : ""), "");
    set("t-lead", a.lead_pts === null ? "–" : (a.lead_pts >= 0 ? "+" : "−") + Math.abs(a.lead_pts).toFixed(1) + " pts");
    set("t-lead-d", a.spy_return_pct === null ? "" : "SPY " + pct(a.spy_return_pct, 2) + " since the start", "");
    set("t-profit", signed(sl.profit), sl.profit >= 0 ? "up" : "down");
    set("t-profit-d", "sleeve " + money(sl.value) + ", " + money(sl.cash) + " in cash");
    var moods = { bear: "Falling", bull: "Rising", mixed: "Mixed" };
    set("t-mood", moods[s.regime] || s.regime || "–");
    set("t-mood-d", s.signals.length ? "Next up: " + s.signals.slice(0, 3).map(function (x) { return x.symbol + " " + x.kind; }).join(", ") : "No signals");

    var lk = s.lock;
    if (lk.enabled && lk.floor) {
      var exposure = s.positions.reduce(function (t, p) { return t + (p.value || 0); }, 0);
      var allowed = Math.max(0, lk.multiplier * (a.value - lk.floor));
      $("lock-text").textContent = "Floor " + money(lk.floor) + ". Account " + money(a.value) + ", so the lead above the floor is " + money(a.value - lk.floor) +
        ". Options held " + money(exposure) + " of " + money(allowed) + " allowed; room for new bets " + money(lk.room || 0) + ".";
      $("lock-fill").style.width = Math.min(100, allowed ? exposure / allowed * 100 : 100).toFixed(1) + "%";
    } else { $("lock-text").textContent = "The lead lock is off."; }

    var daily = s.daily || [];
    lineChart($("chart-daily"), [
      { cls: "lineacc", color: "var(--account)", values: daily.map(function (r) { return r.account_pct; }) },
      { cls: "linespy", color: "var(--spy)", values: daily.map(function (r) { return r.spy_pct; }) }
    ], daily.map(function (r) { return r.date === "start" ? "Start" : new Date(r.date + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }); }),
      function (v, axis) { return axis ? v + "%" : pct(v); });
    var intra = s.intraday || [];
    lineChart($("chart-intraday"), [{ cls: "lineacc", color: "var(--account)", area: true, values: intra.map(function (p) { return p.account; }) }],
      intra.map(function (p) { return p.t; }), function (v, axis) { return axis ? "$" + Math.round(v / 1000) + "K" : money(v); });

    var tb = $("positions"); tb.textContent = "";
    if (!s.positions.length) { var tr0 = tb.insertRow(); var td0 = cell(tr0, "No open positions.", "empty"); td0.colSpan = 7; }
    s.positions.forEach(function (p) {
      var tr = tb.insertRow(); cell(tr, p.label);
      var td = document.createElement("td"); var chip = document.createElement("span"); chip.className = "chip"; chip.textContent = p.engine; td.appendChild(chip); tr.appendChild(td);
      cell(tr, p.qty, "n"); cell(tr, "$" + p.paid.toFixed(2), "n"); cell(tr, p.now === null ? "–" : "$" + p.now.toFixed(2), "n");
      cell(tr, p.value === null ? "–" : money(p.value), "n"); cell(tr, p.pnl_pct === null ? "–" : pct(p.pnl_pct, 0), "n " + (p.pnl_pct >= 0 ? "up" : "down"));
    });
    var cb = $("closed"); cb.textContent = "";
    if (!s.closed.length) { var tr1 = cb.insertRow(); var td1 = cell(tr1, "None yet.", "empty"); td1.colSpan = 5; }
    s.closed.forEach(function (c) { var tr = cb.insertRow(); cell(tr, c.when); cell(tr, c.symbol); cell(tr, c.qty, "n"); cell(tr, "$" + c.price.toFixed(2), "n"); cell(tr, signed(c.pnl), "n " + (c.pnl >= 0 ? "up" : "down")); });
    var lg = $("log"); lg.textContent = (s.log || []).slice().reverse().join("\n") || "Nothing yet.";
    $("foot").textContent = "Data as of " + s.as_of_text + ". Contest ends " + s.end_date + ". Read-only: nothing on this page can place a trade.";
    status();
  }

  function status() {
    var dot = $("statusdot"), text = $("statustext");
    if (!last) return;
    var age = (Date.now() - new Date(last.as_of).getTime()) / 1000;
    if (!last.market_open) { dot.className = "dot"; text.textContent = "Market closed · updated " + ago(age); }
    else if (age < 150) { dot.className = "dot live"; text.textContent = "Live · updated " + ago(age); }
    else { dot.className = "dot stale"; text.textContent = "Delayed · last update " + ago(age); }
  }
  function ago(s) { s = Math.max(0, Math.round(s)); return s < 60 ? s + "s ago" : s < 3600 ? Math.round(s / 60) + " min ago" : Math.round(s / 3600) + " h ago"; }

  function poll() {
    lastFetch = Date.now();
    fetch(API + "/api/state", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (s) { $("fallback").hidden = true; render(s); })
      .catch(function () { $("statusdot").className = "dot stale"; $("statustext").textContent = "Cannot reach the bot · retrying";
        if (FALLBACK) $("fallback").hidden = false; });
  }
  poll(); setInterval(poll, 15000); setInterval(status, 1000);
})();
</script></body></html>
"""
