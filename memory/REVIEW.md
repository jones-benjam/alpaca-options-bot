# Review of the bot's trades

Generated Wed Nov 18, 2026, 1:17 PM ET by `python3 bot.py memory`. Do not edit by hand; it is rewritten every day.
This report is produced by fixed rules, not by an AI model. It describes what happened; it does not predict anything.

## Scoreboard

- **Sleeve:** $108,523 on $50,000 of capital (+$58,523).
- **Closed trades:** 11, of which 5 made money (45%).
- **Banked profit or loss:** +$36,330.
- **Typical winner and loser:** +$5,558 against -$952.
- **Best and worst:** #1 NVDA +$8,460, #20 SPY -$2,300.
- **Market mood now:** bear.

## Things to look at first

- **Bets against the market's mood:** #4 SPY call (2026-11-10), #5 QQQ call (2026-11-10). The rules have blocked these for same-day bets since Nov 11; any after that date would be a bug.
- **One-way book:** all 9 open bets are puts. A sharp move the other way would hit every one of them together.
- **Short of real cash:** the shared account has $2,349 in cash, less than one full-size bet ($21,705). New bets will be smaller or skipped.

## Open bets

| Bet | Paid | Now | Result so far |
|---|---|---|---|
| 4 PLTR 11/27 172.5P | $8.65 | $18.20 | +110% |
| 4 COIN 11/27 140P | $9.40 | $26.68 | +184% |
| 3 MSTR 12/04 125P | $10.90 | $32.26 | +196% |
| 2 MSFT 12/04 540P | $20.00 | $39.01 | +95% |
| 23 NFLX 12/04 63P | $1.96 | $3.41 | +74% |
| 6 QQQ 12/04 673P | $17.37 | $24.13 | +39% |
| 15 GOOGL 12/11 280P | $10.75 | $9.34 | -13% |
| 5 META 12/11 625P | $30.00 | $30.29 | +1% |
| 3 AMD 12/11 505P | $48.25 | $34.36 | -29% |

## Where the profit and loss came from

Closed trades only. With this few trades these tables show what happened, not what works.

### By kind of bet

| | Trades | Won | Profit |
|---|---|---|---|
| same-day bet | 8 | 4 of 8 | +$15,236 |
| three-week bet | 3 | 1 of 3 | +$6,842 |

### By direction

| | Trades | Won | Profit |
|---|---|---|---|
| puts (bets on a fall) | 6 | 3 of 6 | +$16,523 |
| calls (bets on a rise) | 5 | 2 of 5 | +$5,555 |

### By the market's mood when the bet was placed

| | Trades | Won | Profit |
|---|---|---|---|
| falling | 8 | 3 of 8 | +$14,903 |
| mixed | 3 | 2 of 3 | +$7,175 |

### By the reason it was sold

| | Trades | Won | Profit |
|---|---|---|---|
| took profit on half, then trailing stop | 5 | 5 of 5 | +$27,791 |
| breakeven stop | 2 | 0 of 2 | -$225 |
| trend flipped | 1 | 0 of 1 | -$1,568 |
| stop loss | 3 | 0 of 3 | -$3,920 |

## The trader's own picks, scored against the rules

Neither set is traded. Each pick is judged on what the stock did afterwards, in the direction of the pick. With only a handful of picks this is a scoreboard, not proof of skill.

| | Picks scored | Right after 1 day | Average 1-day move | Average 5-day move |
|---|---|---|---|---|
| The rules' top three | 9 | 9 of 9 | +4.16% | too early |

## Where the rest of the memory lives

- `memory/trades.csv`: every trade, one row each.
- `memory/market.csv`: the market's mood and strongest signals, one row a day.
- `memory/LESSONS.md`: what the team has learned so far, written by hand.
- `memory/candidates.csv`, `memory/news.csv`: each day's signals and headlines.
- `memory/DIARY.md`, `memory/TRADER_NOTES.md`, `memory/shadow_picks.csv`: written by the trader persona, a local AI model (see `trader.py`).
- `STRATEGY_LOG.md`: every rule change with its date and reason, and the daily record.
