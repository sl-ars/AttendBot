import logging
import signal
import sys
import threading
from datetime import datetime

from app.config import get_settings
from app.driver_factory import make_driver
from app.store import BotStore
from app.telegram import TelegramNotifier
from app.commands import create_telebot
from app.services.attendance import AttendanceService


def main() -> int:
    settings = get_settings()
    store = BotStore(
        settings.state_path,
        seed_login=settings.wsp_login,
        seed_password=settings.wsp_password,
        seed_base_url=settings.base_url,
    )
    st0 = store.snapshot()

    wake = threading.Event()
    # Populated below; /status can only arrive after the polling thread starts,
    # i.e. after the service exists.
    service: list[AttendanceService] = []

    bot = None
    try:
        bot = create_telebot(
            settings.tg_bot_token,
            settings.tg_chat_id,
            store=store,
            wake=wake,
            status_provider=lambda: service[0].snapshot() if service else {},
        )
    except Exception:
        logging.exception(
            "Telegram bot initialization failed — continuing WITHOUT Telegram "
            "(commands and notifications disabled)"
        )
    tg = TelegramNotifier(bot, settings.tg_chat_id)

    def now_s() -> str:
        return datetime.now(st0.schedule.tz).strftime("%Y-%m-%d %H:%M:%S %Z")

    def safe_notify(text: str) -> None:
        try:
            tg.send_message(text)
        except Exception as e:
            logging.warning("Failed to send Telegram notification: %s", e)

    safe_notify(
        "🚀 Bot starting\n"
        f"Account: {st0.wsp_login or 'не задан — отправьте /login <логин> <пароль>'}\n"
        f"Page: {st0.base_url or 'не задана — /url <адрес> или BASE_URL'}\n"
        f"TZ: {st0.schedule.tz.key}\n"
        f"Time: {now_s()}\n\n"
        f"📅 Schedule:\n{st0.schedule.describe()}\n\n"
        "Управление: /help"
    )

    svc = AttendanceService(
        telegram=tg,
        state_provider=store.snapshot,
        create_driver=lambda: make_driver(settings.remote_url),
        wake=wake,
        wait_seconds=30,
    )
    service.append(svc)

    # Command polling runs in a daemon thread; telebot owns retries/reconnects.
    if bot is not None:
        threading.Thread(
            target=bot.infinity_polling,
            kwargs={"timeout": 25, "allowed_updates": ["message", "callback_query"]},
            name="command-bot",
            daemon=True,
        ).start()

    def _graceful_shutdown(signum=None, _frame=None):
        try:
            sig_name = signal.Signals(signum).name if signum else "UNKNOWN"
        except Exception:
            sig_name = str(signum)
        safe_notify(f"🛑 Bot stopping (signal: {sig_name})\nTime: {now_s()}")
        wake.set()
        try:
            bot.stop_polling()
        except Exception:
            pass
        try:
            svc.shutdown()
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    try:
        svc.run_loop(poll_secs=10)
    except Exception as e:
        safe_notify(
            "💥 Bot crashed\n"
            f"Error: {type(e).__name__}: {e}\n"
            f"Time: {now_s()}"
        )
        raise
    finally:
        try:
            svc.shutdown()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    import os
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    raise SystemExit(main())
