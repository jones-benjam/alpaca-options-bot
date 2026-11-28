# Midas: aggressive options bot for Alpaca paper trading

Trades a $50,000 sleeve of a $100,000 Alpaca **paper** account. The goal is to
beat SPY by as much as possible over a few weeks, accepting a real chance of
losing most of the sleeve. It cannot reach a live account: the paper endpoint
is hard-coded.

The bot's name is Midas. Its orders still carry the original `optbot-` tag,
because the bot rebuilds its trade history from that tag every time it starts.

**Where this is going: [ROADMAP.md](ROADMAP.md)** (Dionysus, the AI trader, earns control of Midas in stages).

**Start here: [STRATEGY_LOG.md](STRATEGY_LOG.md).** It explains the strategy
in plain English, lists every change to it with the date and reason, and has
a row for each trading day's results. A scheduled job on GitHub adds the row
automatically after each market close.

## Strategy

**Regime.** SPY and QQQ both above their 20-day EMA is a bull market (calls
only). Both below is a bear market (since Nov 23, calls on the weakest names, betting
on a rebound; `BEAR_BUY_DIPS=0` goes back to puts). Otherwise mixed (both, at most
two positions per direction).

**Core engine (up to 10 slots, 20% of the sleeve each; new bets are funded by cash from profitable sales).**
- Rank 16 liquid, high-beta names by blended momentum (60% 5-day return, 40%
  20-day return). In a bull market buy calls on the strongest names above their
  10-day EMA; in a bear market buy calls on the weakest names below it. Minimum 2% momentum.
- Contract: about 5% out of the money (about 0.35 delta), about 14 days to expiry.
- Exits: stop at -80% of premium. At +200% sell half; once a position has been
  up 125%, sell if it falls 40% below its peak. A position that was up 50% is closed if it falls back to
  entry. Close if the stock crosses its 10-day EMA near the close (dip calls are
  exempt), or with 2 days left to expiry.
- Hold or switch: in a bear market a put up less than 50% on a stock that is still
  weak is sold and replaced with a call; bigger winners run (`SWITCH_PUTS=0` turns this off).

**0DTE engine (6% of the sleeve per trade, SPY and QQQ).**
- After 10:00 ET, if price breaks the first 30 minutes' high, buy a same-day
  call slightly out of the money; below the low, a put. Only in the direction
  of the regime (no calls in a bear market, no puts in a bull market), and one
  trade a day across both symbols. Entries until 14:00.
- Exits: -50% stop, +100% sell half then 35% trail, everything closed by 15:00.
- While a 0DTE position is open the bot checks exits every 10 seconds instead
  of every 60, because same-day options can fall through a stop in seconds.

**Dionysus, the AI trader (core engine only).** Midas is the bot; Dionysus
is the local AI model that suggests trades to it.
- Each evening the trader persona on the Mac mini (`trader.py`, a local model)
  picks up to three of the day's signals with a conviction from 1 to 5, saved
  to `memory/shadow_picks.csv` on GitHub.
- The next trading day the bot tries picks of conviction 3 or more first, if
  its rules still approve them. It never buys anything the rules reject, and
  sizing, stops and guard rails are unchanged. Missing or stale picks mean the
  rules trade alone. `AI_PICKS=0` turns it off.
- If cash or the lead lock blocks a rule-approved pick rated 4 or 5, Midas may
  sell part of a winning bet Dionysus named (up 10% or more), just enough to
  fund it, once a day (`AI_FREE_UP`).
- Trades it chose carry `_ai<conviction>` in the order id. `memory/REVIEW.md`
  compares them with the rules' own trades. The persona reflects daily and, on
  Fridays, suggests rule changes in `memory/PROPOSALS.md` for a person to
  approve.

**Guard rails.**
- Lead lock (**off** from Nov 28 for the final push; `LOCK_ENABLED=1` turns it on): the whole
  account must stay at least 5 points ahead of SPY. The bot may hold options worth up to twice the account's cushion above that
  floor; a smaller cushion blocks new bets, and no cushion closes everything.
- Kill switch: if the sleeve falls to 30% of its size the bot closes
  everything and stops opening trades. (The floor is $15,000 on the $50,000 sleeve.)
- `END_DATE`: no new trades on that day, flat by 15:00 ET.
- Earnings: no new position in a stock in the five days before its earnings
  report, and a held position is sold in the last half hour before the report
  (`EARNINGS_EXIT_BY` in `config.py`; currently NVDA on Nov 17).
- Shared account: a new position is limited to the account's real cash, so
  the bot never borrows on margin when teammates have spent the rest.
- Restarts: each position's best price is rebuilt from Alpaca's price
  history, so the trailing and breakeven stops survive a redeploy.
- Bad quotes: a stop or trailing exit must show on two passes in a row, and
  the kill switch on three, before the bot sells. Quotes with no bid or an
  absurd spread are ignored for exits and for valuing the sleeve.
- Half days (for example the Friday after Thanksgiving): the time-based rules
  follow the real closing time, so 0DTE positions are closed an hour before
  an early close.
- The bot only sells contracts it bought. It recognises them by the `optbot-`
  prefix on its order ids, so teammates can trade anything else in the account.
  Teammates should leave the bot's option positions alone; if one is closed by
  hand, the bot books it at the current price and moves on.

Every dial is in `config.py` and can be overridden with an environment variable
of the same name.

## Run it

