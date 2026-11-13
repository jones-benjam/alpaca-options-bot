"""The bot's memory: what it traded, why, and how each trade turned out.

    python3 bot.py memory

Nothing here costs money or needs a database. Each order's id carries the
reason it was placed, so the full history can be rebuilt from Alpaca at any
time. This module turns that history into three files in memory/:

  trades.csv   one row per trade: the market's mood and the signal strength at
               entry, why it was sold, how long it was held, profit or loss
  market.csv   one row per trading day: the regime and the strongest signals
  REVIEW.md    a plain-English review: what is working, what is not, and
               anything that looks like a rule being broken

REVIEW.md is written by fixed rules, not by an AI model. It is also the
packet a human reviewer (or, later, an LLM) would read to suggest changes.
memory/LESSONS.md is written by hand and is never touched by this code.
"""
import csv
import datetime as dt
import statistics
from pathlib import Path

import config as C
from bot import earnings_days, parse_occ, read_quote

DIR = Path(__file__).with_name("memory")
TRADES, MARKET, REVIEW = DIR / "trades.csv", DIR / "market.csv", DIR / "REVIEW.md"
CANDIDATES, NEWS = DIR / "candidates.csv", DIR / "news.csv"
PICKS, SCORES = DIR / "shadow_picks.csv", DIR / "shadow_scores.csv"

EXIT_WORDS = {
    "stop": "stop loss", "trail": "trailing stop", "be": "breakeven stop",
    "flip": "trend flipped", "time": "time stop", "earn": "sold before earnings",
    "half": "took profit on half", "exp": "expiry-day exit", "flat": "flattened",
    "writeoff": "closed outside the bot", "expired": "expired", "other": "other",
    "": "not recorded",
}
ENGINES = {"core": "three-week bet", "odte": "same-day bet"}
TRADE_FIELDS = ["id", "engine", "underlying", "direction", "contract", "opened", "regime",
                "signal_pct", "qty", "entry_price", "cost", "closed", "exit", "proceeds",
                "profit", "profit_pct", "days_held", "status"]
MARKET_FIELDS = ["date", "as_of", "regime", "spy", "spy_vs_avg_pct", "qqq", "qqq_vs_avg_pct",
                 "strongest_signals"]
CANDIDATE_FIELDS = ["date", "rank", "symbol", "direction", "strength_pct", "price"]
NEWS_FIELDS = ["time", "symbols", "headline", "source"]
SCORE_FIELDS = ["date", "who", "symbol", "direction", "move_1d_pct", "move_3d_pct", "move_5d_pct"]
HORIZONS = (1, 3, 5)


