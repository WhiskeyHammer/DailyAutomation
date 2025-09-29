import nodriver as uc

async def main():

    browser = await uc.start()
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