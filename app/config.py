import os
from pathlib import Path

XAI_API_KEY = os.environ["XAI_API_KEY"]
XAI_BASE_URL = "https://api.x.ai/v1"
XAI_MANAGEMENT_KEY = os.environ.get("XAI_MANAGEMENT_KEY", "")
XAI_TEAM_ID = os.environ.get("XAI_TEAM_ID", "")
XAI_MANAGEMENT_BASE_URL = "https://management-api.x.ai"
DATA_DIR = Path("/data")
DB_PATH = DATA_DIR / "grok_imagine.db"
VIDEOS_DIR = DATA_DIR / "videos"
POLL_INTERVAL_SECONDS = 5
MAX_POLL_DURATION_SECONDS = 600
