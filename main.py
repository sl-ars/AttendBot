import logging
import signal
import socket
import sys
from datetime import datetime

from app.config import get_settings
from app.driver_factory import make_driver
from app.telegram import TelegramClient
from app.services.attendance import AttendanceService
from app.schedule import Schedule


def main() -> int:
    settings = get_settings()
    schedule = Schedule.from_toml(settings.schedule_path)

    tg = TelegramClient(settings.tg_bot_token, settings.tg_chat_id)
    hostname = socket.gethostname()

    def now_s():
        return datetime.now(schedule.tz).strftime("%Y-%m-%d %H:%M:%S %Z")

    def safe_notify(text: str) -> None:
        try:
            tg.send_message(text)
        except Exception as e:
            logging.warning("Failed to send Telegram notification: %s", e)

    # --- startup notify ---
    safe_notify(
        "🚀 Bot starting\n"
        f"TZ: {schedule.tz.key}\n"
        f"Time: {now_s()}"
    )

    driver = make_driver(settings.remote_url)

    def _graceful_shutdown(signum=None, _frame=None):
        try:
            sig_name = signal.Signals(signum).name if signum else "UNKNOWN"
        except Exception:
            sig_name = str(signum)
        safe_notify(f"🛑 Bot stopping (signal: {sig_name})\nHost: {hostname}\nTime: {now_s()}")
        try:
            driver.quit()
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    driver.get(settings.base_url)
    svc = AttendanceService(driver, tg, schedule)

    try:
        svc.run_loop(settings.wsp_login, settings.wsp_password, poll_secs=10)
    except Exception as e:
        # Crash path notify (SystemExit from signals is NOT caught here)
        safe_notify(
            "💥 Bot crashed\n"
            f"Error: {type(e).__name__}: {e}\n"
            f"Host: {hostname}\n"
            f"Time: {now_s()}"
        )
        raise
    finally:
        # Ensure driver is closed on any non-signal exit (no extra tg notify here to avoid duplicates)
        try:
            driver.quit()
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
