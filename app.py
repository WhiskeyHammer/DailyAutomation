import asyncio
import nodriver as uc
import os
import subprocess

async def main():
    print("Starting browser...")
    print(f"DISPLAY: {os.environ.get('DISPLAY')}")
    print(f"CHROME_PATH: {os.environ.get('CHROME_PATH')}")
    
    chrome_path = os.environ.get('CHROME_PATH')
    
    # Test if Chrome can launch manually
    print("\nTesting Chrome manually...")
    try:
        result = subprocess.run(
            [chrome_path, '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(f"Chrome version test: {result.stdout}")
        print(f"Chrome stderr: {result.stderr}")
    except Exception as e:
        print(f"Chrome manual test failed: {e}")
    
    # Check if Chrome is executable
    print(f"\nChrome file exists: {os.path.exists(chrome_path)}")
    print(f"Chrome is executable: {os.access(chrome_path, os.X_OK)}")
    
    # Try with simpler config first
    print("\nAttempting to start browser with nodriver...")
    
    try:
        config = uc.Config()
        config.browser_executable_path = chrome_path
        config.sandbox = False
        config.headless = False  # Use Xvfb display
        
        # Minimal args to start
        config.add_argument('--disable-dev-shm-usage')
        config.add_argument('--remote-debugging-port=9222')
        
        print(f"Config created. Attempting browser start...")
        browser = await uc.start(config)
        
        print("Browser started successfully!")
        
        page = await browser.get('https://example.com')
        print(f"Page loaded: {page.url}")
        
        await browser.stop()
        
    except Exception as e:
        print(f"\nError starting browser: {e}")
        import traceback
        traceback.print_exc()
        
        # Try without specifying path (let nodriver find Chrome)
        print("\n\nAttempting fallback: letting nodriver find Chrome...")
        try:
            browser = await uc.start(sandbox=False)
            print("Fallback succeeded!")
            await browser.stop()
        except Exception as e2:
            print(f"Fallback also failed: {e2}")

if __name__ == '__main__':
    uc.loop().run_until_complete(main())