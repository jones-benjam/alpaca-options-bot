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

### Tue Nov 10, 2026, 4:30 pm: Sleeve doubled to $50,000, six main bets
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

### Tue Nov 10, 2026, 5:06 pm: Step aside for earnings reports
- **What:** (1) The bot will not open a new bet on a stock in the five days
  before that company reports its quarterly results. (2) If it already holds
  a bet on that stock, it sells in the last half hour before the report.
  Right now this only affects Nvidia, which reports after the close on
  Tue Nov 17. No other stock on the list reports before the contest ends.
- **Why:** Options cost extra just before a report, because everyone expects
  a big move. The moment the results are out, that extra cost disappears, so
  an option can lose value even if the stock moves the right way. The stock
  can also jump sharply in either direction overnight. Holding through a
  report is closer to a coin flip than to a trend bet.
- **Effect:** The Nvidia bet opened on Nov 9 will be sold by about 3:30 pm on
  Nov 17 if it has not been sold earlier. New Nvidia bets are blocked from
  Nov 12 and allowed again from Nov 18.

### Tue Nov 10, 2026, 5:06 pm: What a five-year test of the rules showed (no rule change)
- **What we did:** Replayed the bot's rules on daily prices from July 2021 to
  November 2026 (`python3 backtest_signal.py`). Stock prices are real. Option
  prices are estimated with a standard formula, because historical option
  prices cost money, so the dollar results are a rough guide only.
- **Finding 1: the stock picker has no proven edge.** The stocks it picked
  moved the right way over the next two weeks about half the time. Picking
  stocks at random (but still following the market's mood) did the same.
  Changing how the bot ranks stocks made no meaningful difference, so the
  ranking was left alone.
- **Finding 2: the odds are against us, but the wins are big.** Options lose a
  little value every day, so being right half the time loses money on
  average: roughly 2% to 5% per bet in the main estimate (anywhere from a 9%
  loss to a 6% gain under other assumptions). Looking at every possible
  three-week stretch in those five years:
  - The sleeve's typical (middle) result was a loss of 15% to 33%.
  - It lost more than half its value in about 1 stretch out of 4.
  - It gained more than half in about 1 stretch out of 6.
  - The whole account beat SPY in roughly 1 stretch out of 3.
- **Finding 3: longer-lasting options were steadier.** Using options that
  expire in about six weeks instead of three cut the chance of losing more
  than half the sleeve from about 1 in 4 to about 1 in 11, and beat SPY a
  little more often (about 4 stretches in 10). The price is smaller best
  cases. This has not been changed in the bot (see the next entry).
- **Finding 4: the "trend reversed, sell" rule earns its keep.** Removing it
  made every measure worse.
- **Caveats:** Those five years were a strong period for stocks (SPY rose
  86%), which makes SPY hard to beat and is unkind to bets on falling prices.
  The test checks positions once a day; the real bot checks every minute.
- **What it means:** The bot is a high-risk bet that a big move happens in the
  next three weeks. It is not a reliable way to beat the market. That was the
  choice made on day one; this test puts numbers on it.

### Tue Nov 10, 2026, 5:08 pm: Decision to keep three-week options
- **What:** No change. The team looked at the test result above and chose to
  keep buying options that expire in about three weeks, not six.
- **The trade-off accepted:** Three-week options move more for the same
  money, so the best outcomes are bigger. In return, the chance of a large
  loss stays higher than it would be with six-week options.
- **Effect:** The bot's rules stay exactly as they were.

### Wed Nov 11, 2026, 2:43 pm: Two more tests: more leverage, and "learning" (no rule change)
- **What we did:** Used the same five-year replay to test two ideas the team
  raised. Same caveat as before: stock prices are real, option prices are
  estimated.
- **More leverage does not improve the odds.** We tried cheaper, riskier
  options (ones that only pay off after a bigger move) and options that
  expire in 10 days instead of 21. The rare big wins got bigger, but the
  chance of beating SPY did not go up, and the chance of losing more than
  half the sleeve in three weeks rose from about 1 in 4 to as much as 1 in 2
  or worse. With a stock picker that is right half the time, leverage only
  stretches the range of outcomes in both directions.
- **Simple "learning" does not improve the odds either.** We tried having
  the bot react to its own recent results: avoiding a stock for a week or
  two after losing on it, betting more after a winning streak, betting more
  after a losing streak. None changed the chance of beating SPY. Recent wins
  and losses did not predict the next ones, because results are driven
  mostly by where the market goes next.
- **One rule did reduce big losses:** halving the bet size after a losing
  streak cut the chance of losing more than half the sleeve from about 1 in
  3 to about 1 in 8. It works by betting less during bad stretches, not by
  predicting anything, and it did not make beating SPY more likely. It has
  not been added to the bot.
- **What it means:** The useful kind of memory for this bot is a record we
  can study and explain, not a self-adjusting one.

### Wed Nov 11, 2026, 2:44 pm: The bot now remembers each bet's best price
- **What:** When the bot restarts, it now looks up the highest price each of
  its options has reached since it bought them.
- **Why:** Two of the selling rules depend on that number: "sell if it falls
  30% from its best price" and "sell a bet that was up 50% if it slides back
  to what was paid". The bot kept that number in a file that is erased every
  time we update the bot, so each update quietly switched those two rules
  off until prices made new highs. No money was lost to this, but the Nvidia
  bet spent a day unprotected after being up more than 50%.
- **Effect:** Those rules now survive updates. On this restart the bot
  recovered the best prices of all six bets, including Nvidia's (up 69% at
  its best). The Nvidia bet is now sold if it falls back to about $11.45.