```bash
python3 check_options.py                 # confirm the account can trade options
python3 bot.py run --dry-run --once      # show what it would do, send nothing
python3 bot.py run                       # trade until stopped (Ctrl+C)
python3 bot.py status                    # sleeve P&L, positions, recent trades
python3 sim_test.py                      # offline test with a fake broker, no keys
python3 bot.py journal                   # add today's row to STRATEGY_LOG.md
python3 backtest_signal.py               # replay the rules on five years of prices
python3 bot.py memory                    # refresh the trade table and review
python3 dashboard.py                     # rebuild docs/: the live page and the daily report
python3 measure_option_cost.py --cached  # were options overpriced? (real prices)
```

### The bot's memory

Every order id records why the order was placed (`e_<regime>_<signal>` on a
buy, `x_<reason>` on a sell), so the history can always be rebuilt from Alpaca.
`python3 bot.py memory` turns it into the files in `memory/`:

- `trades.csv`: one row per trade with the regime and signal at entry, the exit
  reason, days held and profit. `signal_pct` is the momentum score for
  three-week bets and the distance past the opening range for same-day bets.
- `market.csv`: one row per trading day with the regime and strongest signals.
- `REVIEW.md`: a plain-English review written by fixed rules (no AI model, no
  cost), including flags such as a bet against the regime.
- `LESSONS.md`: what the team has learned, written by hand.

The daily GitHub job refreshes all of these and commits them.

### The trader persona (optional, runs on a Mac mini)

`trader.py` gives the bot a voice: a local AI model, run with Ollama on a Mac
mini, plays a trader character. He writes `memory/DIARY.md`, records the picks
he would make in `memory/shadow_picks.csv` (never placed, scored in
`REVIEW.md` against the rules' own top picks) and keeps
`memory/TRADER_NOTES.md`, notes to himself that are read back to him later. He
never contacts the broker and cannot change a rule. Setup:
[MAC_MINI_SETUP.md](MAC_MINI_SETUP.md). Test the plumbing anywhere, without a
model: `python3 trader.py selftest`.

Ideas borrowed from open-source projects (designs only; none of their code is
included): layered memory with a character, from
[FinMem](https://github.com/pipiku915/FinMem-LLM-StockTrading); a risk desk the
persona cannot overrule, from
[ai-hedge-fund](https://github.com/virattt/ai-hedge-fund); keeping the exact
facts behind each output, from [LLM_trader](https://github.com/qrak/LLM_trader);
scoring picks only on days after they were made, from
[agent-backtest-lab](https://github.com/bettyguo/agent-backtest-lab); and news
as an input, from [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT).

`STRATEGY_LOG.md` is the project's plain-English record: what the strategy is,
every change to it with the date and reason, and a row per trading day. Run
`journal` after each close, and add an entry under "Changes to the strategy"
whenever a rule changes.

Keys are read from `.env` (copy `.env.example`) or from the environment.
Python 3.9+; no packages to install.

## Live dashboard

**https://jones-benjam.github.io/alpaca-options-bot/** is the live dashboard,
hosted by GitHub Pages from `docs/`. It reads live data from the bot, which
also serves the same page itself at https://msbc5220-optbot.fly.dev. The daily
report is at `docs/report.html`, and the live page links to it when the bot
can't be reached. It is styled in CU Boulder colors as a retro side-scrolling game and shows the whole
account against SPY, the lead lock, every open position, a blotter of every buy
and sell (with the reason, holding time and result, filterable to wins or
losses), the win/loss record, profit by stock, engine and exit reason, and the
bot's latest log lines. Green and red mean only win and loss, and every result
also carries a WIN or LOSS label and an arrow. It refreshes itself every 15 seconds (every few minutes while the market is
closed). Page requests never call the broker; they read the snapshot the bot
makes after each pass, so the page cannot slow trading down or place an order.
The address is public, like this repository. Code: `live.py`.

## Run it in the cloud (Fly.io)

The live copy runs on Fly.io as one small always-on worker (`fly.toml`).

```bash
fly apps create msbc5220-optbot
fly secrets set ALPACA_API_KEY=... ALPACA_SECRET_KEY=... -a msbc5220-optbot
fly deploy --ha=false
fly logs -a msbc5220-optbot
```

- `--ha=false` keeps it to exactly one machine. **Only one live copy may run
  at a time**: two copies would both trade the same sleeve.
- Stop trading with `fly scale count 0 -a msbc5220-optbot`.
- The end date (`2026-12-02`) is set in `fly.toml` and `config.py`.

**Teammates:** to review or try the bot, use `python3 bot.py status` and
`python3 bot.py run --dry-run`. Do not start a second live `bot.py run` while
the Fly.io copy is running.

The bot keeps no database. On every loop it rebuilds its positions and P&L from
Alpaca's order history, so restarts and redeploys are safe.

## Known limits

- The free data plan gives approximate ("indicative") option quotes, so paper
  fills are somewhat optimistic, most of all for 0DTE trades.
- Sleeve cash is tracked by the bot, but buying power is shared with the whole
  account. If teammates use it all, the bot skips entries.
- Earnings dates are entered by hand in `config.py`; a report that is not
  listed there is not guarded against.
- Buying short-dated options loses money on average unless the momentum signal
  has an edge, and `backtest_signal.py` found none: over five years the picks
  were right about half the time, no better than random names. Results over a
  few weeks are dominated by luck and trend. See STRATEGY_LOG.md.
