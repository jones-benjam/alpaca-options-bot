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
- Both below average: the market is falling. The bot buys calls on the most
  beaten-down stocks, betting on a rebound (it bought puts until Nov 23).
- One of each: mixed. The bot may buy both kinds.

**Step 2: the main bets (up to ten, about 20% of the sleeve each, as cash allows).**
The bot watches 16 heavily traded, fast-moving stocks and funds, such as
Nvidia, Tesla, Coinbase and Palantir. In a rising market it buys calls on the
ones climbing fastest. In a falling market it buys calls on the ones that have
dropped furthest. Each bet expires in about two weeks.

**Step 3: same-day bets (one a day, about 6% of the sleeve).** After 10:00 am
the bot looks at the range SPY and QQQ traded in during the first half hour.
If the price breaks out of that range in the same direction as the market's
mood, it buys an option that expires that same afternoon. These are small,
fast, lottery-style bets and are always closed by 3:00 pm.

**When it sells.**
- A main bet that has lost 80% is sold (the "stop loss"); a same-day bet at 50%.
- A main bet up 200% has half of it sold. Once it has been up 125%, it is sold
  if it falls 40% from its best price (25% in its last days). Same-day bets
  sell half at +100% and trail by 35%.
- A bet that was up 50% and slides back to what was paid is sold, so a winner
  does not turn into a loser.
- A main bet is sold two days before the option expires. A bet that follows
  the trend is also sold if the trend reverses. A dip call is not, because it
  starts below the trend on purpose.

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

### Tue Nov 17, 2026, 3:43 pm: Profits go back into the engine
- **What:** (1) The bot can now hold up to ten main bets instead of six. It
  keeps opening new bets, each about 14% of the sleeve as it stands that day,
  for as long as it has the cash, so money freed by profitable sales goes
  straight back to work. (2) It always keeps enough cash back for one
  same-day bet. (3) It skips a new bet smaller than half the normal size,
  rather than dribbling leftover cash into tiny ones. It went live at
  3:43 pm, inside the day's buying window, and immediately opened three new
  bets with the idle cash: puts on Google, Meta and AMD, about $46,000 in all.
- **Why:** The team's instruction: every dollar of profit that comes back
  as cash should keep the engine going, to make as much as possible. Bets
  already grew with the sleeve, but once all six slots were filled, cash
  from sales sat idle: on Nov 17 the sleeve held about $59,000 in cash while
  every slot was taken.
- **Effect:** With the sleeve near $117,000, a new bet is about $16,000.
  Nearly all of the sleeve can now be invested at once, so gains and losses
  will both be larger. While the market's mood is falling, every new bet is
  a put, which makes a sharp rally more painful. The kill switch still
  closes everything if the sleeve falls to $15,000, and the bot still cannot
  spend more cash than the account really has.

### Tue Nov 17, 2026, 3:53 pm: Shoot for the moon, with a parachute
- **What changed, aiming higher:**
  - **Bigger bets:** each new main bet is 20% of the sleeve, up from 14%.
  - **Cheaper, longer-shot options:** new bets use options about 5% "out of
    the money", meaning the stock has to move a little further before they
    pay. They cost less, so the same money buys more of them, and they pay
    off much more on a big move. They also expire worthless more often.
  - **Let winners run:** half of a bet is now sold when it triples (up 200%),
    instead of when it doubles. Once a bet has doubled, it is sold if it
    falls 40% from its best price (it was 30%).
- **What changed, the parachute (a "lead lock"):** the class is graded on
  whether the whole account beats SPY, and the account is far ahead. The bot
  now keeps the account at least 5 points ahead of SPY. It may hold options
  worth up to twice the account's lead above that line. As the lead
  shrinks, it stops adding bets; if the lead is gone, it closes everything.
- **Why:** The team's instruction: be aggressive and shoot for the moon. We
  tested the options on five years of prices, looking at every possible
  11-trading-day stretch (the time left in the contest):

  | | Typical (middle) result | Average result | Best 1 in 10 | Lose more than half |
  |---|---|---|---|---|
  | Before | -23% | +0.5% | +94% or better | about 3 in 10 |
  | Now | -31% | +19% | +159% or better | about 4 in 10 |

  The average and the best cases rise a lot; the typical result and the
  chance of a big loss get worse. That is what aiming for the moon means.
  Letting winners run improved every measure on its own. We rejected options
  10% out of the money: half of those stretches lost more than half the
  sleeve, and real prices for those puts run 1% to 9% above what the test
  assumes.
