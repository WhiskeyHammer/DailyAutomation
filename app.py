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
    config.browser_args = [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--no-first-run',
        '--no-default-browser-check',
        '--window-size=1920,1080'
    ]

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