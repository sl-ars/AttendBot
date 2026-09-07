"""Telegram command semantics + transport wiring (pyTelegramBotAPI/telebot).

Layers:
- ``CommandProcessor.execute`` — pure command logic: parse text, mutate
  ``BotStore``, return the reply string. No Telegram types involved, so it is
  directly testable.
- ``create_telebot`` — builds the TeleBot instance and registers thin handler
  wrappers (commands, /schedule inline editor, sch:* callbacks). The library
  owns polling, retries and dispatch; only messages from the configured chat
  id are honored.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, Dict, Optional

import telebot

from . import schedule_ui
from .store import BotStore

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "🤖 Команды:\n"
    "/help — этот текст\n"
    "/status — состояние бота\n"
    "/login <логин> <пароль> — задать/сменить учётные данные WSP\n"
    "/url <адрес> — сменить страницу посещаемости\n"
    "/stop — приостановить отметки (браузер закроется)\n"
    "/start — возобновить отметки\n"
    "/schedule — редактор расписания"
)

UNKNOWN_CMD_REPLY = "Неизвестная команда. /help — список команд."


def _fmt_secs(s: int) -> str:
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м"
    return f"{sec}с"


class CommandProcessor:
    """Parses command text and applies it to the shared store."""

    def __init__(
        self,
        store: BotStore,
        wake: threading.Event,
        status_provider: Callable[[], Dict],
    ) -> None:
        self._store = store
        self._wake = wake
        self._status_provider = status_provider
        self._handlers: Dict[str, Callable[[str], str]] = {
            "/help": self._cmd_help,
            "/start": self._cmd_start,
            "/resume": self._cmd_start,
            "/stop": self._cmd_stop,
            "/pause": self._cmd_stop,
            "/status": self._cmd_status,
            "/login": self._cmd_login,
            "/url": self._cmd_url,
        }

    def execute(self, text: Optional[str]) -> Optional[str]:
        """Route one message; returns the reply, or None for non-commands."""
        text = (text or "").strip()
        if not text.startswith("/"):
            return None
        cmd = text.split(maxsplit=1)[0].lower()
        if "@" in cmd:  # "/status@my_bot" form
            cmd = cmd.split("@", 1)[0]
        handler = self._handlers.get(cmd)
        if handler is None:
            return UNKNOWN_CMD_REPLY
        try:
            return handler(text)
        except Exception:
            logger.exception("Command handler %s failed", cmd)
            return "⚠️ Внутренняя ошибка команды (подробности в логах)."

    # ---------- handlers ----------

    def _cmd_help(self, _text: str) -> str:
        return HELP_TEXT

    def _cmd_stop(self, _text: str) -> str:
        self._store.paused = True
        self._wake.set()
        return "⏸ Отметки приостановлены, браузер закроется. /start — возобновить."

    def _cmd_start(self, _text: str) -> str:
        self._store.paused = False
        self._wake.set()
        if not self._store.snapshot().wsp_login:
            return "▶️ Работа возобновлена, но учётные данные не заданы — /login <логин> <пароль>"
        return "▶️ Работа возобновлена."

    def _cmd_status(self, _text: str) -> str:
        st = self._store.snapshot()
        svc = self._status_provider() or {}
        now = datetime.now(st.schedule.tz)
        lines = ["🤖 Статус"]
        lines.append(f"Аккаунт: {st.wsp_login or 'не задан — /login <логин> <пароль>'}")
        lines.append(f"Страница: {st.base_url or 'не задана — /url <адрес> или BASE_URL'}")
        lines.append("Режим: приостановлен (/stop)" if st.paused else "Режим: работает")
        if svc.get("driver_open"):
            lines.append(f"Браузер: открыт — {svc.get('current_url', '')}")
        else:
            lines.append("Браузер: закрыт")
        close = st.schedule.seconds_until_close(now)
        if close is not None:
            lines.append(f"Окно расписания: открыто ещё {_fmt_secs(close)}")
        else:
            lines.append(f"Окно расписания: закрыто; следующее через {_fmt_secs(st.schedule.seconds_until_next_open(now))}")
        last = svc.get("last_attend_at")
        lines.append(f"Последняя отметка: {svc.get('last_lesson') or '—'}" + (f" ({last})" if last else ""))
        lines.append(f"Время: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        lines.append("Расписание:")
        lines.append(st.schedule.describe())
        return "\n".join(lines)

    def _cmd_login(self, text: str) -> str:
        parts = text.split(maxsplit=2)  # password may contain spaces
        if len(parts) < 3 or not parts[1].strip() or not parts[2].strip():
            return "Использование: /login <логин> <пароль>\nСмена данных — та же команда."
        login = parts[1].strip()
        password = parts[2].strip()
        self._store.set_credentials(login, password)
        self._wake.set()
        return (
            f"✅ Учётные данные сохранены: {login}\n"
            "⚠️ Пароль хранится в state-файле в открытом виде.\n"
            "Совет: удалите сообщение с паролем из чата — он остаётся в истории."
        )

    def _cmd_url(self, text: str) -> str:
        parts = text.split()
        if len(parts) != 2:
            return "Использование: /url https://…/RegistrationOnline"
        url = parts[1].strip()
        if not url.startswith(("http://", "https://")):
            return "URL должен начинаться с http:// или https://"
        self._store.set_base_url(url)
        self._wake.set()
        return f"✅ Страница посещаемости: {url}"


PROCESSOR_COMMANDS = ["help", "start", "resume", "stop", "pause", "status", "login", "url"]


def create_telebot(
    token: str,
    chat_id: str,
    store: BotStore,
    wake: threading.Event,
    status_provider: Callable[[], Dict],
) -> telebot.TeleBot:
    """Build the TeleBot instance with command handlers registered."""
    bot = telebot.TeleBot(token)
    processor = CommandProcessor(store, wake, status_provider)

    def _authorized_chat(message) -> bool:
        if str(message.chat.id) == chat_id:
            return True
        logger.warning("Ignoring message from unauthorized chat %s", message.chat.id)
        return False

    def _authorized_callback(c) -> bool:
        ok = (c.message and str(c.message.chat.id) == chat_id) or str(c.from_user.id) == chat_id
        if not ok:
            logger.warning("Ignoring callback from unauthorized user %s", c.from_user.id)
        return ok

    def _send(text: str, markup=None) -> None:
        try:
            bot.send_message(chat_id, text, reply_markup=markup)
        except Exception:
            logger.warning("Failed to send command reply", exc_info=True)

    @bot.message_handler(commands=PROCESSOR_COMMANDS)
    def on_command(message):
        if not _authorized_chat(message):
            return
        reply = processor.execute(message.text)
        if reply:
            _send(reply)

    @bot.message_handler(commands=["schedule"])
    def on_schedule(message):
        if not _authorized_chat(message):
            return
        text, markup = schedule_ui.menu_screen(store)
        _send(text, markup)

    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("sch:"))
    def on_schedule_callback(c):
        if not _authorized_callback(c):
            return
        try:
            bot.answer_callback_query(c.id)
        except Exception:
            pass
        screen = schedule_ui.handle_callback(c.data, store, wake)
        if screen is None:
            return
        text, markup = screen
        try:
            bot.edit_message_text(text, chat_id, c.message.message_id, reply_markup=markup)
        except Exception as e:
            if "message is not modified" in str(e):
                return
            logger.warning("edit_message_text failed; sending as new message", exc_info=True)
            _send(text, markup)

    # Fallback for recognized-but-unknown "/commands"; plain text is ignored.
    @bot.message_handler(func=lambda m: bool(m.text) and m.text.startswith("/"), content_types=["text"])
    def on_unknown_command(message):
        if not _authorized_chat(message):
            return
        _send(UNKNOWN_CMD_REPLY)

    return bot
