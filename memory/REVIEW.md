# Review of the bot's trades

Generated Thu Nov 19, 2026, 4:02 PM ET (market closed) by `python3 bot.py memory`. Do not edit by hand; it is rewritten every day.
This report is produced by fixed rules, not by an AI model. It describes what happened; it does not predict anything.

## Scoreboard

- **Sleeve:** $118,526 on $50,000 of capital (+$68,526).
- **Closed trades:** 15, of which 6 made money (40%).
- **Banked profit or loss:** +$21,158.
- **Typical winner and loser:** +$5,021 against -$2,373.
- **Best and worst:** #1 NVDA +$8,460, #17 GOOGL -$9,975.
- **Market mood now:** bear.

## Things to look at first

- **Stops that sold well past the 50% line:** #17 GOOGL (-62%). The price moved through the stop faster than the bot could sell.
- **Losing streak:** the last 4 closed trades all lost money.
- **One-way book:** all 8 open bets are puts. A sharp move the other way would hit every one of them together.
- **Short of real cash:** the shared account has $2,859 in cash, less than one full-size bet ($23,705). New bets will be smaller or skipped.

## Open bets

| Bet | Paid | Now | Result so far |
|---|---|---|---|
| 4 PLTR 11/27 172.5P | $8.65 | $19.55 | +126% |
| 4 COIN 11/27 140P | $9.40 | $31.52 | +235% |
| 3 MSTR 12/04 125P | $10.90 | $39.31 | +261% |
| 23 NFLX 12/04 63P | $1.96 | $4.80 | +145% |
| 6 QQQ 12/04 673P | $17.37 | $35.09 | +102% |
| 5 META 12/11 625P | $30.00 | $41.29 | +38% |
| 20 NVDA 12/11 145P | $4.95 | $7.40 | +49% |
| 3 AMD 12/11 455P | $30.05 | $23.13 | -23% |

## Where the profit and loss came from

Closed trades only. With this few trades these tables show what happened, not what works.

### By kind of bet

| | Trades | Won | Profit |
|---|---|---|---|
| same-day bet | 9 | 4 of 9 | +$15,164 |
| three-week bet | 6 | 2 of 6 | -$6,393 |

### By who chose it

| | Trades | Won | Profit |
|---|---|---|---|
| the rules alone | 15 | 6 of 15 | +$8,771 |

### By direction

| | Trades | Won | Profit |
|---|---|---|---|
| calls (bets on a rise) | 5 | 2 of 5 | +$5,555 |
| puts (bets on a fall) | 10 | 4 of 10 | +$3,216 |

### By the market's mood when the bet was placed

| | Trades | Won | Profit |
|---|---|---|---|
| mixed | 3 | 2 of 3 | +$7,175 |
| falling | 12 | 4 of 12 | +$1,596 |

### By the reason it was sold

| | Trades | Won | Profit |
|---|---|---|---|
| took profit on half, then trailing stop | 6 | 6 of 6 | +$30,126 |
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
| 2026-11-18 | NVDA put | 4/5 | Bought, trade #22: open, no sale yet |

## The trader's own picks, scored against the rules

Neither set is traded. Each pick is judged on what the stock did afterwards, in the direction of the pick. With only a handful of picks this is a scoreboard, not proof of skill.

| | Picks scored | Right after 1 day | Average 1-day move | Average 5-day move |
|---|---|---|---|---|
| Midas (AI persona) | 3 | 3 of 3 | +3.13% | too early |
| Quill (AI persona) | 1 | 1 of 1 | +3.23% | too early |
| The rules' top three | 12 | 12 of 12 | +4.27% | too early |

## Where the rest of the memory lives

- `memory/trades.csv`: every trade, one row each.
- `memory/market.csv`: the market's mood and strongest signals, one row a day.
- `memory/LESSONS.md`: what the team has learned so far, written by hand.
- `memory/candidates.csv`, `memory/news.csv`: each day's signals and headlines.
- `memory/DIARY.md`, `memory/TRADER_NOTES.md`, `memory/shadow_picks.csv`: written by the trader persona, a local AI model (see `trader.py`).
- `STRATEGY_LOG.md`: every rule change with its date and reason, and the daily record.
