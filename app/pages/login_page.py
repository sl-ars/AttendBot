import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import TimeoutException

class LoginPage:
    USERNAME = (By.ID, "gwt-uid-4")
    PASSWORD = (By.ID, "gwt-uid-6")
    LOGIN_TITLE = (By.XPATH, "//div[@class='v-button v-widget primary v-button-primary']")

    def __init__(self, driver: WebDriver, wait_seconds: int = 15) -> None:
        self.driver = driver
        self.wait = WebDriverWait(driver, wait_seconds)

    def at_login(self) -> bool:
        try:
            el = self.wait.until(EC.presence_of_element_located(self.LOGIN_TITLE))
            return (el.text or "").strip() in ["Вход в систему", "Кіру", "Log in", "Вход", "Login"]
        except TimeoutException:
            return False

    def login(self, username: str, password: str) -> None:
        """pge.kbtu.kz specifics (verified against the live page):
        - the username field is a Vaadin combobox: type, then accept the
          suggestion (ArrowDown + Enter) — plain send_keys is cleared on blur;
        - Enter in the password field does NOT submit — click the primary
          button («Кіру»).
        """
        user = self.wait.until(EC.element_to_be_clickable(self.USERNAME))
        user.click()
        user.clear()
        user.send_keys(username)
        time.sleep(1.5)  # let Vaadin filter suggestions
        user.send_keys(Keys.ARROW_DOWN, Keys.ENTER)
        self.wait.until(lambda d: (user.get_attribute("value") or "").strip() == username.strip())

        pwd = self.wait.until(EC.element_to_be_clickable(self.PASSWORD))
        pwd.clear()
        pwd.send_keys(password)

        submit = self.wait.until(EC.element_to_be_clickable(self.LOGIN_TITLE))
        submit.click()
