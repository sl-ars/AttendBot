from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver

def make_driver(remote_url: str) -> WebDriver:
    options = webdriver.ChromeOptions()
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors=yes")
    options.add_argument("--headless=new")
    return webdriver.Remote(command_executor=remote_url, options=options)
