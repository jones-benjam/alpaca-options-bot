"""All strategy dials in one place. Any value can be overridden with an
environment variable of the same name (handy on a cloud host)."""
import os


def _env(name, default, cast=str):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    if cast is bool:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return cast(raw)


# ---- Sleeve -----------------------------------------------------------------
# The money the bot manages. Each step is (first trading day in effect, total).
# Add a step when the sleeve is resized so the daily record stays correct.
SLEEVE_STEPS = [("2026-11-09", 25_000.0), ("2026-11-11", 50_000.0)]
SLEEVE_START = _env("SLEEVE_START", SLEEVE_STEPS[-1][1], float)  # 50% of $100k
BOT_TAG = "optbot"              # prefix on every order the bot places
START_DATE = _env("START_DATE", "2026-11-09")  # ledger counts bot orders from here
END_DATE = _env("END_DATE", "2026-12-02")  # last day: no new trades, flat by 15:00 ET
KILL_FLOOR_PCT = _env("KILL_FLOOR_PCT", 0.30, float)  # halt if sleeve <= 30% of start

# ---- Universe ---------------------------------------------------------------
INDEX = ["SPY", "QQQ"]  # these two set the market regime
UNIVERSE = [
    "SPY", "QQQ", "IWM",
    "NVDA", "TSLA", "AMD", "META", "AMZN", "AAPL", "MSFT", "GOOGL",
    "AVGO", "NFLX", "PLTR", "COIN", "MSTR",
]
PENNY_ALL = {"SPY", "QQQ", "IWM"}  # options quoted in $0.01 at every price

# ---- Core: short-dated momentum options --------------------------------------
# Profits are reinvested: each bet is a share of the sleeve as it stands now, and
# cash freed by sales funds new bets for as long as it lasts, up to this many.
CORE_SLOTS = _env("CORE_SLOTS", 10, int)
CORE_MIN_BET_SHARE = 0.5         # skip a new bet smaller than half a full-size one
CORE_SLOT_PCT = _env("CORE_SLOT_PCT", 0.20, float)  # of sleeve equity, per slot
CORE_MIN_STRENGTH = 0.02    # skip names with under 2% blended momentum
CORE_DTE_MIN = 14
CORE_DTE_MAX = 35
CORE_DTE_TARGET = 21
CORE_DELTA = 0.35           # about 5% out of the money: cheaper, bigger payoff on a big move
CORE_DELTA_TOL = 0.15
CORE_STOP = -0.50           # exit at -50% of premium
CORE_TP1 = 2.00             # at +200% sell half (let winners run) ...
CORE_TRAIL_FROM = 1.00      # ... and once a bet has been up 100% ...
CORE_TRAIL = 0.40           # ... exit if it falls 40% from its best price
CORE_MIN_DTE_EXIT = 4       # never hold into the final days
CORE_MAX_SPREAD = 0.15      # skip contracts with spread > 15% of mid
CORE_ENTRY_FROM = "09:45"   # Eastern time
CORE_ENTRY_TO = "15:45"
FLIP_CHECK_FROM = "15:30"   # trend-flip exits are judged near the close

# ---- Earnings ----------------------------------------------------------------
# Options get expensive before an earnings report and lose that extra value the
# moment it is out, and the stock can gap either way. For each stock reporting
# before END_DATE: the last trading day it is safe to hold (the report comes
# out after that day's close). Dates must come from the company's own notice.
#   NVDA: reports Tue 2026-11-17 after the close (Nvidia press release).
#   AVGO: expected about 2026-12-10, after END_DATE. The other names reported
#   in late October / early November and next report in 2027.
EARNINGS_EXIT_BY = {"NVDA": "2026-11-17"}
EARNINGS_BLACKOUT_DAYS = 5       # no new bet this many calendar days before
HOLD_THROUGH_EARNINGS = _env("HOLD_THROUGH_EARNINGS", False, bool)

