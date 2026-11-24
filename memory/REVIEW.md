# Review of the bot's trades

<<<<<<< Updated upstream
Generated Tue Nov 24, 2026, 12:21 AM ET (market closed) by `python3 bot.py memory`. Do not edit by hand; it is rewritten every day.
=======
Generated Mon Nov 23, 2026, 8:00 PM ET (market closed) by `python3 bot.py memory`. Do not edit by hand; it is rewritten every day.
>>>>>>> Stashed changes
This report is produced by fixed rules, not by an AI model. It describes what happened; it does not predict anything.

## Scoreboard

- **Sleeve:** $102,964 on $50,000 of capital (+$52,964).
- **Closed trades:** 27, of which 13 made money (48%).
- **Banked profit or loss:** +$39,552.
- **Typical winner and loser:** +$5,551 against -$2,798.
- **Best and worst:** #14 QQQ +$12,282, #25 SPY -$10,016.
- **Market mood now:** bear.

## Things to look at first

- **Bets against the market's mood:** #30 PLTR call (2026-11-23), #31 META call (2026-11-23), #32 COIN call (2026-11-23), #33 AMD call (2026-11-23), #34 AVGO call (2026-11-23). The rules have blocked these for same-day bets since Nov 11, so this looks like a bug.
- **Losing streak:** the last 5 closed trades all lost money.
- **Short of real cash:** the shared account has $3,418 in cash, less than one full-size bet ($20,593). New bets will be smaller or skipped.

## Open bets

| Bet | Paid | Now | Result so far |
|---|---|---|---|
| 3 MSTR 12/04 125P | $10.90 | $40.25 | +269% |
| 23 NFLX 12/04 63P | $1.96 | $5.27 | +169% |
| 16 PLTR 12/04 165C | $3.90 | $4.58 | +17% |
| 8 META 12/07 625C | $11.20 | $10.41 | -7% |
| 68 COIN 12/04 116C | $3.15 | $2.93 | -7% |
| 8 AMD 12/04 487.5C | $15.90 | $15.00 | -6% |
| 24 AVGO 12/04 330C | $8.35 | $7.82 | -6% |

## Where the profit and loss came from

Closed trades only. With this few trades these tables show what happened, not what works.

### By kind of bet

| | Trades | Won | Profit |
|---|---|---|---|
| same-day bet | 10 | 5 of 10 | +$16,937 |
| three-week bet | 17 | 8 of 17 | +$16,048 |

### By who chose it

| | Trades | Won | Profit |
|---|---|---|---|
| the rules alone | 23 | 12 of 23 | +$39,096 |
| Dionysus's pick, approved by the rules | 4 | 1 of 4 | -$6,111 |

### By direction

| | Trades | Won | Profit |
|---|---|---|---|
| puts (bets on a fall) | 22 | 11 of 22 | +$27,430 |
| calls (bets on a rise) | 5 | 2 of 5 | +$5,555 |

### By the market's mood when the bet was placed

| | Trades | Won | Profit |
|---|---|---|---|
| falling | 24 | 11 of 24 | +$25,810 |
| mixed | 3 | 2 of 3 | +$7,175 |

### By the reason it was sold

| | Trades | Won | Profit |
|---|---|---|---|
| took profit on half, then trailing stop | 8 | 8 of 8 | +$44,181 |
| half+time | 2 | 2 of 2 | +$14,780 |
| half+stop | 1 | 1 of 1 | +$7,380 |
| trailing stop | 1 | 1 of 1 | +$5,775 |
| breakeven stop | 4 | 1 of 4 | -$252 |
| trend flipped | 2 | 0 of 2 | -$7,163 |
| switched to a call | 4 | 0 of 4 | -$7,805 |
| stop loss | 5 | 0 of 5 | -$23,911 |

## What the bot did with the AI trader's suggestions

Dionysus is the AI trader; Midas is the bot and its rules.

Picks of 3/5 or more are tried first the next trading day, if the rules still approve them. 

| Picked | Suggestion | Conviction | What happened |
|---|---|---|---|
| 2026-11-18 | MSTR put | 5/5 | Not bought; still a signal at the next close (slots, cash, lead-lock room or contract ran out) |
| 2026-11-18 | COIN put | 5/5 | Not bought; still a signal at the next close (slots, cash, lead-lock room or contract ran out) |
| 2026-11-18 | NVDA put | 4/5 | Bought, trade #22: closed, +$7,380 (74.5%) |
| 2026-11-19 | SPY put | 4/5 | Bought, trade #25: closed, -$10,016 (-53.1%) |
| 2026-11-19 | TSLA put | 3/5 | Not bought; still a signal at the next close (slots, cash, lead-lock room or contract ran out) |
| 2026-11-19 | IWM put | 3/5 | Not bought; still a signal at the next close (slots, cash, lead-lock room or contract ran out) |
| 2026-11-20 | MSFT put | 5/5 | Bought, trade #26: closed, -$1,575 (-6.7%) |
| 2026-11-20 | AVGO put | 4/5 | Bought, trade #29: closed, -$1,900 (-12.2%) |
| 2026-11-20 | TSLA put | 3/5 | Not bought; the rules no longer approved it |

## The trader's own picks, scored against the rules

Neither set is traded. Each pick is judged on what the stock did afterwards, in the direction of the pick. With only a handful of picks this is a scoreboard, not proof of skill.

| | Picks scored | Right after 1 day | Average 1-day move | Average 5-day move |
|---|---|---|---|---|
| Dionysus (AI persona) | 6 | 3 of 6 | -0.33% | too early |
| Midas (AI persona) | 3 | 3 of 3 | +3.13% | too early |
| Quill (AI persona) | 2 | 1 of 2 | +0.83% | too early |
| The rules' top three | 18 | 15 of 18 | +1.92% | +15.76% |

## Where the rest of the memory lives

- `memory/trades.csv`: every trade, one row each.
- `memory/market.csv`: the market's mood and strongest signals, one row a day.
- `memory/LESSONS.md`: what the team has learned so far, written by hand.
- `memory/candidates.csv`, `memory/news.csv`: each day's signals and headlines.
- `memory/DIARY.md`, `memory/TRADER_NOTES.md`, `memory/shadow_picks.csv`: written by the trader persona, a local AI model (see `trader.py`).
- `STRATEGY_LOG.md`: every rule change with its date and reason, and the daily record.
