# Roadmap: Dionysus earns control of Midas

**The goal.** Keep this running long after the class project. Test many
strategies, build up years of data, and see whether Dionysus (the AI trader)
can find a better strategy than Midas's (the rules bot) and explain it in
plain words. Over time, Dionysus takes more control and runs strategies of his
own.

**The principle.** Dionysus gains control in stages. Each stage is unlocked by
evidence, not by the calendar. At every stage:

- Midas stays the risk layer. Hard limits live in Midas's code, not in
  anything the model writes, and Midas re-checks everything it is given.
- A person keeps a veto and an off switch.
- Every decision is written down: who made it, why, and how it turned out.

## Stage 0: Dionysus suggests (live since Nov 19, 2026)

- He picks up to three trades each evening. Midas tries those rated 3 or more
  first, if its rules approve them.
- He may name winners that Midas can sell part of to fund a pick rated 4 or 5.
- He writes a diary, desk notes and lessons, and reads back how his picks did.

## Stage 1: Dionysus tunes Midas (this change)

- Each evening he may change one of Midas's settings for the next trading day,
  such as the stop loss, bet size or days to expiry.
- Limits: hard floors, ceilings and step sizes in `config.py`
  (`TUNING_LIMITS`), checked by Midas itself. One change at a time, at most
  one a day, and each dial rests 5 days after a change.
- A person can veto with `mac_mini/veto.sh DIAL`, or turn it all off with
  `AI_TUNING=0`. A change is undone automatically if the three-week trades
  opened after it clearly lose.
- **Gate to stage 2:** the plumbing is proven over a few weeks with no
  unexplained changes.

## Stage 2: the strategy lab (next)

- Dionysus writes **strategy specs**: structured descriptions built from a
  menu of building blocks, with a plain-English explanation of the idea. The
  blocks include signal (momentum windows, trend filters, breakouts, mean
  reversion), direction rules, contract choice (days to expiry, how far out of
  the money), sizing and exits.
- Each spec is **backtested** on five years of prices (extending
  `backtest_signal.py`). It also runs as a **shadow strategy** on live data:
  it trades on paper inside the lab, never at the broker, and has its own
  scoreboard.
- His page gets a lab section: each strategy, its idea in his words, its
  backtest, and its live shadow record against Midas and against holding SPY.
- **Gate to stage 3:** a strategy beats Midas's own on both the backtest and
  at least 8 weeks and 30 trades of shadow results, after costs.

## Stage 3: promotion

- A strategy that passes the gate gets a small slice of the sleeve (for
  example 10%) as its own engine, with its own kill switch. Midas still
  enforces the account-wide limits.
- Its slice grows only as its live record holds up, and shrinks or ends if
  it doesn't.

## Stage 4: Dionysus runs the book

- He decides how the sleeve is split across proven strategies, retires ones
  that fade, and proposes new ones through the lab.
- Midas remains the risk layer: account-wide drawdown limit, position limits,
  quote sanity checks and the kill switch. The person keeps the off switch.

## Before trading past December 2, 2026

These are tied to the class contest and need deciding:

1. **End date:** `END_DATE` is Dec 2. Set a new one, or none.
2. **Account and sleeve:** the class account is shared with teammates. A
   separate paper account may be cleaner for a long-running experiment.
3. **Benchmark and lead lock:** the lead lock protects a lead over SPY for the
   contest's grade. Replace it with a long-term limit, such as a maximum
   drawdown, and keep comparing against holding SPY.
4. **History:** Midas rebuilds its record from Alpaca orders since
   `START_DATE`, and memory files grow every day. Plan for archiving.
5. **The model:** a larger local model makes fewer factual mistakes. Expect
   to upgrade as the Mac mini allows.