- **Effect today:** The lock already limits new bets. The bot holds about
  $104,000 of options against a lead of about $56,000, so it allows only
  about $7,000 more. As the lead grows, more money is released for new
  bets. The open bets follow the new selling rules from now on.

### Wed Nov 18, 2026, 1:23 pm: A live dashboard (no rule change)
- **What:** The bot now runs its own web page at
  https://msbc5220-optbot.fly.dev. It shows the whole account against SPY,
  the lead lock, every open position, recent sales and what the bot is
  doing, and refreshes itself every 15 seconds. It works on a phone. It is
  read-only: nothing on it can place a trade, and loading it never slows the
  bot down.
- **Why:** So the team can follow the bot live instead of waiting for the
  daily record.
- **A one-minute outage:** The first update at 1:22 pm left out a new file,
  so the bot failed to start. It was fixed and trading again at 1:23 pm. No
  orders were missed and every position was intact.
- **Cost:** Nothing extra. It runs on the same server, with Fly.io's free
  shared web address.
- **Effect on trading:** None.

### Wed Nov 18, 2026, 3:45 pm: The dashboard becomes a trading terminal (no rule change)
- **What:** The live page now looks like a trading terminal: black screen,
  amber labels, a price ticker along the top and numbered shortcuts to each
  section. Its new parts are:
  - A trade blotter listing every buy and sell the bot has made, grouped by
    day. Each row shows why the order was placed, the amount, how long the
    bet was held and its profit or loss. Buttons narrow it to buys, sells,
    wins or losses, or to one stock.
  - A win/loss record: wins against losses by count and by dollars, the
    average win and loss, the best and worst sale, and the current streak.
  - A bar for each sale, plus profit broken down by stock, by engine and
    by the reason for selling.
  - Open positions now show dollar profit, days left and a total row.
- **Telling wins from losses:** Green and red are used only for wins and
  losses. Each sale also carries a WIN or LOSS label and an up or down
  arrow, so the colour is never the only cue. Buys are shown in blue and
  sells in amber.
- **First reading:** 22 sales, 15 wins and 7 losses (68%). Winning sales
  made $42,043 and losing sales lost $11,308. Taking profit on half and the
  trailing stop produced every win.
- **Effect on trading:** None. The page only reads what the bot already
  records.

### Wed Nov 18, 2026, 4:00 pm: The dashboard in CU colors (no rule change)
- **What:** The live page now uses CU Boulder's gold, black and grays, with
  a vintage video-game look: a pixel font, pixel frames, faint screen lines,
  and a side-scrolling scene up top. In the scene a pixel bison runs past the
  Flatirons and coins, with the day number, wins, losses and the bot's profit
  shown above it.
- **What stays the same:** All the figures, the blotter and the filters.
  Green and red still mean only win and loss, and each result keeps its
  WIN or LOSS label and arrow. Buys are now cyan and sells gold. Motion stops
  for anyone whose device asks for reduced motion.
- **Effect on trading:** None.

### Wed Nov 18, 2026, 10:30 pm: The AI trader suggests, the rules decide
- **What:** The trader persona (a local AI model on the Mac mini) already
  picked up to three trades each evening from the day's signals, with a
  conviction from 1 to 5, but nothing used them. From the next trading day
  the bot reads those picks and tries the ones of conviction 3 or more
  first, highest conviction first. A pick that another persona also made
  gets one extra point. The rest of the slots are filled in the usual
  momentum order.
- **What stays the same:** The bot only buys a pick its own rules still
  approve that morning: the market's mood, the trend, the minimum momentum,
  the earnings blackout and the contract checks. Bet size, stops, the lead
  lock, the kill switch and the end date are unchanged. The same-day (0DTE)
  bets are untouched. If the picks are missing, more than four days old or
  unreadable, the bot trades exactly as before.
