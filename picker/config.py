"""Central settings. Override with environment variables where noted."""
import os
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("PICKER_DB", ROOT / "data" / "predictions.db"))
UNIVERSE_CSV = Path(os.getenv("PICKER_UNIVERSE", ROOT / "data" / "universe.csv"))
HOLIDAYS_CSV = ROOT / "data" / "holidays.csv"
REPORT_DIR = ROOT / "reports"

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
DATA_READY = time(15, 45)  # daily bar is final by now

# Hugging Face model used to read news. Llama models are gated: accept the
# licence on the model page and export HF_TOKEN. Any chat/instruct model works.
LLM_MODEL = os.getenv("PICKER_LLM", "meta-llama/Llama-3.2-3B-Instruct")

# How the final score is blended (both parts are on a -1..+1 scale).
W_QUANT = 0.6
W_NEWS = 0.4
SHORTLIST = 10        # only the best N by pattern score get an LLM news read
TOP_LOGGED = 5        # rank 1 = the pick, ranks 2..N are "shadow" picks for stats
NEWS_HOURS = 72
MAX_HEADLINES = 8
LOW_CONVICTION = 0.15  # combined score below this is flagged as weak

# Expectation model (all heuristic, tracked so the tracker can judge them):
EXPECTED_MOVE_ATR_FRACTION = 0.5   # expected return = score * ATR% * this
TARGET_ATR_FRACTION = 0.5          # target / stop distance as a share of ATR%
P_UP_SENSITIVITY = 0.30            # p_up = 0.5 + this * score

BENCHMARK = "^NSEI"
