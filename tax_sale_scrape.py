import asyncio
import nodriver as n
import csv
import logging
from lxml import html

# --- 1. CONFIGURATION & XPATH SELECTORS ---
START_URL = "https://duval.realtaxdeed.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=01/15/2025"
OUTPUT_FILE = "duval_sales_strict_2025.csv"
LOG_FILE = "tax_sale_scrape.log"

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
XP_FINAL_PAGE = '//span[@id="maxCA"]'

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
    date_els = await tab.xpath(XP_AUCTION_DATE)
    if not date_els or len(date_els) == 0:
        raise ElementMissingError("Could not find auction date element")
    return date_els[0].text.strip()

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
            logger.error(f"   Error parsing item: {e}")
            continue

async def step_next_page_of_items(tab):
    """Looks for a pagination 'Next' button and clicks it if not on the last page."""
    try:
        # Get total number of pages from XP_FINAL_PAGE (span text)
        final_page_els = await tab.xpath(XP_FINAL_PAGE)
        if not final_page_els or len(final_page_els) == 0:
            raise ElementMissingError("Could not find max page element (XP_FINAL_PAGE)")
        total_pages = int(final_page_els[0].text.strip())
        
        # Get current page - use apply() to get fresh attribute from DOM
        current_page_els = await tab.xpath(XP_CURRENT_PAGE)
        if not current_page_els or len(current_page_els) == 0:
            raise ElementMissingError("Could not find current page element (XP_CURRENT_PAGE)")
        current_page = int(await current_page_els[0].apply("(el) => el.getAttribute('curpg') || '1'"))
        
        logger.info(f"   Page {current_page} of {total_pages}")
        
        # Only click next if we're not on the last page
        if current_page >= total_pages:
            return False
        
        next_btns = await tab.xpath(XP_NEXT_PAGE_BTN)
        if next_btns and len(next_btns) > 0:
            logger.info("   -> Clicking Next Page (Inner)...")
            await next_btns[0].click()
            
            # Wait for the page number to actually change using apply() for fresh values
            expected_page = current_page + 1
            for _ in range(30):  # Max 30 attempts, ~15 seconds total
                await asyncio.sleep(0.5)
                current_page_els = await tab.xpath(XP_CURRENT_PAGE)
                if current_page_els and len(current_page_els) > 0:
                    new_page = int(await current_page_els[0].apply("(el) => el.getAttribute('curpg') || '1'"))
                    if new_page >= expected_page:
                        break
            return True
    except Exception as e:
        logger.error(f"   Error in pagination: {e}")
    return False

async def step_next_auction_date(tab):
    """Looks for 'Next Auction' link and clicks it."""
    try:
        next_date_btns = await tab.xpath(XP_NEXT_DATE_BTN)
        if next_date_btns and len(next_date_btns) > 0:
            # Get current date before clicking
            current_date = None
            date_els = await tab.xpath(XP_AUCTION_DATE)
            if date_els and len(date_els) > 0:
                current_date = date_els[0].text.strip()
            
            logger.info("Moving to Next Auction Date...")
            await next_date_btns[0].click()
            
            # Wait for the date to change (indicating new page loaded)
            for _ in range(20):  # Max 20 attempts, ~10 seconds total
                await asyncio.sleep(0.5)
                date_els = await tab.xpath(XP_AUCTION_DATE)
                if date_els and len(date_els) > 0:
                    new_date = date_els[0].text.strip()
                    if new_date != current_date:
                        break
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
        
        logger.info(f"Scraper Initialized. Output: {OUTPUT_FILE}")

        while True:
            # A. Check Stop Condition
            should_stop = await step_check_stop_condition(tab)
            if should_stop:
                logger.info("Hit 'Auctions Waiting'. No more closed sales. Stopping.")
                break

            # B. Get Date
            date_str = await step_get_date(tab)
            logger.info(f"Processing Date: {date_str}")

            # C. Inner Loop: Items & Pagination
            while True:
                await step_extract_items(tab, date_str, writer, f)
                
                has_next_page = await step_next_page_of_items(tab)
                if not has_next_page:
                    break
            
            # D. Outer Loop: Next Date
            has_next_date = await step_next_auction_date(tab)
            if not has_next_date:
                logger.info("No 'Next Auction' button found. Process complete.")
                break

    logger.info("Scraping complete!")
    browser.stop()

if __name__ == '__main__':
    n.loop().run_until_complete(main())