# ---- Satellite: 0DTE opening-range breakout ----------------------------------
ODTE_ENABLED = _env("ODTE_ENABLED", True, bool)
ODTE_SYMBOLS = ["SPY", "QQQ"]
ODTE_RISK_PCT = _env("ODTE_RISK_PCT", 0.06, float)  # premium per trade, of equity
ODTE_MAX_PER_DAY = _env("ODTE_MAX_PER_DAY", 1, int)  # SPY and QQQ move together
ODTE_WITH_REGIME = _env("ODTE_WITH_REGIME", True, bool)  # never trade against the trend
ODTE_OTM = 0.0015           # strike about 0.15% out of the money
ODTE_BREAK_BUFFER = 0.0005  # price must clear the range by 0.05%
ODTE_STOP = -0.50
ODTE_TP1 = 1.00
ODTE_TRAIL = 0.35
ODTE_MAX_SPREAD = 0.25
ODTE_ENTRY_FROM = "10:00"
ODTE_ENTRY_TO = "14:00"
ODTE_EXIT_AT = "15:00"      # flat well before expiry

# ---- Dionysus, the AI trader (core engine only) -------------------------------
# Two names, so it is always clear who did what: Midas is this bot and its fixed
# rules; Dionysus is the AI trader (a local model on the Mac mini, trader.py).
# Each evening Dionysus suggests up to three trades from the day's signals, with a
# conviction of 1-5. The next trading day Midas tries those first, but only if its
# own rules still approve them; it never buys anything the rules reject, and
# sizing, stops and every guard rail are unchanged. AI_PICKS=0 turns this off.
AI_PICKS = _env("AI_PICKS", True, bool)
AI_TRADER = _env("AI_TRADER", "Dionysus")       # whose picks count (others only add agreement)
AI_TRADER_ALIASES = _env("AI_TRADER_ALIASES", "Midas")  # his earlier name, on picks made before Nov 19
AI_MIN_CONVICTION = _env("AI_MIN_CONVICTION", 3, int)  # weaker picks are ignored
AI_PICKS_URL = _env(
    "AI_PICKS_URL",
    "https://raw.githubusercontent.com/jones-benjam/alpaca-options-bot/main/memory/shadow_picks.csv",
)
AI_MAX_AGE_DAYS = 4             # older picks are stale (covers a long weekend)
AI_REFRESH_SECONDS = 900        # look again this often until the day's picks arrive

# Freeing cash for a strong pick. Dionysus may name up to two of Midas's open
# three-week bets that are in profit, to sell if cash (or lead-lock room) is what
# stops a pick. Midas sells only when ALL of these hold: the pick is rated
# AI_FREE_UP_MIN_CONVICTION or more and its rules approve it; a contract for it
# passed the checks; money is the only thing in the way; the named bet is up at
# least AI_FREE_UP_MIN_GAIN with a believable quote; and the sale would free
# enough for a proper-size bet. It sells only as many contracts as needed, at
# most AI_FREE_UP_MAX_PER_DAY times a day. AI_FREE_UP=0 turns this off.
AI_FREE_UP = _env("AI_FREE_UP", True, bool)
AI_FREE_UP_MIN_CONVICTION = _env("AI_FREE_UP_MIN_CONVICTION", 4, int)
AI_FREE_UP_MIN_GAIN = _env("AI_FREE_UP_MIN_GAIN", 0.10, float)   # +10% or better on what was paid
AI_FREE_UP_MAX_PER_DAY = _env("AI_FREE_UP_MAX_PER_DAY", 1, int)
AI_FREE_UP_URL = _env(
    "AI_FREE_UP_URL",
    "https://raw.githubusercontent.com/jones-benjam/alpaca-options-bot/main/memory/free_up.csv",
)


