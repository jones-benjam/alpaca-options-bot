# Strategy log

A plain-English record of what the bot does, every change made to it and why,
and how the portfolio moved each day. Newest changes are at the bottom of each
section. All times are US Eastern.

## The goal

Beat the professor's portfolio, which simply holds SPY (a fund that tracks the
500 largest US companies). We started with $100,000 of practice money on
Alpaca. The bot manages $50,000 of it, called "the sleeve" (it was $25,000
until Nov 10). The contest ends on December 2, 2026.

## The strategy in plain English

**The bot buys options, never sells them short.** An option is a bet on where
a stock will go by a certain date. A *call* makes money if the stock rises. A
*put* makes money if the stock falls. Options move much more than the stock
itself, so wins and losses are both large. The most the bot can lose on any
one bet is what it paid for it.

**Step 1: read the market's mood.** The bot compares SPY and QQQ (a fund of
big technology companies) with their average price over the last 20 days.
- Both above average: the market is rising. The bot only buys calls.
- Both below average: the market is falling. The bot only buys puts.
- One of each: mixed. The bot may buy both kinds.

**Step 2: the main bets (six at a time, about 14% of the sleeve each).**
The bot watches 16 heavily traded, fast-moving stocks and funds, such as
Nvidia, Tesla, Coinbase and Palantir. In a rising market it buys calls on the
ones climbing fastest. In a falling market it buys puts on the ones dropping
fastest. Each bet expires in about three weeks.

**Step 3: same-day bets (one a day, about 6% of the sleeve).** After 10:00 am
the bot looks at the range SPY and QQQ traded in during the first half hour.
If the price breaks out of that range in the same direction as the market's
mood, it buys an option that expires that same afternoon. These are small,
fast, lottery-style bets and are always closed by 3:00 pm.

**When it sells.**
- A bet that has lost half its value is sold (the "stop loss").
- A bet that has doubled has half of it sold to lock in profit. The rest is
  kept until it falls 30% from its best price.
- A bet that was up 50% and slides back to what was paid is sold, so a winner
  does not turn into a loser.
- A main bet is sold if the stock's trend reverses, or four days before the
  option expires.

**Safety rules.**
- If the sleeve ever falls to $15,000 (a 70% loss), the bot sells everything
  and stops trading.
- On December 2 it opens nothing new and sells everything by 3:00 pm.
- It only touches bets it placed itself, so teammates can trade the rest of
  the account freely.

**How risky is this?** Very. The sleeve can gain or lose 10% or more in a
day. Over a few weeks the result depends mostly on whether the market keeps
trending, not on skill.

## Changes to the strategy

### Mon Nov 9, 2026, 3:31 pm: Bot switched on
- **What:** First version started trading, with the strategy described above,
  except that it could make two same-day bets a day (SPY and QQQ) in either
  direction.
- **Why:** Start of the project.

### Mon Nov 9, 2026, 3:54 pm: Watch same-day bets more closely
- **What:** While a same-day bet is open, the bot now checks prices every 10
  seconds instead of every 60.
- **Why:** These bets can lose half their value in well under a minute. A
  check once a minute could sell far too late.

### Mon Nov 9, 2026, 4:43 pm: Safety fixes after a code review
- **What:** Five fixes. (1) On days the market closes early, such as the
  Friday after Thanksgiving, the bot now sells same-day bets an hour before
  the real close instead of waiting for 3:00 pm. (2) Before selling on a price
  drop, the bot waits for a second price check to agree, so one faulty price
  cannot trigger a sale. (3) Obviously broken prices are ignored. (4) and (5)
  were small reliability fixes.
- **Why:** A review found these weak spots before any of them caused a loss.
  The price feed we use is free and only approximate, so it can occasionally
  show a wrong price.

### Tue Nov 10, 2026, 4:24 pm: Same-day bets must agree with the market's mood
- **What:** (1) Same-day bets are only allowed in the direction of the
  market's mood: puts only when the market is falling, calls only when it is
  rising. (2) One same-day bet a day instead of two. In effect from Wed Nov 11.
- **Why:** On Nov 10 the bot judged the market to be falling and held three
  bets on falling stocks. At 10:01 am it also bought same-day bets on SPY and
  QQQ *rising*. That contradicted its own view. Both lost half their value in
  22 minutes, costing $1,620 (6.5% of the sleeve). SPY and QQQ also move
  together, so two bets were really one double-sized bet.
- **Effect:** The most the bot can lose on same-day bets in a day drops from
  about 6% of the sleeve to about 3%.

### Tue Nov 10, 2026, 4:35 pm: Sleeve doubled to $50,000, six main bets
- **What:** (1) The bot now manages $50,000, half of the starting portfolio,
  up from $25,000. (2) It holds up to six main bets instead of three, each
  about 14% of the sleeve (roughly $7,400, the same size as before). In effect
  from Wed Nov 11, when it will look for three more bets shortly after 9:45 am.
- **Why:** The team decided to put more of the account behind the bot. Six
  bets were chosen over three bigger ones so the new money goes to work right
  away and is spread over more stocks.
- **Effect:** The bot now drives half the account. A 10% move in the sleeve
  moves the whole account by about 5%, up from about 2.5%. The stop-everything
  level rises with it, from $7,500 to $15,000, so the most the bot could lose
  before shutting itself off is about $35,000, or 35% of the starting account.
- **Record keeping:** The $25,000 added is not counted as a gain. In the
  daily record, profit is shown in dollars so it reads the same before and
  after this change.

## Daily record

How to read the table:
- **Whole account** is the full $100,000 practice account, the number the
  class is graded on. As of Nov 10 the bot's sleeve is the only part invested;
  the rest is in cash for teammates to use.
- **Bot's sleeve** is the money the bot manages: $25,000 through Nov 10 and
  $50,000 from Nov 11. **Sleeve profit** is what the bot has made or lost in
  dollars since it started, not counting money added to it.
- **SPY since start** is measured from SPY's close on Fri Nov 6, the last
  close before the bot started. The professor's own starting point may differ.
- In **Holding**, "6 NVDA 11/27 180P" means 6 put options on Nvidia that
  expire Nov 27 and pay off if Nvidia is below $180. P is a put, C is a call.
  The percentage is the gain or loss on that bet so far.
- A new row is added each trading day with `python3 bot.py journal`.

| Date | Whole account | Account day | Bot's sleeve | Sleeve day | Sleeve profit | SPY day | SPY since start | Holding at close | Trades |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-09 | $100,006 | +0.01% | $25,006 | +0.02% | +$6 | +2.36% | +2.36% | 6 NVDA 11/27 180P (+0%), 8 PLTR 11/27 172.5P (+0%), 7 COIN 11/27 140P (+0%) | Bought 6 NVDA 11/27 180P at $10.90; Bought 8 PLTR 11/27 172.5P at $8.65; Bought 7 COIN 11/27 140P at $9.40. The bot started at 3:31 pm, after most of SPY's gain that day. |
| 2026-11-10 | $102,578 | +2.57% | $27,580 | +10.29% | +$2,580 | -0.37% | +1.98% | 6 NVDA 11/27 180P (+48%), 8 PLTR 11/27 172.5P (+0%), 7 COIN 11/27 140P (+16%) | Bought 10 SPY 11/10 753C at $1.52; Bought 6 QQQ 11/10 681C at $2.50; Sold 10 SPY 11/10 753C at $0.71 (-$810); Sold 6 QQQ 11/10 681C at $1.15 (-$810) |
