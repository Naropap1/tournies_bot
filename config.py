"""
Central configuration for Tournies Bot.
Loads secrets from .env and exports constants used across the project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

# --- Secrets ---
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
STARTGG_TOKEN: str = os.getenv("STARTGG_TOKEN", "")

# --- Bot Settings ---
COMMAND_PREFIX: str = "!"
BOT_DESCRIPTION: str = "Tournies Bot — Automated tournament scheduling & bracket management."

# --- Database ---
DB_PATH: str = str(Path(__file__).parent / "tournies.db")

# --- Start.gg API ---
STARTGG_API_URL: str = "https://api.start.gg/gql/alpha"
STARTGG_RATE_LIMIT: int = 80   # max requests per 60 seconds
STARTGG_RATE_WINDOW: int = 60  # seconds

# --- Tournament Defaults ---
DEFAULT_FREQUENCY: str = "monthly"
VALID_FREQUENCIES: list[str] = ["monthly", "quarterly", "bi-annually", "annually"]
MIN_ENTRANTS: int = 2

# --- Match Settings ---
BEST_OF_STANDARD: int = 3  # Bo3 for normal rounds
BEST_OF_FINALS: int = 5    # Bo5 for finals rounds

# --- Alert Timing (in hours before event) ---
ALERT_1_WEEK_HOURS: int = 168   # 7 days
ALERT_24_HOURS: int = 24
ALERT_CHECK_INTERVAL_MINUTES: int = 30  # how often the alert loop runs