def build_trades(led, tz):
    """Group the bot's fills into trades: first buy of a contract to its last sale."""
    done, live = [], {}
    for e in led.events:
        symbol = e["symbol"]
        t = live.get(symbol)
        if e["side"] == "buy":
            if t is None:
                und, _, kind, _ = parse_occ(symbol)
                bits = e["meta"].split("_")
                known = len(bits) == 3 and bits[0] == "e"
                t = live[symbol] = {
                    "id": len(done) + len(live) + 1, "engine": e["tag"], "underlying": und,
                    "direction": kind, "contract": symbol, "at": e["when"],
                    "regime": bits[1] if known else "", "signal_pct": int(bits[2]) / 100 if known else "",
                    "qty": 0, "cost": 0.0, "left": 0, "proceeds": 0.0, "exits": [], "end": None,
                }
            t["qty"] += e["qty"]
            t["left"] += e["qty"]
            t["cost"] += e["qty"] * e["px"] * 100
        elif t is not None:
            t["left"] -= e["qty"]
            t["proceeds"] += e["qty"] * e["px"] * 100
            code = e["meta"][2:] if e["meta"].startswith("x_") else ""
            if code not in t["exits"]:
                t["exits"].append(code)
            t["end"] = e["when"]
            if t["left"] <= 0:
                done.append(live.pop(symbol))
    rows = []
    for t in sorted(done + list(live.values()), key=lambda t: t["at"]):
        closed = t["left"] <= 0
        sold_cost = t["cost"] * (t["qty"] - t["left"]) / t["qty"]
        profit = t["proceeds"] - sold_cost
        rows.append({
            "id": t["id"], "engine": t["engine"], "underlying": t["underlying"],
            "direction": t["direction"], "contract": t["contract"],
            "opened": t["at"].astimezone(tz).strftime("%Y-%m-%d %H:%M"),
            "regime": t["regime"], "signal_pct": t["signal_pct"], "qty": t["qty"],
            "entry_price": round(t["cost"] / t["qty"] / 100, 2), "cost": round(t["cost"], 2),
            "closed": t["end"].astimezone(tz).strftime("%Y-%m-%d %H:%M") if closed else "",
            "exit": "+".join(t["exits"]),
            "proceeds": round(t["proceeds"], 2),
            "profit": round(profit, 2) if t["proceeds"] or closed else "",
            "profit_pct": round(profit / sold_cost * 100, 1) if sold_cost else "",
            "days_held": round((t["end"] - t["at"]).total_seconds() / 86400, 2) if closed else "",
            "status": "closed" if closed else "open",
        })
    for i, row in enumerate(rows, 1):
        row["id"] = i
    return rows


