import nodriver as uc
import os
import asyncio

async def main():
    print("Starting browser...")
    print(f"DISPLAY: {os.environ.get('DISPLAY')}")
    print(f"CHROME_PATH: {os.environ.get('CHROME_PATH')}")
    
    # Method 1: Use Config object (RECOMMENDED)
    config = uc.Config()
    config.browser_executable_path = os.environ.get('CHROME_PATH')
    config.add_argument('--no-sandbox')
    config.add_argument('--disable-setuid-sandbox')
    config.add_argument('--disable-dev-shm-usage')
    config.add_argument('--disable-gpu')
    config.add_argument('--no-first-run')
    config.add_argument('--no-default-browser-check')
    config.add_argument('--window-size=1920,1080')

    browser = await uc.start(config)
    page = await browser.get('https://news.google.com/home?hl=en-US&gl=US&ceid=US:en')

    await page.save_screenshot()
    await page.get_content()
    await page.scroll_down(150)
    elems = await page.xpath("//article/a")

    for elem in elems:
        print(elem.text)

if __name__ == '__main__':

    # since asyncio.run never worked (for me)
    uc.loop().run_until_complete(main())