- **Why:** The rules pick stocks no better than chance (see LESSONS.md), and
  cash is now short, so the order in which approved signals are tried
  decides which ones get funded. The AI's picks set that order, and every
  trade it chose is tagged so the review can compare its results with the
  rules'.
- **How it learns:** Each night the review lists what the bot did with each
  suggestion (bought and how it went, or not bought and why), plus profit
  by "AI pick" against "rules alone". The persona now reflects every day
  instead of weekly, and on Fridays may suggest up to three rule changes in
  `memory/PROPOSALS.md`. A suggestion changes nothing until a person
  approves it here. The risk limits are not on the list it may suggest.
- **Switch:** `AI_PICKS=0` on the host turns it off. `AI_MIN_CONVICTION`
  sets the lowest conviction acted on (3).
- **Effect on trading:** Changes which approved signals are bought first.
  It never adds a trade the rules would not make.

### Thu Nov 19, 2026, 12:00 am: Dionysus may free cash from a winner for a strong pick
- **Names:** The AI trader is now called **Dionysus**; **Midas** is the bot
  and its rules. Picks made under his old name still count.
- **What:** With his picks each evening, Dionysus may name up to two of
  Midas's open three-week bets that he would sell part of to pay for a pick.
  The next day Midas sells part of one only when all of these hold: the pick
  is rated 4 or 5 and the rules approve it; a contract for it passed the
  checks; cash or lead-lock room is the only thing in the way; the named bet
  is up at least 10% with a believable quote; and the sale frees enough for a
  proper-size bet. It sells only as many contracts as needed, at most once a
  day, then buys the pick.
- **What stays the same:** Midas still never buys anything its rules reject.
  Stops, sizing, the kill switch, the lead lock and the end date are
  unchanged.
- **Why:** On Nov 18 cash and the lead lock blocked new bets, so Dionysus's
  picks could not be bought at all. This lets a strong pick replace part of
  an older winner.
- **Risk:** LESSONS.md says the profit so far came from letting winners run.
  Selling part of a winner early works against that, so the rule is narrow,
  each sale is tagged ("sold to fund Dionysus's pick") and the review shows
  how those trades do. `AI_FREE_UP=0` turns it off.
- **Also:** Dionysus's page (`/dionysus` on the live dashboard; the old
  `/midas` link still works) now explains who is who and how a pick becomes a
  trade, says in plain words what Midas did with each pick, and compares his
  record with the rules'.
- **Effect on trading:** Can sell part of one winning bet a day, to buy a
  rule-approved pick rated 4 or 5.

### Thu Nov 19, 2026, 1:00 am: Dionysus may change Midas's settings
- **What:** Each evening Dionysus may change ONE of Midas's settings for the
  next trading day: the lowest momentum for a new bet, how far out of the
  money, days to expiry, the stop loss, the take-profit and trailing levels,
  the number of slots, the bet size, or the lowest rating of his that Midas
  acts on.
- **Limits:** Each dial has a hard floor and ceiling and a largest step
  (`TUNING_LIMITS` in config.py). Midas re-checks every value itself and
  applies settings only between trading days. At most one change starts on
  a given day, a dial rests 5 days after a change, and nothing changes before
  the bot has closed 8 trades. The kill switch, the lead lock, the end date,
  the same-day engine and the safety checks are not on his list.
- **Oversight:** A change shows on his page the evening before it starts.
  `mac_mini/veto.sh DIAL` cancels it. The Mac mini undoes it automatically if
  three or more three-week trades opened after it average a loss at least 10
  points worse than before. `AI_TUNING=0` turns this off and restores every
  value in config.py. Each change is logged in its own section below.
- **Why:** This is the first step toward the long-term goal in ROADMAP.md:
  let Dionysus find and explain a better strategy, and take more control as
  he earns it.
- **Effect on trading:** Up to one setting can differ from config.py each
  day, always inside the limits.

