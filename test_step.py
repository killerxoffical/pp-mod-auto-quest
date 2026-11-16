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
    driver.get('https://accounts.google.com/EmbeddedSetup')
    wait = WebDriverWait(driver, 10)
    el = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@id='identifierId' or @name='identifier']")))
    print('Found email input:', el.get_attribute('id'))
    el.send_keys('test@gmail.com')
    btn = driver.find_element(By.ID, 'identifierNext')
    print('Found Next button:', btn.text)
    btn.click()
    time.sleep(3)
    print('Page URL after email:', driver.current_url)
    pass_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@name='Passwd' or @type='password']")))
    print('Found password input:', pass_input.get_attribute('name'))
except Exception as e:
    print('Error occurred:', type(e).__name__, str(e))
finally:
    driver.quit()
