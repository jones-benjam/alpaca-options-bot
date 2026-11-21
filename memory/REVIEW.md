# Review of the bot's trades

Generated Sat Nov 21, 2026, 8:30 AM ET (market closed) by `python3 bot.py memory`. Do not edit by hand; it is rewritten every day.
This report is produced by fixed rules, not by an AI model. It describes what happened; it does not predict anything.

## Scoreboard

- **Sleeve:** $199,806 on $50,000 of capital (+$149,806).
- **Closed trades:** 16, of which 7 made money (44%).
- **Banked profit or loss:** +$43,141.
- **Typical winner and loser:** +$4,557 against -$2,373.
- **Best and worst:** #1 NVDA +$8,460, #17 GOOGL -$9,975.
- **Market mood now:** bear.

## Things to look at first

- **Stops that sold well past the 50% line:** #17 GOOGL (-62%). The price moved through the stop faster than the bot could sell.
- **One-way book:** all 9 open bets are puts. A sharp move the other way would hit every one of them together.
- **Short of real cash:** the shared account has $16,151 in cash, less than one full-size bet ($39,961). New bets will be smaller or skipped.

## Open bets

| Bet | Paid | Now | Result so far |
|---|---|---|---|
| 4 PLTR 11/27 172.5P | $8.65 | $29.94 | +246% |
| 4 COIN 11/27 140P | $9.40 | $36.48 | +288% |
| 3 MSTR 12/04 125P | $10.90 | $46.50 | +327% |
| 23 NFLX 12/04 63P | $1.96 | $6.60 | +237% |
| 3 QQQ 12/04 673P | $17.37 | $62.19 | +258% |
| 5 META 12/11 625P | $30.00 | $67.69 | +126% |
| 10 NVDA 12/11 145P | $4.95 | $21.84 | +341% |
| 3 AMD 12/11 455P | $30.05 | $56.99 | +90% |
| 16 SPY 12/11 685P | $11.78 | $17.21 | +46% |

## Where the profit and loss came from

Closed trades only. With this few trades these tables show what happened, not what works.

### By kind of bet

| | Trades | Won | Profit |
|---|---|---|---|
| same-day bet | 10 | 5 of 10 | +$16,937 |
| three-week bet | 6 | 2 of 6 | -$6,393 |

### By who chose it

| | Trades | Won | Profit |
|---|---|---|---|
| the rules alone | 16 | 7 of 16 | +$10,544 |

### By direction

| | Trades | Won | Profit |
|---|---|---|---|
| calls (bets on a rise) | 5 | 2 of 5 | +$5,555 |
| puts (bets on a fall) | 11 | 5 of 11 | +$4,989 |

### By the market's mood when the bet was placed

| | Trades | Won | Profit |
|---|---|---|---|
| mixed | 3 | 2 of 3 | +$7,175 |
| falling | 13 | 5 of 13 | +$3,369 |

### By the reason it was sold

| | Trades | Won | Profit |
|---|---|---|---|
| took profit on half, then trailing stop | 7 | 7 of 7 | +$31,899 |
| breakeven stop | 3 | 0 of 3 | -$297 |
| trend flipped | 2 | 0 of 2 | -$7,163 |
| stop loss | 4 | 0 of 4 | -$13,895 |

## What the bot did with the AI trader's suggestions

Dionysus is the AI trader; Midas is the bot and its rules.

Picks of 3/5 or more are tried first the next trading day, if the rules still approve them. 

| Picked | Suggestion | Conviction | What happened |
|---|---|---|---|
| 2026-11-18 | MSTR put | 5/5 | Not bought; still a signal at the next close (slots, cash, lead-lock room or contract ran out) |
| 2026-11-18 | COIN put | 5/5 | Not bought; still a signal at the next close (slots, cash, lead-lock room or contract ran out) |
| 2026-11-18 | NVDA put | 4/5 | Bought, trade #22: open, +$9,950 (201.0%) |
| 2026-11-19 | SPY put | 4/5 | Bought, trade #25: open, no sale yet |
| 2026-11-19 | TSLA put | 3/5 | Not bought; still a signal at the next close (slots, cash, lead-lock room or contract ran out) |
| 2026-11-19 | IWM put | 3/5 | Not bought; still a signal at the next close (slots, cash, lead-lock room or contract ran out) |
| 2026-11-20 | MSFT put | 5/5 | Waiting for the next trading day |
| 2026-11-20 | AVGO put | 4/5 | Waiting for the next trading day |
| 2026-11-20 | TSLA put | 3/5 | Waiting for the next trading day |

## The trader's own picks, scored against the rules

Neither set is traded. Each pick is judged on what the stock did afterwards, in the direction of the pick. With only a handful of picks this is a scoreboard, not proof of skill.

| | Picks scored | Right after 1 day | Average 1-day move | Average 5-day move |
|---|---|---|---|---|
| Dionysus (AI persona) | 3 | 3 of 3 | +4.63% | too early |
| Midas (AI persona) | 3 | 3 of 3 | +3.13% | too early |
| Quill (AI persona) | 1 | 1 of 1 | +3.23% | too early |
| The rules' top three | 15 | 15 of 15 | +5.41% | +24.37% |

## Where the rest of the memory lives

- `memory/trades.csv`: every trade, one row each.
- `memory/market.csv`: the market's mood and strongest signals, one row a day.
- `memory/LESSONS.md`: what the team has learned so far, written by hand.
- `memory/candidates.csv`, `memory/news.csv`: each day's signals and headlines.
- `memory/DIARY.md`, `memory/TRADER_NOTES.md`, `memory/shadow_picks.csv`: written by the trader persona, a local AI model (see `trader.py`).
- `STRATEGY_LOG.md`: every rule change with its date and reason, and the daily record.