### Thu Nov 19, 2026, 3:30 pm: Sharper picks, and setting changes must show their evidence
- **What:** Dionysus's evening picks now leave out stocks Midas already
  holds. Midas never adds to one, so on Nov 18 two of his three top-rated
  picks (MSTR and COIN) were skipped. His settings changes now need evidence.
  He is shown a record computed from Midas's closed three-week trades:
  overall, and by how each was sold. Each change must quote figures from
  that record, and a separate, skeptical review by the model must agree that
  the figures support moving that setting in that direction.
- **Why:** His first change (start trailing at +125%) was justified by a note
  about the stop loss, which is a different rule. As Dionysus gets more
  control, each change he makes should rest on Midas's real results.
- **Oversight:** Changes the review turns down show on his page as "TURNED
  DOWN", with the reviewer's reason, and never reach Midas. They still use
  up that day's one change.
- **Effect on trading:** Trading rules are unchanged. Picks that Midas can
  act on are more likely, and fewer settings changes get through.

### Thu Nov 19, 2026, 3:45 pm: Tighter trailing stop in a bet's last days, and a daily market archive
- **What:** A three-week bet's trailing stop tightens from 40% to 25% from its
  best price once the bot must sell it within 6 days. That deadline is its
  time stop (4 days before expiry) or the contest's end on Dec 2, whichever
  comes first. Separately, the Mac mini now saves a daily market archive
  about half an hour before the close: option chains with quotes, implied
  volatility and greeks for every stock Midas watches, plus Midas's own view
  of the day (see `archive/README.md`).
- **Why:** A big winner close to its forced sale has little time left to
  recover, so giving back 40% of its best price is costly. At its best of
  +230%, the COIN put would sell at about +98% with a 40% trailing stop and
  about +148% with a 25% one. From about Nov 26 every open bet is within 6
  days of the Dec 2 close-out, so gains are protected as the contest ends.
  The archive starts the record the strategy lab needs. Quotes and greeks for
  whole chains cannot be downloaded again later.
- **Effect on trading:** Exits for bets in their last days come sooner. The
  archive only reads market data. `CORE_TRAIL_LATE` (0.25) can be changed as
  a Fly secret.

### Thu Nov 19, 2026, 7:00 pm: Dionysus gets a face (no rule change)
- **What:** The top of Dionysus's desk page now shows him as a grizzled old
  trader in a booth, drawn as pixel art. He has a long grey beard, a vine
  wreath, a green eyeshade and half-moon glasses, and sits among ledgers,
  a chalkboard, a wall clock, a banker's lamp and a ticker machine.
- **It runs on real data:**
  - The chalkboard shows the account since the start, the lead over SPY and today's move.
  - The clock shows Eastern time, and the calendar crosses off the contest's trading days.
  - The ticker arrows follow the stocks Midas watches.
  - He toasts when Midas buys one of his picks, sweats on a day down 3% or more,
    frowns when his requests are turned down, and dozes when the market is closed.
  - His speech line is the first sentence of his latest note, or a short line
    of his own when there is no fresh note.
- **His picks are now trade requests:** each one appears as a typed slip that
  Midas stamps APPROVED, DENIED (with the reason) or PENDING.
- **A fix:** after a bot restart the page used to show his picks as
  "waiting" even when Midas had already acted on them. It now falls back to
  the verdicts in his desk feed.
- **Effect on trading:** None.

### Mon Nov 23, 2026, 2:30 pm: Chasing the upside, and buying the dip
- **Why now:** SPY jumped 4.6% and all 16 stocks rose, but the market's mood
  still read "falling", so Midas bought $74,085 of new puts into the rally.
  The team decided to go for maximum profit and accept the risk of losing
  the sleeve.
- **What we found:** We priced Midas's real signals with real option prices
  from March 2024 on, holding each bet six trading days. In falling markets,
  puts on the weakest stocks averaged -15%. Calls on those same stocks
  averaged +22.5%, and doubled about twice as often (19% against 10%).
- **What changed:**
  1. **In a falling market Midas now buys calls on the most beaten-down
     stocks** instead of puts on them. The puts it already holds stay.
  2. **The lead lock is off.** It no longer limits bets or closes everything
     if the lead over SPY disappears.
  3. **Shorter options:** about 14 days to expiry instead of 21.
  4. **A wide stop:** main bets are sold at -80% instead of -37.5%. This
     cancels Dionysus's tighter stop, which had started today, and he can no
     longer set one tighter than -65%.
  5. **Held longer:** main bets are sold two days before expiry instead of four.
  6. **Smaller minimum bet:** a quarter of a full-size bet instead of half, so
     the little cash left can still be used.