### Wed Nov 11, 2026, 2:44 pm: The bot can only spend cash the account really has
- **What:** Before buying, the bot now checks the account's actual cash and
  never spends more than that.
- **Why:** The account is shared. On Nov 11 teammates invested about $58,700
  in stocks. Together with the bot's $50,000 that is more than the account
  holds. The account had about $3,900 in cash while the bot's own
  bookkeeping said it still had about $12,800 to spend. The broker would
  have lent the difference automatically, which is borrowing nobody chose.
- **Effect:** The bot cannot borrow. It can still reuse the money from its
  own sales. If teammates want the bot to use its full $50,000, some cash
  has to be left free for it.

### Wed Nov 11, 2026, 2:55 pm: Real option prices: a correction, and buying versus selling (no rule change)
- **What we did:** Until now our five-year test had to guess how expensive
  options are. This time we measured it. Alpaca keeps real prices of expired
  options back to February 2024, so we priced 505 real three-week bets (a
  call and a put bought together, on each of the 16 names, every month) and
  checked what each one actually paid out (`python3 measure_option_cost.py`).
- **Correction to the Nov 10 entry.** We had assumed options cost about 20%
  more than the stock's recent swings justify, and said that being right
  half the time therefore loses 2% to 5% per bet. The real prices say
  otherwise for individual stocks: their options were priced almost exactly
  in line with recent swings, and buyers of those 505 bets came out roughly
  even (+4% on average, give or take 4%). Options on the index funds (SPY,
  QQQ, IWM) were the exception: about 9% more expensive than recent swings,
  and their buyers lost about 9% on average.
- **What that changes.** With real price levels the bot's average bet is
  slightly positive (about +2%), not negative. What does not change: the
  typical bet still loses (3 bets in 4 lose, the middle result is about
  -37%), the stock picker is still no better than chance, and over five
  years every version still ends with the sleeve near zero. The reason is
  bet size. Putting 84% of the sleeve into bets that usually lose means a
  normal losing streak wipes out most of the money before the occasional
  big winner arrives. Three-week odds are about the same as before: the
  account beats SPY about 4 times in 10, and the sleeve loses more than half
  about 3 times in 10.
- **Selling instead of buying.** We tested the opposite trade: selling
  options with a capped loss, using the same stock picker. It was much
  steadier (it never lost more than half the sleeve in any three-week
  stretch) but it also lost money: about 1% of the amount at risk per trade.
  It beat SPY no more often than buying did.
- **Trading costs decide the sign.** With our standard cost assumption
  everything loses. With very low costs, small-sized versions of both
  buying and selling make a little. Even with zero costs, none of them
  matched simply holding SPY over the same five years (+85%).
- **What it means:** Neither side of the options market makes this stock
  picker profitable. The missing piece is a way of choosing stocks or timing
  that is right more often than chance. Without that, the only real choices
  are how big the swings are and how much is lost to costs.
- **Caveat:** 505 bets over 32 months is a modest sample from an unusually
  eventful market, and bets made in the same month tend to win or lose
  together, so the true uncertainty is wider than "give or take 4%".

### Wed Nov 11, 2026, 3:09 pm: The bot now remembers why it made each trade
- **What:** (1) Every order the bot places is now stamped with the reason:
  for a purchase, the market's mood and how strong the signal was; for a
  sale, which rule triggered it. (2) A new `memory` folder holds a table of
  every trade with those reasons and its result, a daily note of the
  market's mood, a plain-English review that is rewritten every day, and a
  hand-written list of lessons. (3) The daily job on GitHub keeps all of it
  current.
- **Why:** Until now the bot knew what it had traded but not why, so nobody
  could say which kinds of trades were working. The stamp is stored with
  the order at the broker, so the memory cannot be lost when the bot
  restarts.
- **What it is not:** The review is written by fixed rules, not by an AI
  model, and it costs nothing to run. It describes what happened and flags
  things that look wrong, such as a bet against the market's mood. It does
  not predict anything and it changes no rules by itself. Rule changes still
  go through the team and are recorded here.
- **Effect on trading:** None. The bot buys and sells exactly as before.

