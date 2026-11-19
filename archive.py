"""The daily market archive: raw material for Dionysus's strategy lab.

Once each trading day, about half an hour before the close, this saves what
cannot be fetched again later:

  - option chains for every stock Midas watches (bid, ask, last price, implied
    volatility and greeks for contracts up to 45 days out, near the money);
  - each stock's price and day so far;
  - Midas's own live view (signals, regime, positions, lead lock), from the
    dashboard;
  - the settings Midas trades with that day, including Dionysus's changes.

Daily stock prices and option trade bars can be downloaded again at any time;
quotes, implied volatility and greeks for a whole chain cannot, and neither
can Midas's view of the day. Files go to archive/YYYY/YYYY-MM-DD.json.gz.

    python3 archive.py           # saves today's file if the close is near (desk.sh calls this)
    python3 archive.py --late    # saves the last trading day's file if it is missing (nightly.sh)
    python3 archive.py --force   # saves now, whatever the time
    python3 archive.py --show DAY   # summarises a saved day

Needs the Alpaca paper keys (.env). It only reads market data; it never trades.
"""
import datetime as dt
import gzip
import json
import os
import sys
import urllib.request
from pathlib import Path

import config as C

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "archive"
DAYS_OUT = 45          # contract expiries kept
STRIKE_BAND = 0.10     # strikes within 10% of the price ...
INDEX_BAND = 0.05      # ... 5% for the index funds, whose strikes are dense
NEAR_CLOSE_MIN = 40    # the 30-minute desk run before the close falls inside this
COLS = ["expiry", "type", "strike", "bid", "ask", "last", "iv", "delta", "gamma", "theta", "vega"]


def path_for(day):
    return ARCHIVE / day[:4] / f"{day}.json.gz"


def load(day):
    """One saved day as a dict; each chain's rows become dicts keyed by COLS."""
    with gzip.open(path_for(day), "rt") as f:
        data = json.load(f)
    for chain in data.get("chains", {}).values():
        chain["rows"] = [dict(zip(chain["cols"], r)) for r in chain["rows"]]
    return data


def r(x, n=4):
    return None if x is None else round(float(x), n)


def chain_rows(api, und, spot, today):
    from bot import parse_occ

    band = INDEX_BAND if und in C.PENNY_ALL else STRIKE_BAND
    rows = []
    for kind in ("call", "put"):
        snaps = api.option_chain(
            und, type=kind,
            expiration_date_gte=today.isoformat(),
            expiration_date_lte=(today + dt.timedelta(days=DAYS_OUT)).isoformat(),
            strike_price_gte=f"{spot * (1 - band):.2f}", strike_price_lte=f"{spot * (1 + band):.2f}",
        )
        for symbol, s in snaps.items():
            occ = parse_occ(symbol)
            if not occ or occ[0] != und:
                continue
            q, t, g = s.get("latestQuote") or {}, s.get("latestTrade") or {}, s.get("greeks") or {}
            rows.append([occ[1].isoformat(), occ[2][0], occ[3], r(q.get("bp"), 2), r(q.get("ap"), 2),
                         r(t.get("p"), 2), r(s.get("impliedVolatility")), r(g.get("delta")),
                         r(g.get("gamma"), 5), r(g.get("theta")), r(g.get("vega"))])
    return sorted(rows)


def midas_view():
    url = os.environ.get("LIVE_URL", "https://msbc5220-optbot.fly.dev").rstrip("/") + "/api/state"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as err:  # the archive is still worth saving without it
        return {"error": str(err)}


def settings_in_force(day):
    import trader

    names = list(C.TUNING_LIMITS) + ["CORE_TRAIL_LATE", "CORE_LATE_DAYS", "END_DATE"]
    values = {n: getattr(C, n) for n in names}
    try:
        values.update(trader.settings_now(trader.read_dials(), day))
    except Exception:
        pass
    return values


def snapshot(api, day, late, to_close):
    snaps = api.stock_snapshots(C.UNIVERSE)
    stocks, chains = {}, {}
    for und in C.UNIVERSE:
        s = snaps.get(und) or {}
        bar, prev = s.get("dailyBar") or {}, s.get("prevDailyBar") or {}
        price = (s.get("latestTrade") or {}).get("p") or bar.get("c")
        stocks[und] = {"price": r(price, 2), "open": r(bar.get("o"), 2), "high": r(bar.get("h"), 2),
                       "low": r(bar.get("l"), 2), "close": r(bar.get("c"), 2), "volume": bar.get("v"),
                       "prev_close": r(prev.get("c"), 2)}
        if price:
            try:
                chains[und] = {"spot": r(price, 2), "cols": COLS,
                               "rows": chain_rows(api, und, float(price), dt.date.fromisoformat(day))}
            except Exception as err:
                chains[und] = {"spot": r(price, 2), "cols": COLS, "rows": [], "error": str(err)}
    return {
        "date": day,
        "taken_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "late": late,            # True: taken after the close, so quotes are the last of the day
        "minutes_to_close": None if to_close is None else round(to_close),
        "settings": settings_in_force(day),
        "midas": midas_view(),
        "stocks": stocks,
        "chains": chains,
    }


def save(data):
    out = path_for(data["date"])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as f:
        json.dump(data, f, separators=(",", ":"))
    tmp.replace(out)
    n = sum(len(c["rows"]) for c in data["chains"].values())
    print(f"Archived {data['date']}{' (after the close)' if data['late'] else ''}: "
          f"{len(data['stocks'])} stocks, {n} option contracts, {out.stat().st_size / 1024:.0f} KB -> archive/{out.parent.name}/{out.name}")
    return out


def last_trading_day(api):
    """The date of SPY's latest daily bar: today once the market has opened."""
    bar = (api.stock_snapshots(["SPY"]).get("SPY") or {}).get("dailyBar") or {}
    return str(bar.get("t", ""))[:10] or None


def run(mode, api=None):
    if api is None:
        from alpaca import Alpaca

        api = Alpaca()
    clock = api.clock()
    now = dt.datetime.now(dt.timezone.utc)
    if clock.get("is_open"):
        from bot import parse_ts

        close = parse_ts(clock["next_close"])
        to_close = (close - now).total_seconds() / 60
        day = str(clock["timestamp"])[:10]
        if mode == "late" or (mode == "near" and to_close > NEAR_CLOSE_MIN):
            return None  # the late run only fills a day the near-close run missed
        if path_for(day).exists() and mode != "force":
            return None
        return save(snapshot(api, day, False, to_close))
    if mode == "near":
        return None
    day = last_trading_day(api)
    if not day or (path_for(day).exists() and mode != "force"):
        return None
    return save(snapshot(api, day, True, None))


def show(day):
    d = load(day)
    print(f"{d['date']} taken {d['taken_at']}{' (late)' if d['late'] else ''}, "
          f"{d['minutes_to_close']} min before the close")
    print("settings:", ", ".join(f"{k}={v}" for k, v in d["settings"].items()))
    for und, c in d["chains"].items():
        exps = sorted({x["expiry"] for x in c["rows"]})
        print(f"  {und:5} spot {c['spot']:>9}  {len(c['rows']):4} contracts, {len(exps)} expiries"
              + (f"  ERROR {c['error']}" if c.get("error") else ""))
    m = d.get("midas") or {}
    print("midas view:", "error " + m["error"] if "error" in m else f"regime {m.get('regime')}, "
          f"{len(m.get('signals') or [])} signals, {len(m.get('positions') or [])} positions")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--show":
        show(sys.argv[2])
    else:
        run({"--late": "late", "--force": "force"}.get(arg, "near"))