def write_csv(path, fields, rows):
    DIR.mkdir(exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def market_row(bot, now, is_open):
    view, regime = bot.market_view(now)
    snap = bot.api.stock_snapshots(["SPY"])["SPY"]
    top = "; ".join(f"{s} {k} {x:.1%}" for x, s, k in bot.candidates(view, regime)[:5])
    gap = lambda s: round((view[s]["px"] / view[s]["ema20"] - 1) * 100, 2) if s in view else ""
    return {
        "date": snap["dailyBar"]["t"][:10],
        "as_of": now.strftime("%H:%M ET") if is_open else "close",
        "regime": regime,
        "spy": round(view["SPY"]["px"], 2) if "SPY" in view else "", "spy_vs_avg_pct": gap("SPY"),
        "qqq": round(view["QQQ"]["px"], 2) if "QQQ" in view else "", "qqq_vs_avg_pct": gap("QQQ"),
        "strongest_signals": top or "none",
    }, view, regime, bot.candidates(view, regime)


def upsert_market(row):
    rows = []
    if MARKET.exists():
        with MARKET.open() as f:
            rows = [r for r in csv.DictReader(f) if r["date"] != row["date"]]
    rows.append(row)
    rows.sort(key=lambda r: r["date"])
    write_csv(MARKET, MARKET_FIELDS, rows)


def upsert_by_date(path, fields, day, new_rows):
    """Replace one day's rows in a CSV that keeps a row (or several) per day."""
    rows = []
    if path.exists():
        with path.open() as f:
            rows = [r for r in csv.DictReader(f) if r["date"] != day]
    rows += new_rows
    rows.sort(key=lambda r: (r["date"], int(r.get("rank") or 0)))
    write_csv(path, fields, rows)


def write_candidates(day, view, ranked):
    """Every signal the rules saw that day, strongest first. The trader persona
    chooses his own picks from this list, and both sets are scored later."""
    upsert_by_date(CANDIDATES, CANDIDATE_FIELDS, day, [
        {"date": day, "rank": i, "symbol": sym, "direction": kind,
         "strength_pct": round(strength * 100, 2), "price": round(view[sym]["px"], 2)}
        for i, (strength, sym, kind) in enumerate(ranked, 1)
    ])


def write_news(bot, now):
    """The last day's headlines for the bot's stocks. Only the headline is kept,
    and the file is replaced each day; it is context for the reviewer, not a signal."""
    since = (now - dt.timedelta(hours=24)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        items = bot.api.news(C.UNIVERSE, since)
    except Exception as err:  # news is optional; never let it break the daily job
        print(f"news skipped: {err}")
        return 0
    universe, rows, seen = set(C.UNIVERSE), [], set()
    for n in items:
        syms = [x for x in n.get("symbols", []) if x in universe]
        headline = "".join(ch for ch in (n.get("headline") or "") if ch.isprintable()).strip()[:160]
        if not syms or not headline or headline in seen:
            continue
        seen.add(headline)
        when = dt.datetime.fromisoformat(n["created_at"].replace("Z", "+00:00")).astimezone(now.tzinfo)
        rows.append({"time": when.strftime("%Y-%m-%d %H:%M"), "symbols": " ".join(syms[:4]),
                     "headline": headline, "source": n.get("source", "")})
        if len(rows) >= 20:
            break
    write_csv(NEWS, NEWS_FIELDS, rows)
    return len(rows)


def score_shadow(bot):
    """Score the trader persona's picks against the rules' own top picks.

    Neither set is traded. A pick is judged on what the STOCK did over the next
    1, 3 and 5 trading days, in the direction of the pick. Only days after a
    pick was made are used, so the model cannot be flattered by anything it
    might have memorised about the past."""
    picks = []
    if PICKS.exists():
        with PICKS.open() as f:
            picks = [dict(r, who="trader") for r in csv.DictReader(f)]
    if CANDIDATES.exists():
        with CANDIDATES.open() as f:
            picks += [dict(r, who="rules") for r in csv.DictReader(f) if int(r["rank"]) <= 3]
    if not picks:
        return []
    start = min(p["date"] for p in picks)
    bars = bot.api.daily_bars(sorted({p["symbol"] for p in picks}), start)
    closes = {s: {b["t"][:10]: b["c"] for b in bs} for s, bs in bars.items()}
    rows = []
    for p in picks:
        series = closes.get(p["symbol"], {})
        days = sorted(series)
        if p["date"] not in series:
            continue
        i, sign = days.index(p["date"]), 1 if p["direction"] == "call" else -1
        row = {"date": p["date"], "who": p["who"], "symbol": p["symbol"], "direction": p["direction"]}
        for h in HORIZONS:
            later = days[i + h] if i + h < len(days) else None
            row[f"move_{h}d_pct"] = round(sign * (series[later] / series[p["date"]] - 1) * 100, 2) if later else ""
        rows.append(row)
    rows.sort(key=lambda r: (r["date"], r["who"], r["symbol"]))
    write_csv(SCORES, SCORE_FIELDS, rows)
    return rows


def shadow_section(scores):
    lines = ["## The trader's own picks, scored against the rules", "",
             "Neither set is traded. Each pick is judged on what the stock did afterwards, in the "
             "direction of the pick. With only a handful of picks this is a scoreboard, not proof "
             "of skill.", ""]
    judged = [r for r in scores if r["move_1d_pct"] != ""]
    if not judged:
        return lines + ["No pick is old enough to score yet.", ""]
    lines += ["| | Picks scored | Right after 1 day | Average 1-day move | Average 5-day move |",
              "|---|---|---|---|---|"]
    for who, label in (("trader", "The trader persona"), ("rules", "The rules' top three")):
        mine = [r for r in judged if r["who"] == who]
        if not mine:
            continue
        one = [r["move_1d_pct"] for r in mine]
        five = [r["move_5d_pct"] for r in mine if r["move_5d_pct"] != ""]
        lines.append(f"| {label} | {len(mine)} | {sum(x > 0 for x in one)} of {len(one)} | "
                     f"{statistics.mean(one):+.2f}% | "
                     + (f"{statistics.mean(five):+.2f}% |" if five else "too early |"))
    return lines + [""]


def money(x):
    return f"{'+' if x >= 0 else '-'}${abs(x):,.0f}"


def breakdown(title, rows, key, names=None):
    out = [f"### {title}", "", "| | Trades | Won | Profit |", "|---|---|---|---|"]
    groups = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    for k, rs in sorted(groups.items(), key=lambda kv: -sum(r["profit"] for r in kv[1])):
        label = (names or {}).get(k, k) or "not recorded"
        won = sum(r["profit"] > 0 for r in rs)
        out.append(f"| {label} | {len(rs)} | {won} of {len(rs)} | {money(sum(r['profit'] for r in rs))} |")
    return out + [""]


def flags(trades, closed, led, bot, now, equity):
    """Plain-English warnings: things a reviewer should look at first."""
    out = []
    against = [t for t in trades if (t["regime"], t["direction"]) in (("bear", "call"), ("bull", "put"))]
    if against:
        names = ", ".join(f"#{t['id']} {t['underlying']} {t['direction']} ({t['opened'][:10]})" for t in against)
        out.append(f"**Bets against the market's mood:** {names}. The rules have blocked these for "
                   "same-day bets since Nov 11; any after that date would be a bug.")
    slipped = [t for t in closed if "stop" in t["exit"]
               and t["profit_pct"] < (C.ODTE_STOP if t["engine"] == "odte" else C.CORE_STOP) * 100 - 10]
    if slipped:
        names = ", ".join(f"#{t['id']} {t['underlying']} ({t['profit_pct']:.0f}%)" for t in slipped)
        out.append(f"**Stops that sold well past the 50% line:** {names}. The price moved through the "
                   "stop faster than the bot could sell.")
    streak = 0
    for t in reversed(closed):
        if t["profit"] >= 0:
            break
        streak += 1
    if streak >= 4:
        out.append(f"**Losing streak:** the last {streak} closed trades all lost money.")
    held = list(led.pos.values())
    if len(held) >= 4 and len({p.kind for p in held}) == 1:
        out.append(f"**One-way book:** all {len(held)} open bets are {held[0].kind}s. A sharp move the "
                   "other way would hit every one of them together.")
    soon = sorted({p.und for p in held if earnings_days(p.und, now.date()) is not None})
    if soon:
        out.append(f"**Earnings ahead:** {', '.join(soon)} reports within {C.EARNINGS_BLACKOUT_DAYS} "
                   "days. The bot will sell before the report.")
    cash = float(bot.api.account().get("cash") or 0)
    if cash < C.CORE_SLOT_PCT * equity:
        out.append(f"**Short of real cash:** the shared account has ${cash:,.0f} in cash, less than one "
                   f"full-size bet (${C.CORE_SLOT_PCT * equity:,.0f}). New bets will be smaller or skipped.")
    return out


def write_review(trades, led, bot, now, regime, is_open, scores=()):
    closed = [t for t in trades if t["status"] == "closed"]
    quotes = bot.api.option_snapshots(led.pos) if led.pos else {}
    equity, cash = bot.sleeve(led, quotes)
    wins = [t["profit"] for t in closed if t["profit"] > 0]
    losses = [t["profit"] for t in closed if t["profit"] <= 0]
    stamp = now.strftime("%a %b %-d, %Y, %-I:%M %p ET") + ("" if is_open else " (market closed)")
    lines = [
        "# Review of the bot's trades", "",
        f"Generated {stamp} by `python3 bot.py memory`. Do not edit by hand; it is rewritten every day.",
        "This report is produced by fixed rules, not by an AI model. It describes what happened; "
        "it does not predict anything.", "",
        "## Scoreboard", "",
        f"- **Sleeve:** ${equity:,.0f} on ${C.SLEEVE_START:,.0f} of capital ({money(equity - C.SLEEVE_START)}).",
        f"- **Closed trades:** {len(closed)}, of which {len(wins)} made money"
        + (f" ({len(wins) / len(closed):.0%})." if closed else "."),
        f"- **Banked profit or loss:** {money(led.realized)}.",
    ]
    if wins and losses:
        lines.append(f"- **Typical winner and loser:** {money(statistics.mean(wins))} against "
                     f"{money(statistics.mean(losses))}.")
    if closed:
        best, worst = max(closed, key=lambda t: t["profit"]), min(closed, key=lambda t: t["profit"])
        lines.append(f"- **Best and worst:** #{best['id']} {best['underlying']} {money(best['profit'])}, "
                     f"#{worst['id']} {worst['underlying']} {money(worst['profit'])}.")
    lines += [f"- **Market mood now:** {regime}.", ""]

    found = flags(trades, closed, led, bot, now, equity)
    lines += ["## Things to look at first", ""]
    lines += [f"- {f}" for f in found] or ["- Nothing flagged."]
    lines.append("")

    lines += ["## Open bets", ""]
    if led.pos:
        lines += ["| Bet | Paid | Now | Result so far |", "|---|---|---|---|"]
        for symbol, p in led.pos.items():
            q = read_quote(quotes.get(symbol))
            now_px = f"${q[2]:.2f}" if q else "no quote"
            result = f"{q[2] / p.avg - 1:+.0%}" if q else ""
            lines.append(f"| {p.qty} {p.label()} | ${p.avg:.2f} | {now_px} | {result} |")
    else:
        lines.append("None.")
    lines.append("")

    if closed:
        lines += ["## Where the profit and loss came from", "",
                  "Closed trades only. With this few trades these tables show what happened, "
                  "not what works.", ""]
        lines += breakdown("By kind of bet", closed, lambda t: t["engine"], ENGINES)
        lines += breakdown("By direction", closed, lambda t: t["direction"],
                           {"call": "calls (bets on a rise)", "put": "puts (bets on a fall)"})
        lines += breakdown("By the market's mood when the bet was placed", closed, lambda t: t["regime"],
                           {"bull": "rising", "bear": "falling", "mixed": "mixed"})
        lines += breakdown("By the reason it was sold", closed, lambda t: t["exit"],
                           {k: v for k, v in EXIT_WORDS.items()} | {
                               "half+trail": "took profit on half, then trailing stop"})
    if scores:
        lines += shadow_section(scores)
    lines += ["## Where the rest of the memory lives", "",
              "- `memory/trades.csv`: every trade, one row each.",
              "- `memory/market.csv`: the market's mood and strongest signals, one row a day.",
              "- `memory/LESSONS.md`: what the team has learned so far, written by hand.",
              "- `memory/candidates.csv`, `memory/news.csv`: each day's signals and headlines.",
              "- `memory/DIARY.md`, `memory/TRADER_NOTES.md`, `memory/shadow_picks.csv`: written by "
              "the trader persona, a local AI model (see `trader.py`).",
              "- `STRATEGY_LOG.md`: every rule change with its date and reason, and the daily record.", ""]
    REVIEW.write_text("\n".join(lines))
    return found


def update(bot):
    clock = bot.api.clock()
    now = dt.datetime.fromisoformat(__import__("re").sub(r"\.\d+", "", clock["timestamp"]).replace("Z", "+00:00"))
    led = bot.build_ledger(now)
    trades = build_trades(led, now.tzinfo)
    write_csv(TRADES, TRADE_FIELDS, trades)
    row, view, regime, ranked = market_row(bot, now, clock["is_open"])
    upsert_market(row)
    write_candidates(row["date"], view, ranked)
    headlines = write_news(bot, now)
    scores = score_shadow(bot)
    found = write_review(trades, led, bot, now, regime, clock["is_open"], scores)
    closed = sum(t["status"] == "closed" for t in trades)
    print(f"memory updated: {len(trades)} trades ({closed} closed), market row for {row['date']} "
          f"({row['regime']}), {len(ranked)} candidates, {headlines} headlines, "
          f"{len(scores)} scored picks, {len(found)} flag(s) in {REVIEW.name}")
