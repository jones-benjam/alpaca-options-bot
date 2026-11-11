# Lessons so far

What the team has learned from running the bot, in plain English. This file
is written by hand: add a dated line when something new is learned, and note
which rule (if any) changed because of it. The details and numbers behind
each lesson are in `STRATEGY_LOG.md`.

## About the strategy

- **The stock picker is no better than chance.** Over five years its picks
  moved the right way about half the time, the same as random picks.
  (Nov 10)
- **Most bets lose; a few big winners carry the result.** About three bets
  in four lose money, and the typical loser gives up more than a third of
  what was paid. (Nov 10, confirmed with real prices Nov 11)
- **Bet size is what sinks it over time.** With most of the sleeve in bets
  that usually lose, an ordinary losing streak empties the sleeve before a
  big winner arrives. (Nov 11)
- **More leverage does not improve the odds.** It makes the rare wins bigger
  and large losses far more common. (Nov 11)
- **Having the bot react to its own recent wins and losses does not help.**
  Recent results did not predict the next ones. (Nov 11)
- **Selling options instead of buying them was steadier but still lost.**
  Neither side beat simply holding SPY. (Nov 11)
- **Options on individual stocks were fairly priced; options on index funds
  were about 9% overpriced.** Measured from 505 real bets, 2024 to 2026.
  (Nov 11)

## About running the bot

- **Do not let two parts of the bot disagree.** On Nov 10 it held bets on
  falling prices and bought same-day bets on rising prices; both of those
  lost within 22 minutes. Rule changed: same-day bets must follow the
  market's mood, one a day. (Nov 10)
- **Prices right after the close cannot be trusted.** Our first daily record
  understated the account by about $3,900. Rule changed: the record is
  marked preliminary until Alpaca's official close is in. (Nov 11)
- **Anything the bot needs to remember must survive a restart.** Updating
  the bot was silently switching off two of its selling rules. Rule changed:
  it now rebuilds what it needs from Alpaca every time it starts. (Nov 11)
- **A shared account needs a spending limit.** Once teammates invested, the
  bot could have borrowed without anyone deciding to. Rule changed: it can
  only spend cash the account really has. (Nov 11)
- **Company results are a coin flip for an option holder.** Rule changed:
  no new bet in the five days before a report, and sell before it. (Nov 10)
- **Check a claim against real data before repeating it.** We said option
  buyers overpay; real prices showed that was only true for index funds.
  (Nov 11)

## Open questions

- Is there any signal for these stocks that beats chance? Nothing tested so
  far does.
- Should the bot bet less after a losing streak? It would not improve the
  odds of beating SPY, but in the five-year test it cut the chance of losing
  more than half the sleeve from about 1 in 3 to about 1 in 8.
