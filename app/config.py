from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    wsp_login: str = os.environ["WSP_LOGIN"]
    wsp_password: str = os.environ["WSP_PASSWORD"]
    tg_chat_id: str = os.environ["TG_CHAT_ID"]
    tg_bot_token: str = os.environ["TG_BOT_TOKEN"]
    remote_url: str = os.getenv("REMOTE_URL", "http://selenium:4444/wd/hub")
    base_url: str = os.getenv("BASE_URL", "https://wsp.kbtu.kz/RegistrationOnline")
    schedule_path: str = os.getenv("SCHEDULE_PATH", "schedule.toml")

def get_settings() -> Settings:
    return Settings()
