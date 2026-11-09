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
SLEEVE_START = _env("SLEEVE_START", 25_000.0, float)  # the bot's 25% of $100k
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
CORE_SLOTS = _env("CORE_SLOTS", 3, int)
CORE_SLOT_PCT = _env("CORE_SLOT_PCT", 0.28, float)  # of sleeve equity, per slot
CORE_MIN_STRENGTH = 0.02    # skip names with under 2% blended momentum
CORE_DTE_MIN = 14
CORE_DTE_MAX = 35
CORE_DTE_TARGET = 21
CORE_DELTA = 0.50           # at the money: the most gamma per dollar
CORE_DELTA_TOL = 0.15
CORE_STOP = -0.50           # exit at -50% of premium
CORE_TP1 = 1.00             # at +100% sell half ...
CORE_TRAIL = 0.30           # ... then exit the rest 30% off its peak
CORE_MIN_DTE_EXIT = 4       # never hold into the final days
CORE_MAX_SPREAD = 0.15      # skip contracts with spread > 15% of mid
CORE_ENTRY_FROM = "09:45"   # Eastern time
CORE_ENTRY_TO = "15:45"
FLIP_CHECK_FROM = "15:30"   # trend-flip exits are judged near the close

# ---- Satellite: 0DTE opening-range breakout ----------------------------------
ODTE_ENABLED = _env("ODTE_ENABLED", True, bool)
ODTE_SYMBOLS = ["SPY", "QQQ"]
ODTE_RISK_PCT = _env("ODTE_RISK_PCT", 0.06, float)  # premium per trade, of equity
ODTE_OTM = 0.0015           # strike about 0.15% out of the money
ODTE_BREAK_BUFFER = 0.0005  # price must clear the range by 0.05%
ODTE_STOP = -0.50
ODTE_TP1 = 1.00
ODTE_TRAIL = 0.35
ODTE_MAX_SPREAD = 0.25
ODTE_ENTRY_FROM = "10:00"
ODTE_ENTRY_TO = "14:00"
ODTE_EXIT_AT = "15:00"      # flat well before expiry

# ---- Engine -----------------------------------------------------------------
LOOP_SECONDS = _env("LOOP_SECONDS", 60, int)
ODTE_LOOP_SECONDS = _env("ODTE_LOOP_SECONDS", 10, int)  # while a 0DTE position is open
HEARTBEAT_SECONDS = 300     # how often the status line is logged
MAX_ENTRY_ATTEMPTS = 3      # per symbol per day
QUOTE_MAX_AGE_SEC = 900     # ignore option quotes older than this
MIN_OPTION_ASK = 0.20
STATE_FILE = _env("STATE_FILE", "")
