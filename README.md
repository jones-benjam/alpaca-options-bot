# optbot: aggressive options bot for Alpaca paper trading

Trades a $50,000 sleeve of a $100,000 Alpaca **paper** account. The goal is to
beat SPY by as much as possible over a few weeks, accepting a real chance of
losing most of the sleeve. It cannot reach a live account: the paper endpoint
is hard-coded.

**Start here: [STRATEGY_LOG.md](STRATEGY_LOG.md).** It explains the strategy
in plain English, lists every change to it with the date and reason, and has
a row for each trading day's results. A scheduled job on GitHub adds the row
automatically after each market close.

## Strategy

**Regime.** SPY and QQQ both above their 20-day EMA is a bull market (calls
only). Both below is a bear market (puts only). Otherwise mixed (both, at most
two positions per direction).

**Core engine (6 slots, 14% of the sleeve each).**
- Rank 16 liquid, high-beta names by blended momentum (60% 5-day return, 40%
  20-day return). Buy calls on the strongest names above their 10-day EMA, or
  puts on the weakest names below it. Minimum 2% momentum.
- Contract: at the money (about 0.50 delta), about 21 days to expiry.
- Exits: stop at -50% of premium. At +100% sell half, then trail the rest 30%
  below its peak. A position that was up 50% is closed if it falls back to
  entry. Close if the stock crosses its 10-day EMA near the close, or with 4
  days left to expiry.

**0DTE engine (6% of the sleeve per trade, SPY and QQQ).**
- After 10:00 ET, if price breaks the first 30 minutes' high, buy a same-day
  call slightly out of the money; below the low, a put. Only in the direction
  of the regime (no calls in a bear market, no puts in a bull market), and one
  trade a day across both symbols. Entries until 14:00.
- Exits: -50% stop, +100% sell half then 35% trail, everything closed by 15:00.
- While a 0DTE position is open the bot checks exits every 10 seconds instead
  of every 60, because same-day options can fall through a stop in seconds.

**Guard rails.**
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
