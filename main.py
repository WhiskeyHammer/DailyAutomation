import asyncio
import nodriver as uc
import random

# Configuration
TARGET_URL = "https://workout-tracker-hxg5.onrender.com/"

async def check_site():
    browser = None
    try:
        # Start browser with flags optimized for low-memory server environments
        browser = await uc.start(
            headless=True,
            browser_args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage", # Crucial for Docker
                "--disable-gpu"
            ]
        )

        tab = await browser.get(TARGET_URL)
        
        # Wait for the password field (indicates login screen)
        # We use a short timeout to fail fast
        print(f"Checking {TARGET_URL}...")
        password_field = await tab.select('input[type="password"]', timeout=15)

        if password_field:
            print("SUCCESS: Login screen is visible.")
        else:
            print("FAILURE: Password field not found.")

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        # VERY IMPORTANT: Close the browser to free up RAM
        if browser:
            browser.stop()

async def run_loop():
    print("Starting Monitoring Service...")
    while True:
        await check_site()
        check_interval = random.randint(60, 180)
        print(f"Sleeping for {check_interval} seconds...")
        await asyncio.sleep(check_interval)

if __name__ == '__main__':
    # nodriver standard loop
    uc.loop().run_until_complete(run_loop())
