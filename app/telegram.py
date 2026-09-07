"""Telegram transport built on pyTelegramBotAPI (telebot).

One shared TeleBot instance does everything: the command layer polls it via
``infinity_polling`` (daemon thread), and the attendance thread sends
notifications through this sync facade. Sends are plain blocking calls —
telebot is safe to call from any thread.

If the bot failed to initialize (e.g. malformed token), ``bot`` is None and
sends become logged no-ops — attendance must not depend on Telegram.
"""
import logging
from typing import Optional

import telebot

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send-only facade over the shared TeleBot instance."""

    def __init__(self, bot: Optional[telebot.TeleBot], chat_id: str) -> None:
        self._bot = bot
        self.chat_id = chat_id

    def send_message(self, text: str) -> None:
        if self._bot is None:
            logger.warning("Telegram disabled (bot not initialized); dropping message")
            return
        self._bot.send_message(self.chat_id, text)
