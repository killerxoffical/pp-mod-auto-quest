from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--disable-blink-features=AutomationControlled')
opts.add_experimental_option('excludeSwitches', ['enable-automation'])
opts.add_experimental_option('useAutomationExtension', False)

driver = webdriver.Chrome(options=opts)
try:
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.get('https://accounts.google.com/EmbeddedSetup')
    wait = WebDriverWait(driver, 10)
    # The actual input id on Google is identifierId
    email_field = wait.until(EC.presence_of_element_located((By.ID, "identifierId")))
    print('Found email_field successfully:', email_field.get_attribute('id'))
    email_field.send_keys('mdd145712@gmail.com')
    print('Filled email value:', email_field.get_attribute('value'))
except Exception as e:
    print('Error:', e)
finally:
    driver.quit()