### Fri Nov 13, 2026, 12:22 pm: Groundwork for a trader with a personality (not switched on yet)
- **What:** The project can now give the bot a voice: a free AI model that
  runs on our own Mac mini and plays a trader character, a brilliant,
  obsessive trader who always wants a bigger stake. Each day he will write a
  diary about the bot's trades, choose the trades he would make from the
  same signals the rules saw, and once a week write notes to himself that he
  reads back later. The setup steps are in `MAC_MINI_SETUP.md`. None of this
  runs until the Mac mini is set up.
- **Why:** To have the bot explain itself in plain words, and to test, at
  no cost, whether an AI model picks better than the fixed rules.
- **What he cannot do:** He does not trade and cannot change a rule or a
  limit. His picks are only recorded and scored. Every number he writes is
  checked against the bot's records, and a made-up figure is flagged.
- **Also new in the bot's memory:** each day's full list of signals and the
  day's news headlines for our stocks, both free from Alpaca.
- **Effect on trading:** None.

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
- A new row is added automatically after each market close. A date marked
  **(preliminary)** or **(as of ...)** uses prices from that moment. It is
  replaced the next morning with Alpaca's official end-of-day values, which
  are the numbers the class is graded on.

| Date | Whole account | Account day | Bot's sleeve | Sleeve day | Sleeve profit | SPY day | SPY since start | Holding at close | Trades |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-09 | $100,006 | +0.01% | $25,006 | +0.02% | +$6 | +2.36% | +2.36% | 6 NVDA 11/27 180P (+0%), 8 PLTR 11/27 172.5P (+0%), 7 COIN 11/27 140P (+0%) | Bought 6 NVDA 11/27 180P at $10.90; Bought 8 PLTR 11/27 172.5P at $8.65; Bought 7 COIN 11/27 140P at $9.40. The bot started at 3:31 pm, after most of SPY's gain that day. |
| 2026-11-10 | $106,493 | +6.49% | $31,495 | +25.95% | +$6,495 | -0.37% | +1.98% | 6 NVDA 11/27 180P (+54%), 8 PLTR 11/27 172.5P (+35%), 7 COIN 11/27 140P (+32%) | Bought 10 SPY 11/10 753C at $1.52; Bought 6 QQQ 11/10 681C at $2.50; Sold 10 SPY 11/10 753C at $0.71 (-$810); Sold 6 QQQ 11/10 681C at $1.15 (-$810) |
| 2026-11-11 | $100,054 | -6.05% | $50,386 | -10.81% | +$386 | +1.32% | +3.32% | 6 NVDA 11/27 180P (+16%), 8 PLTR 11/27 172.5P (-24%), 7 COIN 11/27 140P (-4%), 6 MSTR 12/04 125P (-7%), 3 MSFT 12/04 540P (+24%), 2 AMD 12/04 565C (-5%) | Bought 6 MSTR 12/04 125P at $10.90; Bought 28 NFLX 12/04 64P at $2.41; Bought 3 MSFT 12/04 540P at $20.00; Bought 35 SPY 11/11 759C at $0.78; Sold 17 SPY 11/11 759C at $1.55 (+$1,309); Sold 18 SPY 11/11 759C at $2.15 (+$2,466); Sold 28 NFLX 12/04 64P at $1.85 (-$1,568); Bought 2 AMD 12/04 565C at $31.25 |
| 2026-11-12 | $119,090 | +19.03% | $70,340 | +39.60% | +$20,340 | -0.35% | +2.96% | 8 PLTR 11/27 172.5P (-17%), 7 COIN 11/27 140P (+35%), 6 MSTR 12/04 125P (+29%), 3 MSFT 12/04 540P (+24%), 2 AMD 12/04 565C (+54%), 46 NFLX 12/04 63P (-1%) | Sold 3 NVDA 11/27 180P at $28.55 (+$5,295); Sold 3 NVDA 11/27 180P at $21.45 (+$3,165); Bought 46 NFLX 12/04 63P at $1.96; Bought 20 QQQ 11/12 690C at $2.00; Sold 10 QQQ 11/12 690C at $4.07 (+$2,070); Sold 10 QQQ 11/12 690C at $3.38 (+$1,380) |
| 2026-11-13 (as of 12:08 ET) | $124,013 | +4.13% | $75,797 | +7.76% | +$25,797 | -0.69% | +2.24% | 8 PLTR 11/27 172.5P (-1%), 7 COIN 11/27 140P (+52%), 6 MSTR 12/04 125P (+61%), 3 MSFT 12/04 540P (+13%), 46 NFLX 12/04 63P (+15%) | Sold 2 AMD 12/04 565C at $31.00 (-$50); Bought 17 QQQ 11/13 679P at $2.50; Sold 8 QQQ 11/13 679P at $5.22 (+$2,176); Sold 9 QQQ 11/13 679P at $4.50 (+$1,800) |
