from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
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
    btn = driver.find_element(By.ID, 'identifierNext')
    btn.click()
    time.sleep(4)
    # Check what text or error is shown on the page
    body_text = driver.find_element(By.TAG_NAME, 'body').text
    print('PAGE BODY TEXT:\n', body_text)
finally:
    driver.quit()
