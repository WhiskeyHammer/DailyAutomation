import asyncio
import nodriver as uc
import os
import subprocess
import time

async def main():
    print("Starting browser...")
    print(f"DISPLAY: {os.environ.get('DISPLAY')}")
    
    chrome_path = os.environ.get('CHROME_PATH', '/usr/bin/google-chrome')
    
    # Method 1: Try with user-data-dir specified
    print("\n=== Attempt 1: With user-data-dir ===")
    try:
        config = uc.Config()
        config.browser_executable_path = chrome_path
        config.sandbox = False
        config.headless = False
        config.user_data_dir = '/tmp/chrome-nodriver-profile'
        
        config.add_argument('--disable-dev-shm-usage')
        config.add_argument('--disable-gpu')
        config.add_argument('--remote-debugging-port=9222')
        
        browser = await uc.start(config)
        print("✓ Browser started!")
        
        page = await browser.get('https://example.com')
        print(f"✓ Page loaded: {page.url}")
        
        await browser.stop()
        return
        
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Method 2: Try starting Chrome process manually first
    print("\n=== Attempt 2: Manual Chrome process ===")
    try:
        # Start Chrome manually with debugging
        chrome_process = subprocess.Popen([
            chrome_path,
            '--remote-debugging-port=9222',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-software-rasterizer',
            '--disable-extensions',
            '--no-first-run',
            '--user-data-dir=/tmp/chrome-manual',
            'about:blank'
        ], 
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, 'DISPLAY': ':99'}
        )
        
        print(f"Chrome process started with PID: {chrome_process.pid}")
        time.sleep(3)  # Give Chrome time to start
        
        # Check if process is still running
        if chrome_process.poll() is not None:
            stdout, stderr = chrome_process.communicate()
            print(f"Chrome died immediately!")
            print(f"stdout: {stdout.decode()}")
            print(f"stderr: {stderr.decode()}")
        else:
            print("Chrome process is running")
            
            # Try connecting to existing Chrome
            config = uc.Config()
            config.host = '127.0.0.1'
            config.port = 9222
            
            browser = await uc.start(config)
            print("✓ Connected to existing Chrome!")
            
            page = await browser.get('https://example.com')
            print(f"✓ Page loaded: {page.url}")
            
            await browser.stop()
            chrome_process.terminate()
            chrome_process.wait()
            return
            
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        if 'chrome_process' in locals():
            chrome_process.terminate()
    
    # Method 3: Try with Selenium first to see if that works
    print("\n=== Attempt 3: Test with Selenium (for comparison) ===")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        
        options = Options()
        options.binary_location = chrome_path
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--headless=new')
        
        driver = webdriver.Chrome(options=options)
        driver.get('https://example.com')
        print(f"✓ Selenium works! Title: {driver.title}")
        driver.quit()
        
        print("\n→ Selenium works but nodriver doesn't!")
        print("→ This suggests nodriver has an issue with Chrome detection/connection")
        
    except Exception as e:
        print(f"✗ Selenium also failed: {e}")

if __name__ == '__main__':
    uc.loop().run_until_complete(main())