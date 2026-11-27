# Review of the bot's trades

Generated Thu Nov 26, 2026, 8:00 PM ET (market closed) by `python3 bot.py memory`. Do not edit by hand; it is rewritten every day.
This report is produced by fixed rules, not by an AI model. It describes what happened; it does not predict anything.

## Scoreboard

- **Sleeve:** $43,223 on $50,000 of capital (-$6,777).
- **Closed trades:** 36, of which 15 made money (42%).
- **Banked profit or loss:** -$6,777.
- **Typical winner and loser:** +$6,361 against -$4,867.
- **Best and worst:** #6 MSTR +$12,610, #32 COIN -$17,748.
- **Market mood now:** bear.

## Things to look at first

- **Bets against the market's mood:** #30 PLTR call (2026-11-23), #31 META call (2026-11-23), #32 COIN call (2026-11-23), #33 AMD call (2026-11-23), #34 AVGO call (2026-11-23), #35 QQQ call (2026-11-24). The rules have blocked these for same-day bets since Nov 11, so this looks like a bug.
- **Losing streak:** the last 12 closed trades all lost money.

## Open bets

None.

## Where the profit and loss came from

Closed trades only. With this few trades these tables show what happened, not what works.

### By kind of bet

| | Trades | Won | Profit |
|---|---|---|---|
| same-day bet | 11 | 5 of 11 | +$16,587 |
| three-week bet | 25 | 10 of 25 | -$23,364 |

### By who chose it

| | Trades | Won | Profit |
|---|---|---|---|
| the rules alone | 31 | 14 of 31 | +$6,913 |
| Dionysus's pick, approved by the rules | 5 | 1 of 5 | -$13,690 |

### By direction

| | Trades | Won | Profit |
|---|---|---|---|
| puts (bets on a fall) | 25 | 13 of 25 | +$50,339 |
| calls (bets on a rise) | 11 | 2 of 11 | -$57,116 |

### By the market's mood when the bet was placed

| | Trades | Won | Profit |
|---|---|---|---|
| mixed | 3 | 2 of 3 | +$7,175 |
| falling | 33 | 13 of 33 | -$13,952 |

### By the reason it was sold

| | Trades | Won | Profit |
|---|---|---|---|
| took profit on half, then trailing stop | 8 | 8 of 8 | +$44,181 |
| half+time | 2 | 2 of 2 | +$14,780 |
| half+fund+flat | 1 | 1 of 1 | +$12,610 |
| half+flat | 1 | 1 of 1 | +$10,649 |
| half+stop | 1 | 1 of 1 | +$7,380 |
| trailing stop | 1 | 1 of 1 | +$5,775 |
| breakeven stop | 4 | 1 of 4 | -$252 |
| trend flipped | 2 | 0 of 2 | -$7,163 |
| switched to a call | 4 | 0 of 4 | -$7,805 |
| stop loss | 6 | 0 of 6 | -$24,261 |
| flattened | 6 | 0 of 6 | -$62,671 |

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
| 2026-11-23 | QQQ call | 5/5 | Bought, trade #35: closed, -$7,579 (-69.3%) |
| 2026-11-23 | GOOGL call | 4/5 | Not bought; still a signal at the next close (slots, cash, lead-lock room or contract ran out) |
| 2026-11-24 | NVDA call | 5/5 | Not bought; the rules no longer approved it |
| 2026-11-25 | MSTR call | 5/5 | Waiting for the next trading day |

## The trader's own picks, scored against the rules

Neither set is traded. Each pick is judged on what the stock did afterwards, in the direction of the pick. With only a handful of picks this is a scoreboard, not proof of skill.

| | Picks scored | Right after 1 day | Average 1-day move | Average 5-day move |
|---|---|---|---|---|
| Dionysus (AI persona) | 9 | 3 of 9 | -1.01% | too early |
| Midas (AI persona) | 3 | 3 of 3 | +3.13% | +6.18% |
| Quill (AI persona) | 5 | 1 of 5 | -1.14% | +1.02% |
| The rules' top three | 24 | 17 of 24 | +0.60% | +11.98% |

## Where the rest of the memory lives

- `memory/trades.csv`: every trade, one row each.
- `memory/market.csv`: the market's mood and strongest signals, one row a day.
- `memory/LESSONS.md`: what the team has learned so far, written by hand.
- `memory/candidates.csv`, `memory/news.csv`: each day's signals and headlines.
- `memory/DIARY.md`, `memory/TRADER_NOTES.md`, `memory/shadow_picks.csv`: written by the trader persona, a local AI model (see `trader.py`).
- `STRATEGY_LOG.md`: every rule change with its date and reason, and the daily record.
