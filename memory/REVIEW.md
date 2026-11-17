# Review of the bot's trades

Generated Tue Nov 17, 2026, 4:24 PM ET (market closed) by `python3 bot.py memory`. Do not edit by hand; it is rewritten every day.
This report is produced by fixed rules, not by an AI model. It describes what happened; it does not predict anything.

## Scoreboard

- **Sleeve:** $113,979 on $50,000 of capital (+$63,979).
- **Closed trades:** 10, of which 5 made money (50%).
- **Banked profit or loss:** +$38,630.
- **Typical winner and loser:** +$5,558 against -$683.
- **Best and worst:** #1 NVDA +$8,460, #7 NFLX -$1,568.
- **Market mood now:** bear.

## Things to look at first

- **Bets against the market's mood:** #4 SPY call (2026-11-10), #5 QQQ call (2026-11-10). The rules have blocked these for same-day bets since Nov 11; any after that date would be a bug.
- **One-way book:** all 9 open bets are puts. A sharp move the other way would hit every one of them together.
- **Short of real cash:** the shared account has $4,651 in cash, less than one full-size bet ($22,796). New bets will be smaller or skipped.

## Open bets

| Bet | Paid | Now | Result so far |
|---|---|---|---|
| 4 PLTR 11/27 172.5P | $8.65 | $17.55 | +103% |
| 4 COIN 11/27 140P | $9.40 | $24.00 | +155% |
| 3 MSTR 12/04 125P | $10.90 | $29.08 | +167% |
| 2 MSFT 12/04 540P | $20.00 | $38.52 | +93% |
| 23 NFLX 12/04 63P | $1.96 | $3.98 | +103% |
| 6 QQQ 12/04 673P | $17.37 | $25.49 | +47% |
| 15 GOOGL 12/11 280P | $10.75 | $10.13 | -6% |
| 5 META 12/11 625P | $30.00 | $30.55 | +2% |
| 3 AMD 12/11 505P | $48.25 | $41.31 | -14% |

## Where the profit and loss came from

Closed trades only. With this few trades these tables show what happened, not what works.

### By kind of bet

| | Trades | Won | Profit |
|---|---|---|---|
| same-day bet | 7 | 4 of 7 | +$17,536 |
| three-week bet | 3 | 1 of 3 | +$6,842 |

### By direction

| | Trades | Won | Profit |
|---|---|---|---|
| puts (bets on a fall) | 5 | 3 of 5 | +$18,823 |
| calls (bets on a rise) | 5 | 2 of 5 | +$5,555 |

### By the market's mood when the bet was placed

| | Trades | Won | Profit |
|---|---|---|---|
| falling | 7 | 3 of 7 | +$17,203 |
| mixed | 3 | 2 of 3 | +$7,175 |

### By the reason it was sold

| | Trades | Won | Profit |
|---|---|---|---|
| took profit on half, then trailing stop | 5 | 5 of 5 | +$27,791 |
| breakeven stop | 2 | 0 of 2 | -$225 |
| trend flipped | 1 | 0 of 1 | -$1,568 |
| stop loss | 2 | 0 of 2 | -$1,620 |

## The trader's own picks, scored against the rules

Neither set is traded. Each pick is judged on what the stock did afterwards, in the direction of the pick. With only a handful of picks this is a scoreboard, not proof of skill.

| | Picks scored | Right after 1 day | Average 1-day move | Average 5-day move |
|---|---|---|---|---|
| The rules' top three | 6 | 6 of 6 | +4.77% | too early |

## Where the rest of the memory lives

- `memory/trades.csv`: every trade, one row each.
- `memory/market.csv`: the market's mood and strongest signals, one row a day.
- `memory/LESSONS.md`: what the team has learned so far, written by hand.
- `memory/candidates.csv`, `memory/news.csv`: each day's signals and headlines.
- `memory/DIARY.md`, `memory/TRADER_NOTES.md`, `memory/shadow_picks.csv`: written by the trader persona, a local AI model (see `trader.py`).
- `STRATEGY_LOG.md`: every rule change with its date and reason, and the daily record.
