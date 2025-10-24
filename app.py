import asyncio
import nodriver as uc
import os
import subprocess
import time

async def main():
    print("Starting browser...")
    print(f"DISPLAY: {os.environ.get('DISPLAY')}")
    
    chrome_path = os.environ.get('CHROME_PATH', '/usr/bin/google-chrome')
    chrome_process = None
    
    try:
        # Start Chrome manually with debugging
        print("Starting Chrome process...")
        chrome_process = subprocess.Popen([
            chrome_path,
            '--remote-debugging-port=9222',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-software-rasterizer',
            '--disable-extensions',
            '--no-first-run',
            '--user-data-dir=/tmp/chrome-nodriver',
            'about:blank'
        ], 
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, 'DISPLAY': os.environ.get('DISPLAY', ':99')}
        )
        
        print(f"Chrome started with PID: {chrome_process.pid}")
        time.sleep(3)  # Give Chrome time to start
        
        # Check if Chrome is still running
        if chrome_process.poll() is not None:
            stdout, stderr = chrome_process.communicate()
            print(f"Chrome failed to start!")
            print(f"stderr: {stderr.decode()}")
            return
        
        print("Chrome is running, connecting with nodriver...")
        
        # Connect to the existing Chrome instance
        config = uc.Config()
        config.host = '127.0.0.1'
        config.port = 9222
        
        browser = await uc.start(config)
        print("✓ Connected to Chrome!")
        
        page = await browser.get('https://news.google.com/home?hl=en-US&gl=US&ceid=US:en')

        await page.save_screenshot()
        await page.get_content()
        await page.scroll_down(150)
        elems = await page.xpath("//article/a")

        for elem in elems:
            print(elem.text)
        
        # DON'T await browser.stop() - it returns None
        # Just call it directly
        browser.stop()
        print("✓ Browser connection closed")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Clean up Chrome process
        if chrome_process and chrome_process.poll() is None:
            print("Terminating Chrome process...")
            chrome_process.terminate()
            try:
                chrome_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chrome_process.kill()
                chrome_process.wait()
            print("✓ Chrome process terminated")

if __name__ == '__main__':
    uc.loop().run_until_complete(main())