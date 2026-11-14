# Final project: slide outline

A starting point for the five slides (strategy, implementation, results,
takeaways). Figures are as of the official close on Thu Nov 12, 2026 and will
change before the contest ends on Dec 2. Refresh every number from
`docs/index.html` (the dashboard) and `STRATEGY_LOG.md` before presenting.

---

## Slide 1. The goal and the bet

**Headline:** Beat a portfolio that just holds SPY, using a trading bot.

- $100,000 of practice money on Alpaca. The professor holds SPY.
- We gave an automated bot half the account and told it to take big risks.
- The bot only buys options: calls when prices are rising, puts when they
  are falling. An option moves far more than the stock, so wins and losses
  are both large.

**Say out loud:** We chose a high-risk approach on purpose. With practice
money and a pass/fail comparison against SPY, the downside was small.

## Slide 2. How the bot decides

**Headline:** Three rules: read the mood, pick the fastest movers, cut losers early.

- **Mood:** are SPY and QQQ above or below their 20-day average?
- **Picks:** up to six bets on the strongest (or weakest) of 16 fast-moving
  stocks, each expiring in about three weeks. One small same-day bet.
- **Exits:** sell a loser at half its value; sell half of a winner when it
  doubles and let the rest run; never hold through an earnings report.
- **Safety:** a kill switch, a cap at the account's real cash, and a rule
  that one bad price cannot trigger a sale.

**Visual:** the strategy section of `STRATEGY_LOG.md`, or a simple flow:
mood, picks, exits.

## Slide 3. How we built it

**Headline:** A small program on a $2-a-month server, built with an AI coding assistant.

- About 14 dated changes in two weeks, each logged in plain English with the
  reason (`STRATEGY_LOG.md`).
- It rebuilds everything it knows from the broker's records, so it survives
  restarts with no database.
- Every order is stamped with why it was placed, which gives the bot a
  memory we can study (`memory/`).
- A simulated broker tests every rule before a change goes live.
- A free AI model on our own Mac mini plays the bot's "trader" and writes a
  daily diary. It cannot trade or change a rule.

**Visual:** the dashboard page, or a diagram: bot on Fly.io, records on
GitHub, the trader persona on the Mac mini.

## Slide 4. Results

**Headline:** Ahead of SPY so far, on a handful of big winners.

| | Through Nov 12 |
|---|---|
| Whole account | $119,090 (+19.1%) |
| SPY over the same period | +3.0% |
| The bot's profit | +$20,340 |
| Closed trades | 8, of which 4 made money |
| Best and worst trade | +$8,460 and −$1,568 |

- The path was rough: +6.5% one day, −6.0% the next, +19.0% the day after.
- The market fell and the bot was holding bets on falling prices.

**Visual:** the "account against SPY" chart and the "every closed trade"
chart from the dashboard.

## Slide 5. What we learned

**Headline:** We were ahead, and our own tests say that was mostly luck.

- **The stock picker has no proven edge.** Over five years its picks were
  right about half the time, the same as random picks.
- **Bet size is the real risk.** In the five-year replay every version of
  the rules eventually lost the whole sleeve, while SPY gained 85%.
- **More leverage and "learning" rules did not improve the odds.** Selling
  options instead of buying them was steadier and still lost.
- **We corrected ourselves with real data.** We assumed option buyers
  overpay. Real prices showed that was true for index funds, not for
  individual stocks.
- **Building it taught as much as trading it:** stale prices, a shared
  account that could have borrowed without anyone deciding to, and a
  restart that quietly switched off two selling rules.

**Say out loud:** If we did this with real money, the honest plan would be
much smaller bets, a signal that has been shown to work, and real costs.

---

## Backup slides, if asked

- **"Did the AI trader beat the rules?"** `memory/REVIEW.md`, the section
  scoring the personas' picks against the rules' top three.
- **"How do you know the numbers are right?"** The daily record uses
  Alpaca's official closing values, and the bot's profit matches the
  account's change to within the teammates' own positions.
- **"What would you change?"** `memory/LESSONS.md`.
