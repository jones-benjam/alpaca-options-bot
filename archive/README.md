# Daily market archive

One file per trading day, `YYYY/YYYY-MM-DD.json.gz`, written by `archive.py` on
the Mac mini about half an hour before the close (the desk job). If that run
is missed, the nightly job writes one after the close, marked `"late": true`.
It is raw material for Dionysus's strategy lab (ROADMAP.md, stage 2).

It keeps what cannot be downloaded again later: the quotes, implied volatility
and greeks of whole option chains, and Midas's own view of the day. Daily
stock prices and option trade bars can always be fetched again, so they are
not stored here.

| Key | What |
|---|---|
| `date`, `taken_at`, `late`, `minutes_to_close` | when it was taken |
| `settings` | Midas's settings that day, including Dionysus's changes |
| `midas` | Midas's live dashboard state: regime, signals, positions, sleeve, lead lock |
| `stocks` | each watched stock: price, open, high, low, close so far, volume, previous close |
| `chains` | per stock: `spot`, `cols`, `rows`. Contracts up to 45 days out, strikes within 10% of the price (5% for SPY, QQQ, IWM) |

Each chain row is `[expiry, type (c/p), strike, bid, ask, last, iv, delta,
gamma, theta, vega]`. Greeks come from Alpaca's free (indicative) feed.

```python
import archive
day = archive.load("2026-11-19")          # rows come back as dicts
spy = day["chains"]["SPY"]["rows"]
```

`python3 archive.py --show 2026-11-19` prints a summary. About 200 KB a day,
roughly 50 MB a year.
