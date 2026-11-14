#!/usr/bin/env python3
"""Build a one-page dashboard of the project: docs/index.html.

    python3 dashboard.py

It reads only the project's own records (STRATEGY_LOG.md and memory/), needs
no keys and no packages, and writes a single self-contained page: no outside
scripts, fonts or images. Open the file in any browser, or turn on GitHub
Pages for the /docs folder to get a link the whole team can use.
"""
import csv
import datetime as dt
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
MEMORY = ROOT / "memory"
OUT = ROOT / "docs" / "index.html"
START_VALUE = 100_000.0
esc = html.escape


# ---- data ---------------------------------------------------------------------
def daily_rows():
    rows = []
    log = ROOT / "STRATEGY_LOG.md"
    for line in log.read_text().splitlines() if log.exists() else []:
        if re.match(r"^\| \d{4}-\d{2}-\d{2}", line):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) >= 10:
                money = lambda s: float(re.sub(r"[^\d.\-]", "", s.replace("-$", "-")) or 0)
                rows.append({
                    "date": c[0][:10], "label": c[0], "final": "(" not in c[0],
                    "account": money(c[1]), "sleeve": money(c[3]), "profit": money(c[5]),
                    "spy": float(c[7].replace("%", "").replace("+", "") or 0),
                    "holding": c[8], "trades": c[9],
                })
    return rows


def read_csv(name):
    path = MEMORY / name
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def section(path, heading):
    if not path.exists():
        return ""
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", path.read_text(), flags=re.S | re.M)
    return m.group(1).strip() if m else ""


def short(date):
    return dt.date.fromisoformat(date).strftime("%b %-d")


def pct(x, digits=1):
    return f"{'+' if x >= 0 else '−'}{abs(x):.{digits}f}%"


def dollars(x):
    return f"{'+' if x >= 0 else '−'}${abs(x):,.0f}"


def nice_ticks(lo, hi, target=5):
    span = (hi - lo) or 1
    raw = span / target
    mag = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 1
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    first = int(lo // step) * step
    ticks, v = [], first
    while v <= hi + step * 0.999:
        ticks.append(round(v, 6))
        v += step
    return ticks


# ---- charts -------------------------------------------------------------------
def line_chart(points):
    """Account and SPY, both as % change since the start, on one axis."""
    W, H, L, R, T, B = 720, 300, 46, 112, 14, 30
    pw, ph = W - L - R, H - T - B
    values = [p["account"] for p in points] + [p["spy"] for p in points]
    ticks = nice_ticks(min(0, min(values)), max(values))
    lo, hi = ticks[0], ticks[-1]
    x = lambda i: L + (pw * i / max(1, len(points) - 1))
    y = lambda v: T + ph * (1 - (v - lo) / (hi - lo))
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="lc-title lc-desc" class="chart" id="line-chart">',
           '<title id="lc-title">Account and SPY, percent change since the start</title>',
           f'<desc id="lc-desc">The account is at {pct(points[-1]["account"])} and SPY at '
           f'{pct(points[-1]["spy"])} as of {esc(points[-1]["name"])}.</desc>']
    for t in ticks:
        cls = "axis" if t == 0 else "grid"
        out.append(f'<line class="{cls}" x1="{L}" x2="{L + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        out.append(f'<text class="tick" x="{L - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{t:g}%</text>')
    every = 1 if len(points) <= 9 else 2 if len(points) <= 18 else 3
    for i, p in enumerate(points):
        if i % every == 0 or i == len(points) - 1:
            out.append(f'<text class="tick" x="{x(i):.1f}" y="{H - 8}" text-anchor="middle">{esc(p["name"])}</text>')
    for key in ("spy", "account"):
        path = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(p[key]):.1f}" for i, p in enumerate(points))
        out.append(f'<path class="line s-{key}" d="{path}"/>')
    ends = {k: y(points[-1][k]) for k in ("account", "spy")}
    crowded = abs(ends["account"] - ends["spy"]) < 16
    for key, name in (("account", "Account"), ("spy", "SPY")):
        ex = x(len(points) - 1)
        out.append(f'<circle class="dot s-{key}" cx="{ex:.1f}" cy="{ends[key]:.1f}" r="4.5"/>')
        if not (crowded and key == "spy"):  # never stack colliding labels; the legend covers it
            out.append(f'<text class="endlabel" x="{ex + 10:.1f}" y="{ends[key] + 4:.1f}">'
                       f'<tspan class="strong">{pct(points[-1][key])}</tspan> {name}</text>')
    out.append(f'<line class="crosshair" id="crosshair" x1="0" x2="0" y1="{T}" y2="{T + ph}" visibility="hidden"/>')
    for i in range(len(points)):  # one wide, focusable hit area per day
        left = L if i == 0 else (x(i - 1) + x(i)) / 2
        right = L + pw if i == len(points) - 1 else (x(i) + x(i + 1)) / 2
        out.append(f'<rect class="hit" data-i="{i}" data-x="{x(i):.1f}" x="{left:.1f}" y="{T}" '
                   f'width="{right - left:.1f}" height="{ph}" tabindex="0" '
                   f'aria-label="{esc(points[i]["name"])}: account {pct(points[i]["account"])}, SPY {pct(points[i]["spy"])}"/>')
    out.append("</svg>")
    return "\n".join(out)


