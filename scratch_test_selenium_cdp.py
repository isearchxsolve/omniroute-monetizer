import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

try:
    driver = webdriver.Chrome(options=options)
    print("SELENIUM CONNECTED TO REAL CHROME ON :9222 SUCCESSFULLY!")
    print("Title:", driver.title)
    print("URL:", driver.current_url)
    print("Window handles count:", len(driver.window_handles))
except Exception as e:
    print("Selenium connection error:", e)
