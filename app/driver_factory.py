from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver

def make_driver(remote_url: str) -> WebDriver:
    options = webdriver.ChromeOptions()
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors=yes")
    options.add_argument("--headless=new")
    # Keep the grid container small: avoid /dev/shm usage (Chrome falls back
    # to /tmp), so the 2gb default shm_size is unnecessary.
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Remote(command_executor=remote_url, options=options)