def bar_chart(trades):
    """Profit or loss of each closed trade. Direction and sign carry the meaning;
    the two colours only reinforce it."""
    W, H, L, R, T, B = 720, 260, 56, 16, 22, 34
    pw, ph = W - L - R, H - T - B
    values = [t["profit"] for t in trades]
    ticks = nice_ticks(min(0, min(values)), max(0, max(values)), 4)
    lo, hi = ticks[0], ticks[-1]
    y = lambda v: T + ph * (1 - (v - lo) / (hi - lo))
    band = pw / len(trades)
    bw = min(24, band - 2)
    best, worst = max(values), min(values)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="bc-title bc-desc" class="chart" id="bar-chart">',
           '<title id="bc-title">Profit or loss of each closed trade</title>',
           f'<desc id="bc-desc">{sum(v > 0 for v in values)} of {len(values)} closed trades made money. '
           f'Best {dollars(best)}, worst {dollars(worst)}.</desc>']
    for t in ticks:
        cls = "axis" if t == 0 else "grid"
        compact = abs(hi) >= 10000 or abs(lo) >= 10000
        label = "$0" if t == 0 else (f"{'−' if t < 0 else ''}${abs(t) / 1000:g}K" if compact
                                     else f"{'−' if t < 0 else ''}${abs(t):,.0f}")
        out.append(f'<line class="{cls}" x1="{L}" x2="{L + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        out.append(f'<text class="tick" x="{L - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{label}</text>')
    zero = y(0)
    for i, t in enumerate(trades):
        cx = L + band * (i + 0.5)
        v, top = t["profit"], min(y(t["profit"]), zero)
        h = max(1.5, abs(y(v) - zero))
        r = min(4, h, bw / 2)
        x0, x1 = cx - bw / 2, cx + bw / 2
        if v >= 0:   # rounded at the data end, square on the baseline
            d = f"M{x0:.1f},{zero:.1f} V{top + r:.1f} Q{x0:.1f},{top:.1f} {x0 + r:.1f},{top:.1f} H{x1 - r:.1f} Q{x1:.1f},{top:.1f} {x1:.1f},{top + r:.1f} V{zero:.1f} Z"
        else:
            bot = zero + h
            d = f"M{x0:.1f},{zero:.1f} V{bot - r:.1f} Q{x0:.1f},{bot:.1f} {x0 + r:.1f},{bot:.1f} H{x1 - r:.1f} Q{x1:.1f},{bot:.1f} {x1:.1f},{bot - r:.1f} V{zero:.1f} Z"
        tip = f"#{t['id']} {t['underlying']} {t['direction']}: {dollars(v)} ({t['exit_words']})"
        out.append(f'<path class="bar {"gain" if v >= 0 else "loss"}" d="{d}" tabindex="0" data-tip="{esc(tip)}" aria-label="{esc(tip)}"/>')
        if v in (best, worst):  # label only the extremes; the rest live in the tooltip and table
            ly = top - 6 if v >= 0 else zero + h + 14
            out.append(f'<text class="barlabel" x="{cx:.1f}" y="{ly:.1f}" text-anchor="middle">{dollars(v)}</text>')
        if len(trades) <= 16 or i % 2 == 0:
            out.append(f'<text class="tick" x="{cx:.1f}" y="{H - 10}" text-anchor="middle">#{t["id"]}</text>')
    out.append("</svg>")
    return "\n".join(out)


# ---- page ---------------------------------------------------------------------
CSS = """
:root { color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
  --account:#2a78d6; --spy:#eb6834; --gain:#2a78d6; --loss:#e34948; --up:#006300; --down:#d03b3b; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
  --account:#3987e5; --spy:#d95926; --gain:#3987e5; --loss:#e66767; --up:#0ca30c; --down:#e66767; } }
:root[data-theme="dark"] { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
  --account:#3987e5; --spy:#d95926; --gain:#3987e5; --loss:#e66767; --up:#0ca30c; --down:#e66767; }
* { box-sizing: border-box; }
body { margin:0; background:var(--page); color:var(--ink);
  font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:980px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:18px; margin:0 0 4px; }
p { margin:0 0 12px; } .sub { color:var(--ink2); margin-bottom:20px; } .small { color:var(--muted); font-size:13px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:18px; margin-bottom:16px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-bottom:16px; }
.tile { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
.tile .k { color:var(--ink2); font-size:13px; } .tile .v { font-size:28px; font-weight:650; line-height:1.2; }
.tile .d { font-size:13px; color:var(--ink2); } .up { color:var(--up); } .down { color:var(--down); }
.legend { display:flex; gap:18px; flex-wrap:wrap; color:var(--ink2); font-size:14px; margin:6px 0 4px; }
.key { display:inline-block; width:18px; height:0; border-top:2px solid; vertical-align:middle; margin-right:6px; }
.sw { display:inline-block; width:10px; height:10px; border-radius:2px; vertical-align:middle; margin-right:6px; }
.chartwrap { position:relative; } svg.chart { width:100%; height:auto; display:block; overflow:visible; }
.grid { stroke:var(--grid); stroke-width:1; } .axis { stroke:var(--axis); stroke-width:1; }
.tick { fill:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
.line { fill:none; stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }
.line.s-account, .dot.s-account { stroke:var(--account); } .line.s-spy { stroke:var(--spy); }
.dot { stroke:var(--surface); stroke-width:2; } .dot.s-account { fill:var(--account); } .dot.s-spy { fill:var(--spy); stroke:var(--surface); }
.endlabel { fill:var(--ink2); font-size:13px; } .endlabel .strong { fill:var(--ink); font-weight:650; }
.barlabel { fill:var(--ink); font-size:12px; font-weight:600; }
.bar.gain { fill:var(--gain); } .bar.loss { fill:var(--loss); }
.bar:hover, .bar:focus { opacity:.78; outline:none; } .hit { fill:transparent; outline:none; }
.crosshair { stroke:var(--axis); stroke-width:1; }
.tip { position:absolute; pointer-events:none; background:var(--surface); border:1px solid var(--border);
  border-radius:8px; padding:8px 10px; font-size:13px; box-shadow:0 4px 14px rgba(0,0,0,.12); white-space:nowrap; display:none; z-index:2; }
.tip b { font-size:15px; } .tip .row { color:var(--ink2); }
table { border-collapse:collapse; width:100%; font-size:14px; } th, td { text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--grid); }
th { color:var(--ink2); font-weight:600; } td.n, th.n { text-align:right; font-variant-numeric:tabular-nums; }
.scroll { overflow-x:auto; } details { margin-top:10px; } summary { cursor:pointer; color:var(--ink2); font-size:14px; }
blockquote { margin:0; padding:0 0 0 14px; border-left:3px solid var(--axis); color:var(--ink2); white-space:pre-wrap; }
ul { margin:0; padding-left:20px; } li { margin-bottom:6px; }
"""

JS = """
(function () {
  var data = JSON.parse(document.getElementById('line-data').textContent);
  var wrap = document.getElementById('line-wrap'), svg = document.getElementById('line-chart');
  var tip = document.getElementById('line-tip'), cross = document.getElementById('crosshair');
  function row(cls, value, name) {
    var d = document.createElement('div'); d.className = 'row';
    var k = document.createElement('span'); k.className = 'key'; k.style.borderColor = 'var(--' + cls + ')';
    var b = document.createElement('b'); b.textContent = value + ' ';
    d.appendChild(k); d.appendChild(b); d.appendChild(document.createTextNode(name)); return d;
  }
  function show(rect) {
    var p = data[+rect.dataset.i], x = +rect.dataset.x;
    cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.setAttribute('visibility', 'visible');
    tip.textContent = '';
    var h = document.createElement('div'); h.textContent = p.name; tip.appendChild(h);
    tip.appendChild(row('account', p.accountText + ' (' + p.accountValue + ')', 'Account'));
    tip.appendChild(row('spy', p.spyText, 'SPY'));
    tip.style.display = 'block';
    var box = svg.getBoundingClientRect(), scale = box.width / 720, left = x * scale + 12;
    if (left + tip.offsetWidth > box.width) left = x * scale - tip.offsetWidth - 12;
    tip.style.left = Math.max(0, left) + 'px'; tip.style.top = '8px';
  }
  function hide() { tip.style.display = 'none'; cross.setAttribute('visibility', 'hidden'); }
  svg.querySelectorAll('.hit').forEach(function (r) {
    r.addEventListener('pointermove', function () { show(r); });
    r.addEventListener('focus', function () { show(r); });
    r.addEventListener('blur', hide);
  });
  svg.addEventListener('pointerleave', hide);

  var bwrap = document.getElementById('bar-wrap'), btip = document.getElementById('bar-tip');
  if (bwrap) bwrap.querySelectorAll('.bar').forEach(function (b) {
    function on() {
      btip.textContent = b.dataset.tip; btip.style.display = 'block';
      var w = bwrap.getBoundingClientRect(), r = b.getBoundingClientRect();
      var left = r.left - w.left + r.width / 2 - btip.offsetWidth / 2;
      btip.style.left = Math.max(0, Math.min(left, w.width - btip.offsetWidth)) + 'px';
      btip.style.top = Math.max(0, r.top - w.top - btip.offsetHeight - 8) + 'px';
    }
    function off() { btip.style.display = 'none'; }
    b.addEventListener('pointermove', on); b.addEventListener('focus', on);
    b.addEventListener('pointerleave', off); b.addEventListener('blur', off);
  });
})();
"""

EXIT_WORDS = {"stop": "stop loss", "trail": "trailing stop", "be": "back to break-even", "flip": "trend reversed",
              "time": "close to expiry", "earn": "before earnings", "half": "half sold at double",
              "exp": "expiry day", "flat": "closed out", "writeoff": "closed outside the bot", "expired": "expired"}


def tile(label, value, detail="", cls=""):
    return (f'<div class="tile"><div class="k">{esc(label)}</div><div class="v">{esc(value)}</div>'
            f'<div class="d {cls}">{esc(detail)}</div></div>')


def build():
    rows = daily_rows()
    if not rows:
        raise SystemExit("No daily record in STRATEGY_LOG.md yet.")
    last = rows[-1]
    points = [{"name": "Start", "account": 0.0, "spy": 0.0, "value": START_VALUE}] + [
        {"name": short(r["date"]) + ("" if r["final"] else "*"),
         "account": (r["account"] / START_VALUE - 1) * 100, "spy": r["spy"], "value": r["account"]}
        for r in rows
    ]
    acct, spy = points[-1]["account"], points[-1]["spy"]
    lead = acct - spy
    trades = read_csv("trades.csv")
    closed = []
    for t in trades:
        if t["status"] == "closed":
            words = " then ".join(EXIT_WORDS.get(x, x) for x in t["exit"].split("+")) or "not recorded"
            closed.append(dict(t, profit=float(t["profit"]), exit_words=words))
    wins = sum(t["profit"] > 0 for t in closed)
    arrow = lambda v: "▲" if v >= 0 else "▼"

    tiles = "".join([
        tile("Whole account", f"${last['account']:,.0f}", f"{arrow(acct)} {pct(acct)} since the start", "up" if acct >= 0 else "down"),
        tile("SPY, the benchmark", pct(spy), "since the contest began"),
        tile("Lead over SPY", f"{'+' if lead >= 0 else '−'}{abs(lead):.1f} pts",
             f"{arrow(lead)} {'ahead of' if lead >= 0 else 'behind'} the professor", "up" if lead >= 0 else "down"),
        tile("The bot's profit", dollars(last["profit"]), f"on a sleeve now worth ${last['sleeve']:,.0f}"),
        tile("Closed trades", f"{wins} of {len(closed)}", "made money"),
    ])

    line_data = [{"name": p["name"], "accountText": pct(p["account"]), "accountValue": f"${p['value']:,.0f}",
                  "spyText": pct(p["spy"])} for p in points]
    line_table = "".join(
        f"<tr><td>{esc(p['name'])}</td><td class='n'>${p['value']:,.0f}</td><td class='n'>{pct(p['account'])}</td>"
        f"<td class='n'>{pct(p['spy'])}</td></tr>" for p in points)
    prelim = "" if last["final"] else (
        '<p class="small">* The latest day uses prices from when the page was built. It is replaced '
        "with Alpaca's official close afterwards.</p>")

    bars = ""
    if closed:
        trade_rows = "".join(
            f"<tr><td>#{esc(t['id'])}</td><td>{esc(t['underlying'])} {esc(t['direction'])}</td>"
            f"<td>{esc(t['opened'][:10])}</td><td>{esc(t['regime'] or 'n/a')}</td><td>{esc(t['exit_words'])}</td>"
            f"<td class='n'>{dollars(t['profit'])}</td><td class='n'>{float(t['profit_pct']):+.0f}%</td></tr>"
            for t in closed)
        bars = f"""
<section class="card">
  <h2>Every closed trade</h2>
  <p class="sub">Profit or loss in dollars, in the order the trades were opened. A few large winners carry the result.</p>
  <div class="legend"><span><span class="sw" style="background:var(--gain)"></span>Made money (above the line)</span>
    <span><span class="sw" style="background:var(--loss)"></span>Lost money (below the line)</span></div>
  <div class="chartwrap" id="bar-wrap">{bar_chart(closed)}<div class="tip" id="bar-tip"></div></div>
  <details><summary>Show the numbers</summary><div class="scroll"><table>
    <tr><th>Trade</th><th>Bet</th><th>Opened</th><th>Market mood</th><th>Why it was sold</th><th class="n">Result</th><th class="n">Return</th></tr>
    {trade_rows}</table></div></details>
</section>"""

    flags = [re.sub(r"\*\*", "", f[2:]) for f in section(MEMORY / "REVIEW.md", "Things to look at first").splitlines()
             if f.startswith("- ")]
    flags_html = "".join(f"<li>{esc(f)}</li>" for f in flags) or "<li>Nothing flagged.</li>"
    holding = "".join(f"<li>{esc(h.strip())}</li>" for h in last["holding"].split(",") if h.strip()) or "<li>Nothing.</li>"

    diary_html = ""
    diary = MEMORY / "DIARY.md"
    if diary.exists():
        entries = re.split(r"(?m)^## ", diary.read_text())[1:]
        if entries:
            head, _, body = entries[-1].partition("\n")
            title = re.sub(r"^# ", "", diary.read_text().splitlines()[0])
            diary_html = f"""
<section class="card">
  <h2>{esc(title)}: {esc(head.strip())}</h2>
  <p class="sub">Written by a local AI model playing the bot's trader persona. The numbers are checked against the bot's records; the opinions are in character.</p>
  <blockquote>{esc(body.strip())}</blockquote>
</section>"""

    built = dt.datetime.now().strftime("%b %-d, %Y at %-I:%M %p")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Options bot dashboard</title><style>{CSS}</style></head><body><main>
<h1>Options bot: how we stand against SPY</h1>
<p class="sub">A class project on practice money. The goal is to finish ahead of a portfolio that simply holds SPY.
As of {esc(last['label'])}.</p>
<div class="tiles">{tiles}</div>

<section class="card">
  <h2>The account against SPY</h2>
  <p class="sub">Percent change since the start, on one scale. The account started at $100,000.</p>
  <div class="legend"><span><span class="key" style="border-color:var(--account)"></span>Account</span>
    <span><span class="key" style="border-color:var(--spy)"></span>SPY</span></div>
  <div class="chartwrap" id="line-wrap">{line_chart(points)}<div class="tip" id="line-tip"></div></div>
  {prelim}
  <details><summary>Show the numbers</summary><div class="scroll"><table>
    <tr><th>Day</th><th class="n">Account</th><th class="n">Account change</th><th class="n">SPY change</th></tr>
    {line_table}</table></div></details>
</section>
{bars}
<section class="card">
  <h2>What the bot holds now</h2>
  <p class="sub">"P" is a put, a bet that the price falls. "C" is a call, a bet that it rises. The percentage is the result so far.</p>
  <ul>{holding}</ul>
</section>

<section class="card">
  <h2>Things to look at first</h2>
  <p class="sub">Warnings from the bot's rule-based review.</p>
  <ul>{flags_html}</ul>
</section>
{diary_html}
<p class="small">Built {esc(built)} from the project's own records by <code>python3 dashboard.py</code>.
Full history: STRATEGY_LOG.md and the memory folder.</p>
</main>
<script type="application/json" id="line-data">{json.dumps(line_data)}</script>
<script>{JS}</script></body></html>
"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page)
    print(f"dashboard written: {OUT.relative_to(ROOT)} ({len(rows)} days, {len(closed)} closed trades)")


if __name__ == "__main__":
    build()
