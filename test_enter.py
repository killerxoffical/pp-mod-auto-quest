from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--disable-blink-features=AutomationControlled')

driver = webdriver.Chrome(options=opts)
try:
    driver.get('https://accounts.google.com/EmbeddedSetup')
    wait = WebDriverWait(driver, 10)
    el = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@id='identifierId' or @name='identifier']")))
    el.send_keys('mdd145712@gmail.com')
    el.send_keys(Keys.ENTER)
    time.sleep(5)
    print('PAGE BODY TEXT:\n', driver.find_element(By.TAG_NAME, 'body').text)
finally:
    driver.quit()
