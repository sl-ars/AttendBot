import logging
import signal
import sys
from datetime import datetime

from app.config import get_settings
from app.driver_factory import make_driver
from app.telegram import TelegramClient
from app.services.attendance import AttendanceService
from app.schedule import Schedule


def format_schedule(schedule: Schedule) -> str:
    lines = [f"Timezone: {schedule.tz.key}"]
    for idx, day_rule in schedule.days.items():
        day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][idx]
        if not day_rule.enabled:
            lines.append(f"• {day_name}: off")
            continue
        windows = [f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for s, e in day_rule.windows]
        lines.append(f"• {day_name}: {', '.join(windows) if windows else 'default'}")
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    schedule = Schedule.from_toml(settings.schedule_path)

    tg = TelegramClient(settings.tg_bot_token, settings.tg_chat_id)

    def now_s():
        return datetime.now(schedule.tz).strftime("%Y-%m-%d %H:%M:%S %Z")

    def safe_notify(text: str) -> None:
        try:
            tg.send_message(text)
        except Exception as e:
            logging.warning("Failed to send Telegram notification: %s", e)

    safe_notify(
        "🚀 Bot starting\n"
        f"Account: {settings.wsp_login}\n"
        f"TZ: {schedule.tz.key}\n"
        f"Time: {now_s()}\n\n"
        f"📅 Schedule:\n{format_schedule(schedule)}"
    )

    def create_driver():
        return make_driver(settings.remote_url)

    svc = AttendanceService(
        telegram=tg,
        schedule=schedule,
        base_url=settings.base_url,
        create_driver=create_driver,
        wait_seconds=30,
        driver=None,
    )

    def _graceful_shutdown(signum=None, _frame=None):
        try:
            sig_name = signal.Signals(signum).name if signum else "UNKNOWN"
        except Exception:
            sig_name = str(signum)
        safe_notify(f"🛑 Bot stopping (signal: {sig_name})\nAccount: {settings.wsp_login}\nTime: {now_s()}")
        try:
            svc.shutdown()
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    try:
        svc.run_loop(settings.wsp_login, settings.wsp_password, poll_secs=10)
    except Exception as e:
        safe_notify(
            "💥 Bot crashed\n"
            f"Error: {type(e).__name__}: {e}\n"
            f"Account: {settings.wsp_login}\n"
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
