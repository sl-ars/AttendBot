from dataclasses import dataclass
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    tg_chat_id: str = os.environ["TG_CHAT_ID"]
    tg_bot_token: str = os.environ["TG_BOT_TOKEN"]
    # One-time seed values for the state file (see app/store.py); the state
    # file is the source of truth once it exists. No code-level defaults —
    # BASE_URL lives in .env / Coolify env UI.
    wsp_login: Optional[str] = os.getenv("WSP_LOGIN") or None
    wsp_password: Optional[str] = os.getenv("WSP_PASSWORD") or None
    base_url: Optional[str] = os.getenv("BASE_URL") or None
    remote_url: str = os.getenv("REMOTE_URL", "http://selenium:4444/wd/hub")
    state_path: str = os.getenv("STATE_PATH", "state.json")

def get_settings() -> Settings:
    return Settings()
