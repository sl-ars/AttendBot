import requests

class TelegramClient:
    def __init__(self, bot_token: str, chat_id: str, timeout: int = 10) -> None:
        self.base = f"https://api.telegram.org/bot{bot_token}"
        self.chat_id = chat_id
        self.timeout = timeout

    def send_message(self, text: str) -> None:
        url = f"{self.base}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        r = requests.post(url, json=payload, timeout=self.timeout)
        r.raise_for_status()
