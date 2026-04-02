"""Configuration — ligues cibles, seuils de décision, constantes."""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Secrets ────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "499940076"))
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")

# ── Scan ───────────────────────────────────────────────────────
SCAN_INTERVAL = 120  # secondes (2 minutes)

# ── Sofascore ──────────────────────────────────────────────────
SOFASCORE_API = "https://api.sofascore.com/api/v1"

# Ligues cibles — mapping nom Sofascore (slug ou fragment) → label affiché
# Sofascore utilise uniqueCategory.name et tournament.name
TARGET_LEAGUES = {
    # Turquie
    "bsl": "Turquie BSL",
    "super lig": "Turquie Süper Lig",
    "türkiye sigorta basketbol süper ligi": "Turquie BSL",
    "turkish basketball": "Turquie BSL",
    # Géorgie
    "georgia": "Géorgie",
    "superliga": "Géorgie",
    # Roumanie
    "liga nationala": "Roumanie Div A",
    "romania": "Roumanie Div A",
    # Danemark
    "basketligaen": "Danemark",
    "denmark": "Danemark",
    # Arabie Saoudite
    "saudi": "Arabie Saoudite",
    "sbl": "Arabie Saoudite",
    # Pologne
    "polish basketball league": "Pologne BBL",
    "plk": "Pologne BBL",
    "energa basket liga": "Pologne BBL",
    # Australie
    "nbl": "NBL Australie",
    "nbl1": "NBL1 Australie",
    "australia": "Australie",
    # FIBA
    "fiba": "FIBA",
    "basketball champions league": "FIBA BCL",
    # Japon
    "b.league": "Japon B League",
    "b league": "Japon B League",
    "b2 league": "Japon B2",
    "japan": "Japon",
    # Bulgarie
    "nbl bulgaria": "Bulgarie NBL",
    "bulgaria": "Bulgarie NBL",
    # Europe
    "euroleague": "Euroligue",
    "eurocup": "Eurocoupe",
    # Corée
    "kbl": "Corée KBL",
    "wkbl": "Corée WKBL",
    "korean basketball": "Corée KBL",
    # Chine
    "cba": "CBA Chine",
    "chinese basketball": "CBA Chine",
    # Finlande
    "korisliiga": "Finlande Korisliiga",
    "finland": "Finlande",
}

# ── Seuils de verdict ─────────────────────────────────────────
GAP_STRONG = 8.0        # GAP >= 8 → signal fort OVER/UNDER
GAP_WEAK = 3.0          # GAP < 3 → PASSER
SHOOTING_HIGH = 65.0    # FG% > 65% → régression attendue (UNDER)
FOULS_HIGH = 18          # Fautes combinées > 18 → lancers à venir (OVER)
ML_BLOWOUT = 1.30       # ML favori < 1.30 → favori écrasant → PASSER si GAP faible

# ── The Odds API ───────────────────────────────────────────────
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
# Sports keys pour The Odds API (basket)
ODDS_API_SPORTS = [
    "basketball_euroleague",
    "basketball_nba",
    "basketball_nbl",
    "basketball_turkey_bsl",
    "basketball_korea_kbl",
    "basketball_china_cba",
    "basketball_japan_b_league",
]
