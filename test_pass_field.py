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
opts.add_experimental_option('excludeSwitches', ['enable-automation'])
opts.add_experimental_option('useAutomationExtension', False)

driver = webdriver.Chrome(options=opts)
try:
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.get('https://accounts.google.com/EmbeddedSetup')
    wait = WebDriverWait(driver, 10)
    email_field = wait.until(EC.presence_of_element_located((By.ID, "identifierId")))
    email_field.send_keys('mdd145712@gmail.com')
    time.sleep(1)
    
    # Click next button
    next_btn = driver.find_element(By.ID, "identifierNext")
    driver.execute_script("arguments[0].click();", next_btn)
    
    # Wait for password input to appear
    print('Waiting for password field...')
    pass_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password' or @name='Passwd']")))
    print('Found password field successfully:', pass_field.get_attribute('name'))
except Exception as e:
    print('Error:', type(e).__name__, str(e))
finally:
    driver.quit()
