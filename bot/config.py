"""Configuration du bot — charge les variables d'environnement."""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "499940076"))

# Sofascore
SOFASCORE_BASE = "https://www.sofascore.com"
SOFASCORE_API = "https://api.sofascore.com/api/v1"

# Seuils de décision
EV_THRESHOLD = 0.03        # EV minimum pour émettre un signal (3 %)
GAP_MIN_POINTS = 3.0       # Écart minimum vs ligne pour considérer un signal
PACE_LEAGUE_BASE = 165.0   # Points par match — base NBA/Euroleague

# Intervalle de scan (secondes)
SCAN_INTERVAL = 90