# Dionysus may change Midas's settings. Each evening he may set ONE of the dials
# below to a new value, taking effect the next trading day; a person can veto it
# before then (mac_mini/veto.sh), and the Mac mini undoes a change automatically
# if the three-week trades opened after it clearly lose. Midas re-checks every
# value itself: it must lie inside the hard limits here and move at most one step
# from the value before it, and at most one change may start on a given day.
# Anything else in the file is ignored. Only these dials: the kill switch, the
# lead lock, the end date, the same-day engine and the safety checks are not on
# the list. AI_TUNING=0 turns this off and restores every value above.
AI_TUNING = _env("AI_TUNING", True, bool)
AI_TUNING_URL = _env(
    "AI_TUNING_URL",
    "https://raw.githubusercontent.com/jones-benjam/alpaca-options-bot/main/memory/dials.json",
)
# dial: (lowest, highest, largest step; None means 25% of the value before it)
TUNING_LIMITS = {
    "CORE_MIN_STRENGTH": (0.01, 0.06, None),
    "CORE_DELTA": (0.20, 0.50, None),
    "CORE_DTE_TARGET": (14, 30, 4),
    "CORE_STOP": (-0.65, -0.35, None),
    "CORE_TP1": (1.00, 3.00, None),
    "CORE_TRAIL_FROM": (0.50, 2.00, None),
    "CORE_TRAIL": (0.25, 0.55, None),
    "CORE_SLOTS": (6, 12, 2),
    "CORE_SLOT_PCT": (0.10, 0.25, None),
    "AI_MIN_CONVICTION": (3, 5, 1),
}
TUNING_MIN_CLOSED_TRADES = 8      # no change until the bot has closed this many trades
TUNING_COOLDOWN_DAYS = 5          # a dial changed or undone is left alone this many days


def tuning_step_ok(dial, old, new):
    """Is `new` inside the hard limits and no more than one step from `old`?"""
    lo, hi, step = TUNING_LIMITS[dial]
    if not lo <= new <= hi or new == old:
        return False
    return abs(new - old) <= (step if step is not None else abs(old) * 0.25) + 1e-9


def ai_names():
    """Every name Dionysus's own picks may carry (his current and earlier names)."""
    return {AI_TRADER} | {n.strip() for n in AI_TRADER_ALIASES.replace(",", " ").split() if n.strip()}

# ---- Engine -----------------------------------------------------------------
LOOP_SECONDS = _env("LOOP_SECONDS", 60, int)
ODTE_LOOP_SECONDS = _env("ODTE_LOOP_SECONDS", 10, int)  # while a 0DTE position is open
HEARTBEAT_SECONDS = 300     # how often the status line is logged

# ---- Safety ------------------------------------------------------------------
EXIT_CONFIRMATIONS = 2      # passes a stop / trailing exit must persist before selling
KILL_CONFIRMATIONS = 3      # passes under the kill floor before flattening
MAX_TRIGGER_SPREAD = 0.50   # ignore quotes wider than this (of mid) for price exits
# Early-close days (for example the Friday after Thanksgiving): the clock-time
# rules above also fire this many minutes before the actual close.
ODTE_ENTRY_MIN_TO_CLOSE = 120
ODTE_EXIT_MIN_TO_CLOSE = 60
FLIP_MIN_TO_CLOSE = 30
CORE_ENTRY_MIN_TO_CLOSE = 15
MAX_ENTRY_ATTEMPTS = 3      # per symbol per day
QUOTE_MAX_AGE_SEC = 900     # ignore option quotes older than this
MIN_OPTION_ASK = 0.20
STATE_FILE = _env("STATE_FILE", "")

# ---- Lead lock: protects the win over SPY ----------------------------------------
# The class is graded on whether the whole account beats SPY. The lock keeps a
# floor under that: SPY's return since the start, plus a margin. The bot may hold
# options worth up to LOCK_MULTIPLIER times the account's cushion above the floor.
# A shrinking cushion stops new bets; if it is gone, the bot closes everything.
LOCK_ENABLED = _env("LOCK_ENABLED", True, bool)
LOCK_START_VALUE = 100_000.0     # the whole account at the start
LOCK_MARGIN_PCT = 0.05           # stay at least 5 points ahead of SPY
LOCK_MULTIPLIER = _env("LOCK_MULTIPLIER", 2.0, float)
