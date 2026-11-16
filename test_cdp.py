from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--disable-blink-features=AutomationControlled')
opts.add_experimental_option('excludeSwitches', ['enable-automation'])
opts.add_experimental_option('useAutomationExtension', False)

driver = webdriver.Chrome(options=opts)
try:
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """
    })
    driver.get('https://accounts.google.com/EmbeddedSetup')
    val = driver.execute_script("return navigator.webdriver")
    print('navigator.webdriver is:', val)
finally:
    driver.quit()
