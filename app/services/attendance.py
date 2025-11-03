# app/services/attendance.py
import logging
import time
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver
from ..telegram import TelegramClient
from ..pages.login_page import LoginPage
from ..schedule import Schedule

logger = logging.getLogger(__name__)

class AttendanceService:
    ATTEND_BTN = (By.XPATH, "//div[contains(@class,'v-button') and contains(@class,'primary')]")
    LESSON_LABEL = (By.XPATH, "//div[contains(@class,'v-label-bold') and contains(@class,'v-has-width')]")

    def __init__(self, driver: WebDriver, telegram: TelegramClient, schedule: Schedule, wait_seconds: int = 30) -> None:
        self.driver = driver
        self.wait = WebDriverWait(driver, wait_seconds)
        self.tg = telegram
        self.login_page = LoginPage(driver)
        self.schedule = schedule
        logger.info("AttendanceService initialized (wait_seconds=%s, tz=%s)", wait_seconds, self.schedule.tz.key)

    def _safe_url(self) -> str:
        try:
            return self.driver.current_url
        except Exception:
            return "<unavailable>"

    def ensure_logged_in(self, username: str, password: str) -> None:
        logger.debug("Checking login state at %s", self._safe_url())
        if self.login_page.at_login():
            logger.info("Detected login screen → attempting login")
            self.login_page.login(username, password)
            logger.info("Login submitted")

    def try_attend_once(self) -> bool:
        logger.debug("Waiting for ATTEND button…")
        btn = self.wait.until(EC.element_to_be_clickable(self.ATTEND_BTN))
        logger.info("Clicking ATTEND at %s", self._safe_url())
        btn.click()

        logger.debug("Waiting for lesson label…")
        lesson_text = self.wait.until(EC.presence_of_element_located(self.LESSON_LABEL)).text
        lesson = (lesson_text or "").split("\n")[0].strip()

        logger.info("Attended lesson: %s", lesson or "<empty>")
        self.tg.send_message(f"Attended\n{lesson}")
        return True

    def _sleep_until_open(self) -> None:
        now = datetime.now(self.schedule.tz)
        secs = self.schedule.seconds_until_next_open(now)
        if secs == 0:
            return
        wake = now + timedelta(seconds=secs)
        logger.info(
            "Outside configured schedule — sleeping until %s (%ds)",
            wake.strftime("%Y-%m-%d %H:%M:%S %Z"),
            secs,
        )
        time.sleep(secs)

    def run_loop(self, username: str, password: str, poll_secs: int = 10) -> None:
        """Main loop with fixed-interval polling. No backoff; always sleep poll_secs (default 10s)."""
        logger.info(
            "Starting schedule-aware loop (fixed poll=%ss, tz=%s)",
            poll_secs, self.schedule.tz.key
        )

        while True:
            # Block if outside allowed windows.
            self._sleep_until_open()

            try:
                self.ensure_logged_in(username, password)
                self.try_attend_once()

                logger.debug("Sleeping %ss (inside window)", poll_secs)
                time.sleep(poll_secs)

            except TimeoutException:
                logger.warning(
                    "Timeout waiting for UI elements at %s; refreshing page. Next check in %ss",
                    self._safe_url(), poll_secs
                )
                try:
                    self.driver.refresh()
                except Exception:
                    logger.exception("Failed to refresh after TimeoutException")
                time.sleep(poll_secs)

            except WebDriverException as e:
                logger.exception("WebDriverException: %s; will refresh and retry in %ss", e, poll_secs)
                time.sleep(3)
                try:
                    self.driver.refresh()
                    logger.debug("Refreshed page after WebDriverException; current_url=%s", self._safe_url())
                except Exception:
                    logger.exception("Failed to refresh after WebDriverException")
                time.sleep(poll_secs)

            except Exception:
                logger.exception("Unexpected error in run_loop; retrying in %ss", poll_secs)
                time.sleep(poll_secs)
