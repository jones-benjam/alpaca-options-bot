# Review of the bot's trades

Generated Wed Nov 18, 2026, 9:37 PM ET (market closed) by `python3 bot.py memory`. Do not edit by hand; it is rewritten every day.
This report is produced by fixed rules, not by an AI model. It describes what happened; it does not predict anything.

## Scoreboard

- **Sleeve:** $106,198 on $50,000 of capital (+$56,198).
- **Closed trades:** 12, of which 5 made money (42%).
- **Banked profit or loss:** +$30,735.
- **Typical winner and loser:** +$5,558 against -$1,615.
- **Best and worst:** #1 NVDA +$8,460, #19 AMD -$5,595.
- **Market mood now:** bear.

## Things to look at first

- **One-way book:** all 8 open bets are puts. A sharp move the other way would hit every one of them together.
- **Short of real cash:** the shared account has $11,229 in cash, less than one full-size bet ($21,240). New bets will be smaller or skipped.

## Open bets

| Bet | Paid | Now | Result so far |
|---|---|---|---|
| 4 PLTR 11/27 172.5P | $8.65 | $16.75 | +94% |
| 4 COIN 11/27 140P | $9.40 | $29.02 | +209% |
| 3 MSTR 12/04 125P | $10.90 | $35.55 | +226% |
| 2 MSFT 12/04 540P | $20.00 | $34.78 | +74% |
| 23 NFLX 12/04 63P | $1.96 | $3.72 | +90% |
| 6 QQQ 12/04 673P | $17.37 | $23.13 | +33% |
| 15 GOOGL 12/11 280P | $10.75 | $8.74 | -19% |
| 5 META 12/11 625P | $30.00 | $29.06 | -3% |

## Where the profit and loss came from

Closed trades only. With this few trades these tables show what happened, not what works.

### By kind of bet

| | Trades | Won | Profit |
|---|---|---|---|
| same-day bet | 8 | 4 of 8 | +$15,236 |
| three-week bet | 4 | 1 of 4 | +$1,247 |

### By direction

| | Trades | Won | Profit |
|---|---|---|---|
| puts (bets on a fall) | 7 | 3 of 7 | +$10,928 |
| calls (bets on a rise) | 5 | 2 of 5 | +$5,555 |

### By the market's mood when the bet was placed

| | Trades | Won | Profit |
|---|---|---|---|
| falling | 9 | 3 of 9 | +$9,308 |
| mixed | 3 | 2 of 3 | +$7,175 |

### By the reason it was sold

| | Trades | Won | Profit |
|---|---|---|---|
| took profit on half, then trailing stop | 5 | 5 of 5 | +$27,791 |
| breakeven stop | 2 | 0 of 2 | -$225 |
| stop loss | 3 | 0 of 3 | -$3,920 |
| trend flipped | 2 | 0 of 2 | -$7,163 |

## The trader's own picks, scored against the rules

Neither set is traded. Each pick is judged on what the stock did afterwards, in the direction of the pick. With only a handful of picks this is a scoreboard, not proof of skill.

| | Picks scored | Right after 1 day | Average 1-day move | Average 5-day move |
|---|---|---|---|---|
| The rules' top three | 9 | 9 of 9 | +4.65% | too early |

## Where the rest of the memory lives

- `memory/trades.csv`: every trade, one row each.
- `memory/market.csv`: the market's mood and strongest signals, one row a day.
- `memory/LESSONS.md`: what the team has learned so far, written by hand.
- `memory/candidates.csv`, `memory/news.csv`: each day's signals and headlines.
- `memory/DIARY.md`, `memory/TRADER_NOTES.md`, `memory/shadow_picks.csv`: written by the trader persona, a local AI model (see `trader.py`).
- `STRATEGY_LOG.md`: every rule change with its date and reason, and the daily record.
