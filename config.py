"""
config.py — Central configuration for the patent defect ingestion pipeline.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "patent_defects.duckdb"
CHECKPOINT_FILE = DATA_DIR / "checkpoint.json"

# ---------------------------------------------------------------------------
# Target CPC class prefixes
# ---------------------------------------------------------------------------
CPC_CLASSES = ["G06F", "H04L", "H01L", "G06N"]

# Per-class record target (4 classes × 15,000 = 60,000 total)
DEFAULT_LIMIT_PER_CLASS = 15_000

# ---------------------------------------------------------------------------
# USPTO PEDS API
# ---------------------------------------------------------------------------
PEDS_BASE_URL = "https://ped.uspto.gov/api/queries"
PEDS_TIMEOUT = 30          # seconds per request
PEDS_PAGE_SIZE = 500       # records per page (API max)
PEDS_RATE_LIMIT = 8        # max concurrent requests

# ---------------------------------------------------------------------------
# PatentsView API
# ---------------------------------------------------------------------------
PATENTSVIEW_BASE_URL = "https://api.patentsview.org/patents/query"
PATENTSVIEW_TIMEOUT = 30
PATENTSVIEW_PAGE_SIZE = 1_000   # API allows up to 10,000 but 1k is safe
PATENTSVIEW_RATE_LIMIT = 5

# ---------------------------------------------------------------------------
# Retry / backoff
# ---------------------------------------------------------------------------
MAX_RETRIES = 5
BACKOFF_BASE = 2.0         # exponential backoff multiplier (seconds)
BACKOFF_MAX = 60.0         # cap on retry wait time (seconds)

# ---------------------------------------------------------------------------
# Statutory rejection markers
# (matched case-insensitively against Office Action text)
# ---------------------------------------------------------------------------
REJECTION_MARKERS = {
    "§112": [
        r"35\s+U\.?S\.?C\.?\s*[§Ss]?\s*112",
        r"35\s+USC\s+112",
        r"indefiniteness",
        r"lack\s+of\s+antecedent\s+basis",
        r"antecedent\s+basis",
        r"written\s+description",
        r"enablement",
    ],
    "§102": [
        r"35\s+U\.?S\.?C\.?\s*[§Ss]?\s*102",
        r"35\s+USC\s+102",
        r"anticipat(?:ed|ion)",
        r"prior\s+art\s+discloses",
        r"teaches\s+each\s+(?:element|limitation)",
    ],
    "§103": [
        r"35\s+U\.?S\.?C\.?\s*[§Ss]?\s*103",
        r"35\s+USC\s+103",
        r"obvious(?:ness|ly)",
        r"would\s+have\s+been\s+obvious",
        r"obvious\s+to\s+(?:one|a person)\s+(?:of\s+)?(?:ordinary\s+)?skill",
        r"prima\s+facie\s+obvious",
    ],
}

# Sentence window around a detected rejection (characters)
RATIONALE_WINDOW = 800

# ---------------------------------------------------------------------------
# Claim phrase extraction
# ---------------------------------------------------------------------------
# Regex to identify claim language in OA text
CLAIM_PHRASE_PATTERNS = [
    r'[Cc]laim\s+\d+[,\s]+(?:particularly\s+)?(?:the\s+)?(?:language|phrase|term|limitation|element)\s+"([^"]{10,200})"',
    r'"([^"]{10,200})"\s+(?:in\s+)?(?:claim|Claim)\s+\d+',
    r'[Cc]laim\s+\d+\s+recites\s+"([^"]{10,200})"',
    r'[Cc]laim\s+\d+[,\s]+(?:the\s+)?(?:phrase|term|language)\s+"([^"]{10,200})"',
    r'[Tt]he\s+(?:phrase|term|limitation)\s+"([^"]{10,200})"',
]

# Amended claim detection in response documents
AMENDMENT_MARKERS = [
    r"[Aa]mend(?:ed|ment)",
    r"[Cc]ancelled\s+and\s+replaced",
    r"[Rr]eplaced\s+with",
    r"[Cc]laim\s+\d+\s+is\s+amended",
]