- **The result on real prices:** the average bet went from +5.5% to +21.3%,
  and the chance of doubling from 14% to 18%. The chance of losing at least
  half went from 37% to 53%, so this is a riskier strategy on purpose.
- **What could go wrong:** The price data covers 2024 to 2026, when dips
  mostly recovered. It was also used to choose these settings, so the results
  are flattering. In 2025 the new setup did no better than the old one
  (-3.1% against -1.6%). A long decline like 2022 would hurt dip calls badly.
- **Still in place:** the $15,000 kill switch, the limit to the account's real
  cash (no borrowing against teammates' money), the earnings rule, and
  selling everything by 3:00 pm on December 2.

### Mon Nov 23, 2026, 2:45 pm: Midas decides whether to hold or switch its puts
- **What:** While the market reads "falling", Midas now makes its own call on
  each put it still holds:
  - **Up less than 50%:** sell it and buy a call on the same stock, as long as
    the stock is still beaten down and a suitable call is available.
  - **Up 50% or more:** hold it and let the normal selling rules run.
  It switches one put a minute, starting with the worst, and each stock at
  most once a day. It stops switching three days before the contest ends.
- **Why:** The team asked Midas to do whatever makes the most profit. We tested
  102 real past cases of a put held five days in a market still falling, over
  the next six trading days. For puts up less than 50% (59 cases), holding
  averaged -37% and switching +59%, and switching won 64% of the time. For
  bigger winners (43 cases) switching won only 47% of the time, so they stay.
- **How much to trust it:** It is a small sample. Three huge winners lift the
  +59%; without them switching averaged +16.5%, still ahead of holding. In
  2026 alone, switching won less than half the time.
- **First decisions:** Midas would switch AMD, COIN, AVGO and MSFT (about
  $72,000) and hold MSTR and NFLX, which are up 265% and 158%.

### Tue Nov 24, 2026, 6:15 pm: The daily record failed once (no rule change)
- **What happened:** GitHub's daily job failed at 5:49 pm. That morning the Mac
  mini had saved four files containing git conflict markers, left behind when
  its update clashed with GitHub's own changes. The job could not read them.
  Trading was not affected.
- **Fixed:** the four files were cleaned, keeping GitHub's final copies. The
  Mac mini now sets its own leftover edits aside instead of mixing them in,
  neither machine will save a file with conflict markers in it, and the daily
  job skips damaged rows instead of stopping.

## Changes Dionysus made to Midas's settings

Written automatically. Dionysus may change one setting a day, inside hard limits that Midas checks itself (see TUNING_LIMITS in config.py). A change starts the next trading day; a person can veto it before then with `mac_mini/veto.sh DIAL`, and it is undone automatically if the three-week trades opened after it clearly lose.

- **2026-11-18**: Dionysus set CORE_TRAIL_FROM from 1.0 to 1.25, starting 2026-11-20. Start trailing later so winners run longer; aligns with note about cutting winners early.
- **2026-11-20**: Dionysus set CORE_STOP from -0.5 to -0.375, starting 2026-11-23. The stop loss trade lost -62%, far worse than the -50% stop. Tightening to -0.375 reduces potential loss. Evidence: "average -62%" Second look: The record shows the sole stop‑loss trade lost -62%, so raising the stop‑loss threshold to -37.5% would reduce potential loss.
- **2026-11-23**: a person vetoed CORE_STOP -0.5 to -0.375.
- **2026-11-23**: undid CORE_TRAIL_FROM 1.0 to 1.25 automatically: the 5 three-week trades opened since it began averaged -19%, against +41% before.

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
| 2026-11-13 | $122,912 | +3.21% | $74,425 | +5.81% | +$24,425 | -0.38% | +2.57% | 8 PLTR 11/27 172.5P (-0%), 7 COIN 11/27 140P (+48%), 6 MSTR 12/04 125P (+46%), 3 MSFT 12/04 540P (+10%), 46 NFLX 12/04 63P (+14%) | Sold 2 AMD 12/04 565C at $31.00 (-$50); Bought 17 QQQ 11/13 679P at $2.50; Sold 8 QQQ 11/13 679P at $5.22 (+$2,176); Sold 9 QQQ 11/13 679P at $4.50 (+$1,800) |
| 2026-11-16 | $141,024 | +14.74% | $93,759 | +25.98% | +$43,759 | -1.89% | +0.63% | 8 PLTR 11/27 172.5P (+67%), 4 COIN 11/27 140P (+113%), 3 MSTR 12/04 125P (+109%), 3 MSFT 12/04 540P (+20%), 46 NFLX 12/04 63P (+57%), 6 QQQ 12/04 673P (+33%) | Sold 3 MSTR 12/04 125P at $19.45 (+$2,565); Sold 3 COIN 11/27 140P at $18.60 (+$2,760); Bought 6 QQQ 12/04 673P at $17.37; Bought 25 SPY 11/16 745P at $2.03; Sold 25 SPY 11/16 745P at $1.96 (-$175) |
| 2026-11-17 | $162,719 | +15.38% | $115,922 | +23.64% | +$65,922 | -1.03% | -0.41% | 4 PLTR 11/27 172.5P (+94%), 4 COIN 11/27 140P (+156%), 3 MSTR 12/04 125P (+157%), 2 MSFT 12/04 540P (+101%), 23 NFLX 12/04 63P (+98%), 6 QQQ 12/04 673P (+61%), 15 GOOGL 12/11 280P (-2%), 5 META 12/11 625P (+0%), 3 AMD 12/11 505P (-10%) | Bought 30 SPY 11/17 735P at $1.88; Sold 15 SPY 11/17 735P at $3.84 (+$2,940); Sold 1 MSFT 12/04 540P at $38.65 (+$1,865); Sold 4 PLTR 11/27 172.5P at $16.30 (+$3,060); Sold 15 SPY 11/17 735P at $5.34 (+$5,190); Sold 23 NFLX 12/04 63P at $3.70 (+$4,002); Bought 15 GOOGL 12/11 280P at $10.75; Bought 5 META 12/11 625P at $30.00; Bought 3 AMD 12/11 505P at $48.25 |
| 2026-11-18 | $156,697 | -3.70% | $109,911 | -5.19% | +$59,911 | -0.28% | -0.69% | 4 PLTR 11/27 172.5P (+92%), 4 COIN 11/27 140P (+205%), 3 MSTR 12/04 125P (+215%), 2 MSFT 12/04 540P (+91%), 23 NFLX 12/04 63P (+82%), 6 QQQ 12/04 673P (+55%), 15 GOOGL 12/11 280P (-22%), 5 META 12/11 625P (+11%) | Bought 23 SPY 11/18 727P at $1.98; Sold 23 SPY 11/18 727P at $0.98 (-$2,300); Sold 3 AMD 12/11 505P at $29.60 (-$5,595) |
| 2026-11-19 | $160,685 | +2.54% | $115,098 | +4.72% | +$65,098 | -1.98% | -2.66% | 4 PLTR 11/27 172.5P (+117%), 4 COIN 11/27 140P (+220%), 3 MSTR 12/04 125P (+250%), 23 NFLX 12/04 63P (+128%), 6 QQQ 12/04 673P (+89%), 5 META 12/11 625P (+31%), 20 NVDA 12/11 145P (+48%), 3 AMD 12/11 455P (-12%) | Sold 2 MSFT 12/04 540P at $22.35 (+$470); Sold 15 GOOGL 12/11 280P at $4.10 (-$9,975); Bought 18 SPY 11/19 728P at $3.06; Sold 18 SPY 11/19 728P at $3.02 (-$72); Bought 20 NVDA 12/11 145P at $4.95; Bought 3 AMD 12/11 455P at $30.05 |
| 2026-11-20 | $238,173 | +48.22% | $195,400 | +69.77% | +$145,400 | -3.51% | -6.08% | 4 PLTR 11/27 172.5P (+197%), 4 COIN 11/27 140P (+304%), 3 MSTR 12/04 125P (+334%), 23 NFLX 12/04 63P (+209%), 3 QQQ 12/04 673P (+250%), 5 META 12/11 625P (+112%), 10 NVDA 12/11 145P (+344%), 3 AMD 12/11 455P (+87%), 16 SPY 12/11 685P (+48%) | Bought 6 QQQ 11/20 633P at $4.38; Sold 3 QQQ 11/20 633P at $8.82 (+$1,332); Sold 3 QQQ 11/20 633P at $5.85 (+$441); Sold 3 QQQ 12/04 673P at $51.57 (+$10,260); Bought 16 SPY 12/11 685P at $11.78; Sold 10 NVDA 12/11 145P at $14.90 (+$9,950) |
| 2026-11-23 | $148,528 | -37.64% | $101,563 | -48.02% | +$51,563 | +4.62% | -1.75% | 3 MSTR 12/04 125P (+274%), 23 NFLX 12/04 63P (+144%), 16 PLTR 12/04 165C (+15%), 8 META 12/07 625C (+1%), 68 COIN 12/04 116C (-10%), 8 AMD 12/04 487.5C (-4%), 24 AVGO 12/04 330C (-9%) | Sold 4 PLTR 11/27 172.5P at $13.35 (+$1,880); Sold 4 COIN 11/27 140P at $27.10 (+$7,080); Sold 3 QQQ 12/04 673P at $24.11 (+$2,022); Sold 3 AMD 12/11 455P at $30.20 (+$45); Sold 16 SPY 12/11 685P at $5.52 (-$10,016); Sold 10 NVDA 12/11 145P at $2.38 (-$2,570); Bought 21 MSFT 12/11 487.5P at $11.25; Bought 38 COIN 12/11 105P at $6.25; Bought 4 AMD 12/11 430P at $27.90; Sold 5 META 12/11 625P at $41.55 (+$5,775); Bought 10 AVGO 12/11 297.5P at $15.55; Bought 16 PLTR 12/04 165C at $3.90; Sold 4 AMD 12/11 430P at $24.20 (-$1,480); Bought 8 META 12/07 625C at $11.20; Bought 68 COIN 12/04 116C at $3.15; Sold 38 COIN 12/11 105P at $5.50 (-$2,850); Sold 10 AVGO 12/11 297.5P at $13.65 (-$1,900); Bought 8 AMD 12/04 487.5C at $15.90; Sold 21 MSFT 12/11 487.5P at $10.50 (-$1,575); Bought 24 AVGO 12/04 330C at $8.35 |
| 2026-11-24 | $113,841 | -23.35% | $67,959 | -33.09% | +$17,959 | -0.51% | -2.24% | 1 MSTR 12/04 125P (+326%), 23 NFLX 12/04 63P (+122%), 16 PLTR 12/04 165C (+22%), 8 META 12/07 625C (-33%), 68 COIN 12/04 116C (-65%), 8 AMD 12/04 487.5C (-69%), 24 AVGO 12/04 330C (-51%), 13 QQQ 12/08 660C (-18%) | Sold 2 MSTR 12/04 125P at $42.45 (+$6,310); Bought 13 QQQ 12/08 660C at $8.41; Bought 2 QQQ 11/24 634P at $3.48; Sold 2 QQQ 11/24 634P at $1.73 (-$350) |
| 2026-11-25 | $88,317 | -22.42% | $43,223 | -36.40% | -$6,777 | -0.30% | -2.54% | Nothing | Sold 1 MSTR 12/04 125P at $48.25 (+$3,735); Sold 23 NFLX 12/04 63P at $4.85 (+$6,647); Sold 16 PLTR 12/04 165C at $2.36 (-$2,464); Sold 8 META 12/07 625C at $2.71 (-$6,792); Sold 68 COIN 12/04 116C at $0.54 (-$17,748); Sold 8 AMD 12/04 487.5C at $1.01 (-$11,912); Sold 24 AVGO 12/04 330C at $1.61 (-$16,176); Sold 13 QQQ 12/08 660C at $2.58 (-$7,579) |
