import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    InvalidSessionIdException,
)
from selenium.webdriver.remote.webdriver import WebDriver

from ..telegram import TelegramClient
from ..pages.login_page import LoginPage
from ..schedule import Schedule

logger = logging.getLogger(__name__)

class AttendanceService:
    ATTEND_BTN = (By.XPATH, "//div[contains(@class,'v-button') and contains(@class,'primary')]")
    LESSON_LABEL = (By.XPATH, "//div[contains(@class,'v-label-bold') and contains(@class,'v-has-width')]")

    def __init__(
        self,
        telegram: TelegramClient,
        schedule: Schedule,
        *,
        base_url: str,
        create_driver: Callable[[], WebDriver],
        wait_seconds: int = 30,
        driver: Optional[WebDriver] = None,
    ) -> None:
        self.driver: Optional[WebDriver] = driver
        self._wait_seconds = wait_seconds
        self.wait: Optional[WebDriverWait] = WebDriverWait(driver, wait_seconds) if driver else None
        self.login_page: Optional[LoginPage] = LoginPage(driver) if driver else None

        self.tg = telegram
        self.schedule = schedule
        self._create_driver = create_driver
        self.base_url = base_url

        logger.info("AttendanceService initialized (wait_seconds=%s, tz=%s)", wait_seconds, self.schedule.tz.key)

    # ---------- infra ----------

    def _notify(self, text: str) -> None:
        try:
            self.tg.send_message(text)
        except Exception:
            logger.warning("Failed to send Telegram notification")

    def _rebind_driver(self, driver: WebDriver) -> None:
        self.driver = driver
        self.wait = WebDriverWait(driver, self._wait_seconds)
        self.login_page = LoginPage(driver)

    def _open_driver(self, reason: str) -> None:
        logger.info("Opening WebDriver (reason: %s)", reason)
        drv = self._create_driver()
        self._rebind_driver(drv)
        drv.get(self.base_url)
        #self._notify(f"🔧 Browser opened ({reason})")

    def _shutdown_driver(self, reason: str) -> None:
        if not self.driver:
            return
        logger.info("Closing WebDriver (reason: %s)", reason)
        try:
            self.driver.quit()
        except Exception:
            logger.exception("Error while quitting WebDriver")
        finally:
            self.driver = None
            self.wait = None
            self.login_page = None
        #self._notify(f"🌙 Browser closed ({reason})")

    def _safe_url(self) -> str:
        try:
            return self.driver.current_url if self.driver else "<no-driver>"
        except Exception:
            return "<unavailable>"

    # ---------- domain ----------

    def ensure_logged_in(self, username: str, password: str) -> None:
        if not (self.driver and self.wait and self.login_page):
            raise RuntimeError("Driver is not initialized")
        logger.debug("Checking login state at %s", self._safe_url())
        if self.login_page.at_login():
            logger.info("Detected login screen → attempting login")
            self.login_page.login(username, password)
            logger.info("Login submitted")

    def try_attend_once(self) -> bool:
        if not (self.driver and self.wait):
            raise RuntimeError("Driver is not initialized")
        logger.debug("Waiting for ATTEND button…")
        btn = self.wait.until(EC.element_to_be_clickable(self.ATTEND_BTN))
        logger.info("Clicking ATTEND at %s", self._safe_url())
        btn.click()

        logger.debug("Waiting for lesson label…")
        lesson_text = self.wait.until(EC.presence_of_element_located(self.LESSON_LABEL)).text
        lesson = (lesson_text or "").split("\n")[0].strip()

        logger.info("Attended lesson: %s", lesson or "<empty>")
        self._notify(f"Attended\n{lesson}")
        return True

    # ---------- main loop ----------

    def run_loop(self, username: str, password: str, poll_secs: int = 10) -> None:

        logger.info("Starting schedule-aware loop (poll=%ss, tz=%s)", poll_secs, self.schedule.tz.key)

        while True:
            now = datetime.now(self.schedule.tz)
            secs = self.schedule.seconds_until_next_open(now)

            if secs > 0:
                if self.driver:
                    self._shutdown_driver("outside schedule window")
                wake = now + timedelta(seconds=secs)
                logger.info("Outside schedule — sleeping until %s (%ds)", wake.strftime("%Y-%m-%d %H:%M:%S %Z"), secs)
                time.sleep(secs)
                continue

            if not self.driver:
                self._open_driver("enter schedule window")

            try:
                self.ensure_logged_in(username, password)
                self.try_attend_once()
                logger.debug("Sleeping %ss (inside window)", poll_secs)
                time.sleep(poll_secs)

            except InvalidSessionIdException as e:
                logger.exception("InvalidSessionIdException: %s; recreate driver", e)
                self._shutdown_driver("invalid session id")
                time.sleep(2)
                self._open_driver("recover invalid session")
                time.sleep(poll_secs)

            except TimeoutException:
                logger.warning("Timeout waiting for UI at %s; refreshing; next check in %ss", self._safe_url(), poll_secs)
                try:
                    if self.driver:
                        self.driver.refresh()
                except Exception:
                    logger.exception("Failed to refresh after TimeoutException; recreating driver")
                    self._shutdown_driver("refresh failed after timeout")
                    self._open_driver("recover after timeout")
                time.sleep(poll_secs)

            except WebDriverException as e:
                logger.exception("WebDriverException: %s; will try refresh", e)
                time.sleep(3)
                try:
                    if self.driver:
                        self.driver.refresh()
                except Exception:
                    logger.exception("Failed to refresh after WebDriverException; recreating driver")
                    self._shutdown_driver("refresh failed after wde")
                    self._open_driver("recover after wde")
                time.sleep(poll_secs)

            except Exception:
                logger.exception("Unexpected error in run_loop; retrying in %ss", poll_secs)
                time.sleep(poll_secs)

    def shutdown(self) -> None:
        self._shutdown_driver("service shutdown")
