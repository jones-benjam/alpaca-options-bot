# Review of the bot's trades

Generated Sat Nov 14, 2026, 1:33 PM ET (market closed) by `python3 bot.py memory`. Do not edit by hand; it is rewritten every day.
This report is produced by fixed rules, not by an AI model. It describes what happened; it does not predict anything.

## Scoreboard

- **Sleeve:** $75,497 on $50,000 of capital (+$25,497).
- **Closed trades:** 8, of which 4 made money (50%).
- **Banked profit or loss:** +$16,423.
- **Typical winner and loser:** +$4,915 against -$810.
- **Best and worst:** #1 NVDA +$8,460, #7 NFLX -$1,568.
- **Market mood now:** bear.

## Things to look at first

- **Bets against the market's mood:** #4 SPY call (2026-11-10), #5 QQQ call (2026-11-10). The rules have blocked these for same-day bets since Nov 11; any after that date would be a bug.
- **One-way book:** all 5 open bets are puts. A sharp move the other way would hit every one of them together.

## Open bets

| Bet | Paid | Now | Result so far |
|---|---|---|---|
| 8 PLTR 11/27 172.5P | $8.65 | $9.03 | +4% |
| 7 COIN 11/27 140P | $9.40 | $14.81 | +58% |
| 6 MSTR 12/04 125P | $10.90 | $16.23 | +49% |
| 3 MSFT 12/04 540P | $20.00 | $22.49 | +12% |
| 46 NFLX 12/04 63P | $1.96 | $2.19 | +11% |

## Where the profit and loss came from

Closed trades only. With this few trades these tables show what happened, not what works.

### By kind of bet

| | Trades | Won | Profit |
|---|---|---|---|
| same-day bet | 5 | 3 of 5 | +$9,581 |
| three-week bet | 3 | 1 of 3 | +$6,842 |

### By direction

| | Trades | Won | Profit |
|---|---|---|---|
| puts (bets on a fall) | 3 | 2 of 3 | +$10,868 |
| calls (bets on a rise) | 5 | 2 of 5 | +$5,555 |

### By the market's mood when the bet was placed

| | Trades | Won | Profit |
|---|---|---|---|
| falling | 5 | 2 of 5 | +$9,248 |
| mixed | 3 | 2 of 3 | +$7,175 |

### By the reason it was sold

| | Trades | Won | Profit |
|---|---|---|---|
| took profit on half, then trailing stop | 4 | 4 of 4 | +$19,661 |
| breakeven stop | 1 | 0 of 1 | -$50 |
| trend flipped | 1 | 0 of 1 | -$1,568 |
| stop loss | 2 | 0 of 2 | -$1,620 |

## The trader's own picks, scored against the rules

Neither set is traded. Each pick is judged on what the stock did afterwards, in the direction of the pick. With only a handful of picks this is a scoreboard, not proof of skill.

No pick is old enough to score yet.

## Where the rest of the memory lives

- `memory/trades.csv`: every trade, one row each.
- `memory/market.csv`: the market's mood and strongest signals, one row a day.
- `memory/LESSONS.md`: what the team has learned so far, written by hand.
- `memory/candidates.csv`, `memory/news.csv`: each day's signals and headlines.
- `memory/DIARY.md`, `memory/TRADER_NOTES.md`, `memory/shadow_picks.csv`: written by the trader persona, a local AI model (see `trader.py`).
- `STRATEGY_LOG.md`: every rule change with its date and reason, and the daily record.
