from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

opts = Options()
opts.add_argument('--headless=new')

driver = webdriver.Chrome(options=opts)
try:
    driver.get('https://accounts.google.com/EmbeddedSetup')
    time.sleep(2)
    el = driver.find_element(By.ID, 'identifierId')
    el.send_keys('mdd145712@gmail.com')
    btn = driver.find_element(By.ID, 'identifierNext')
    print('Button tag:', btn.tag_name, 'class:', btn.get_attribute('class'))
    # In Google, identifierNext is usually a <div> wrapper, and the actual button is inside it!
    # Let's find button inside or click:
    inner_btn = btn.find_element(By.TAG_NAME, 'button') if len(btn.find_elements(By.TAG_NAME, 'button')) > 0 else btn
    print('Inner button:', inner_btn.tag_name, inner_btn.text)
    driver.execute_script("arguments[0].click();", inner_btn)
    time.sleep(4)
    print('PAGE BODY TEXT AFTER JS CLICK:\n', driver.find_element(By.TAG_NAME, 'body').text)
finally:
    driver.quit()
