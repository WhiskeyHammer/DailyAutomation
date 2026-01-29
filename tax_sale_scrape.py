import asyncio
import nodriver as n
import csv
from lxml import html

# --- 1. CONFIGURATION & XPATH SELECTORS ---
START_URL = "https://duval.realtaxdeed.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=01/15/2025"
OUTPUT_FILE = "duval_sales_strict_2025.csv"

# --- XPath Selectors High Level Page Items ---
XP_AUCTION_DATE     = '//div[contains(@class, "BLHeaderDateDisplay")]'
XP_AUCTION_ITEMS    = '//div[contains(@class, "AUCTION_ITEM") and contains(@class, "PREVIEW")]'
XP_MSG_WAITING      = '//div[contains(@class, "Sub_Title") and contains(text(), "Auctions Waiting")]'
XP_MSG_CLOSED       = '//div[contains(@class, "Sub_Title") and contains(text(), "Auctions Closed")]'
XP_NEXT_PAGE_BTN    = '(//div[./div[contains(text(),"Auctions Closed or Canceled")]]//span[contains(@class, "PageRight")])[1]'
XP_NEXT_DATE_BTN    = '//a[contains(text(), "Next Auction")]'

# --- XPath Selectors Auction Items ---
XP_ITEM_ADDRESS_PART1 = './/tr[./td[text()="Property Address:"]]/td[2]'
XP_ITEM_ADDRESS_PART2 = './/tr[./td[text()="Property Address:"]]/following-sibling::tr[1]/td[2]'
XP_SALE_AMOUNT = './/div[@class="ASTAT_MSGD Astat_DATA"]'
XP_ASSESSED_VALUE = './/tr[./td[text()="Assessed Value:"]]/td[2]'
XP_OPENING_BID = './/tr[./td[text()="Opening Bid:"]]/td[2]'
XP_PARCEL_ID = './/tr[./td[text()="Parcel ID:"]]/td[2]/a'
XP_CURRENT_PAGE = '//input[@id="curPCA"]'
XP_FINAL_PAGE = '//input[@id="maxCA"]'

# Item inner detail selectors (relative to item)
XP_ITEM_LINK        = './/a[contains(@href, "Detail.aspx")]'


# --- 2. HELPER FUNCTIONS ---

class ElementMissingError(Exception):
    """Raised when an expected element is not found on the page."""
    pass


# --- 3. LOGICAL STEP FUNCTIONS ---

async def step_check_stop_condition(tab):
    """Checks if we hit the 'Auctions Waiting' section."""
    try:
        waiting_els = await tab.xpath(XP_MSG_WAITING)
        waiting_found = len(waiting_els) > 0
    except Exception:
        waiting_found = False
    
    try:
        closed_els = await tab.xpath(XP_MSG_CLOSED)
        closed_found = len(closed_els) > 0
    except Exception:
        closed_found = False
    
    # Stop if waiting found but closed not found
    if waiting_found and not closed_found:
        return True
    return False

async def step_get_date(tab):
    """Extracts the date string from the header."""
    try:
        date_els = await tab.xpath(XP_AUCTION_DATE)
        if date_els and len(date_els) > 0:
            return date_els[0].text.strip()
    except Exception as e:
        raise ElementMissingError(f"Could not find auction date element: {e}")
    raise ElementMissingError("Could not find auction date element")

async def step_extract_items(tab, current_date, writer, file_handle):
    """Finds all items on current view, parses them, writes to CSV."""
    
    # Get all auction item divs using XPath (xpath returns a list)
    items = await tab.xpath(XP_AUCTION_ITEMS)
    
    if not items:
        raise ElementMissingError("No auction items found on page")

    for item in items:
        try:
            if "Auction Sold" not in item.text:
                continue # skip it if it's not sold
            
            item_html = await item.get_html()
            tree = html.fromstring(item_html)

            # Property Address
            address_1 = tree.xpath(XP_ITEM_ADDRESS_PART1)[0].text_content().strip()
            address_2 = tree.xpath(XP_ITEM_ADDRESS_PART2)[0].text_content().strip()
            address = f"{address_1}, {address_2}"

            # Sale Amount
            sale_amount = tree.xpath(XP_SALE_AMOUNT)[0].text_content().strip()

            # Assessed Value
            assessed_value = tree.xpath(XP_ASSESSED_VALUE)[0].text_content().strip()

            # Opening Bid
            opening_bid = tree.xpath(XP_OPENING_BID)[0].text_content().strip()

            # Parcel ID
            parcel_id_raw = tree.xpath(XP_PARCEL_ID)[0]
            parcel_id = parcel_id_raw.text_content().strip()
            parcel_link = parcel_id_raw.get('href')

            # Write to CSV
            writer.writerow([current_date, parcel_id, address, sale_amount, assessed_value, opening_bid, parcel_link])
            file_handle.flush()

        except Exception as e:
            print(f"   Error parsing item: {e}")
            continue

async def step_next_page_of_items(tab):
    """Looks for a pagination 'Next' button and clicks it."""
    try:
        next_btns = await tab.xpath(XP_NEXT_PAGE_BTN)
        if next_btns and len(next_btns) > 0:
            print("   -> Clicking Next Page (Inner)...")
            await next_btns[0].click()
            await asyncio.sleep(3)
            return True
    except Exception:
        pass
    return False

async def step_next_auction_date(tab):
    """Looks for 'Next Auction' link and clicks it."""
    try:
        next_date_btns = await tab.xpath(XP_NEXT_DATE_BTN)
        if next_date_btns and len(next_date_btns) > 0:
            print("Moving to Next Auction Date...")
            await next_date_btns[0].click()
            await asyncio.sleep(4)
            return True
    except Exception:
        pass
    return False


# --- 4. MAIN EXECUTION ---

async def main():
    browser = await n.start(browser_args=['--start-maximized'])
    
    # Navigate
    try:
        tab = await browser.get(START_URL)
        await tab.wait_for('body')
        await asyncio.sleep(3)
    except Exception as e:
        raise ConnectionError(f"Failed to load initial URL: {e}")

    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Parcel ID", "Address", "Sale Amount", "Assessed Value", "Opening Bid", "Link"])
        
        print(f"Scraper Initialized. Output: {OUTPUT_FILE}")

        while True:
            # A. Check Stop Condition
            should_stop = await step_check_stop_condition(tab)
            if should_stop:
                print("Hit 'Auctions Waiting'. No more closed sales. Stopping.")
                break

            # B. Get Date
            date_str = await step_get_date(tab)
            print(f"Processing Date: {date_str}")

            # C. Inner Loop: Items & Pagination
            while True:
                await step_extract_items(tab, date_str, writer, f)
                
                has_next_page = await step_next_page_of_items(tab)
                if not has_next_page:
                    break
            
            # D. Outer Loop: Next Date
            has_next_date = await step_next_auction_date(tab)
            if not has_next_date:
                print("No 'Next Auction' button found. Process complete.")
                break

    print("Scraping complete!")
    await browser.stop()

if __name__ == '__main__':
    n.loop().run_until_complete(main())
