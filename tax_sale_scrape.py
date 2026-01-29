import asyncio
import nodriver as n
import csv
import logging
from lxml import html

from datetime import datetime

# --- 1. CONFIGURATION & XPATH SELECTORS ---
CALENDAR_URL = "https://duval.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar&selCalDate=%7Bts%20%272025%2D01%2D01%2000%3A00%3A00%27%7D"
AUCTION_URL_TEMPLATE = "https://duval.realtaxdeed.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={date}"
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

# --- XPath Selectors Calendar Page ---
XP_CAL_AUCTION_DAYS = '//div[contains(@class,"CALSELT ")]'
XP_CAL_NEXT_MONTH   = '(//div[@class="CALNAV"]/a)[2]'
XP_CAL_CURRENT_DATE = '(//div[@class="CALDATE"])[1]'

# --- XPath Selectors High Level Page Items ---
XP_AUCTION_DATE     = '//div[contains(@class, "BLHeaderDateDisplay")]'
XP_AUCTION_ITEMS    = '//div[contains(@class, "AUCTION_ITEM") and contains(@class, "PREVIEW")]'
XP_MSG_WAITING      = '//div[contains(@class, "Sub_Title") and contains(text(), "Auctions Waiting")]'
XP_MSG_CLOSED       = '//div[contains(@class, "Sub_Title") and contains(text(), "Auctions Closed")]'
XP_NEXT_PAGE_BTN    = '(//div[./div[contains(text(),"Auctions Closed or Canceled")]]//span[contains(@class, "PageRight")])[1]'

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
    if not date_els:
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
        if not final_page_els:
            raise ElementMissingError("Could not find max page element (XP_FINAL_PAGE)")
        total_pages = int(final_page_els[0].text.strip())
        
        # Get current page - use apply() to get fresh attribute from DOM
        current_page_els = await tab.xpath(XP_CURRENT_PAGE)
        if not current_page_els:
            raise ElementMissingError("Could not find current page element (XP_CURRENT_PAGE)")
        current_page = int(await current_page_els[0].apply("(el) => el.getAttribute('curpg') || '1'"))
        
        logger.info(f"   Page {current_page} of {total_pages}")
        
        # Only click next if we're not on the last page
        if current_page >= total_pages:
            return False
        
        next_btns = await tab.xpath(XP_NEXT_PAGE_BTN)
        if next_btns:
            logger.info("   -> Clicking Next Page (Inner)...")
            await next_btns[0].click()
            
            # Wait for the page number to actually change using apply() for fresh values
            expected_page = current_page + 1
            for _ in range(30):  # Max 30 attempts, ~15 seconds total
                await asyncio.sleep(0.5)
                current_page_els = await tab.xpath(XP_CURRENT_PAGE)
                if current_page_els:
                    new_page = int(await current_page_els[0].apply("(el) => el.getAttribute('curpg') || '1'"))
                    if new_page >= expected_page:
                        # Short pause to let page fully render
                        await asyncio.sleep(0.5)
                        break
            return True
    except Exception as e:
        logger.error(f"   Error in pagination: {e}")
    return False

async def collect_auction_dates_from_calendar(tab):
    """
    Navigates through the calendar and collects all auction date dayids.
    Stops when no auction days are found AND the calendar month is beyond current month/year.
    Returns a list of dayid strings (format: MM/DD/YYYY).
    """
    auction_dates = []
    current_real_date = datetime.now()
    
    logger.info("Navigating to calendar page...")
    await tab.get(CALENDAR_URL)
    await asyncio.sleep(3)
    
    while True:
        # Get current calendar month/year from the page
        cal_date_els = await tab.xpath(XP_CAL_CURRENT_DATE)
        if not cal_date_els:
            raise ElementMissingError("Could not find calendar date element (XP_CAL_CURRENT_DATE)")
        
        cal_date_text = cal_date_els[0].text.strip()  # e.g., "January 2025"
        logger.info(f"Scanning calendar: {cal_date_text}")
        
        # Parse the calendar month/year
        try:
            cal_date = datetime.strptime(cal_date_text, "%B %Y")
        except ValueError as e:
            raise ElementMissingError(f"Could not parse calendar date '{cal_date_text}': {e}")
        
        # Get all auction day elements on this month
        auction_day_els = await tab.xpath(XP_CAL_AUCTION_DAYS)
        
        # Extract dayid from each auction day
        for day_el in auction_day_els:
            dayid = await day_el.apply("(el) => el.getAttribute('dayid')")
            if dayid:
                auction_dates.append(dayid)
                logger.info(f"   Found auction date: {dayid}")
        
        # Check stop condition: no auction days AND calendar is beyond current month
        has_auction_days = len(auction_day_els) > 0
        is_future_month = (cal_date.year > current_real_date.year or 
                          (cal_date.year == current_real_date.year and cal_date.month > current_real_date.month))
        
        if not has_auction_days and is_future_month:
            logger.info(f"No auction days found and calendar ({cal_date_text}) is beyond current month. Stopping calendar scan.")
            break
        
        # Click next month button with retry logic
        old_cal_date_text = cal_date_text
        max_retries = 3
        month_changed = False
        
        for retry in range(max_retries):
            next_month_btns = await tab.xpath(XP_CAL_NEXT_MONTH)
            if not next_month_btns:
                logger.info("No next month button found. Stopping calendar scan.")
                break
            
            # Wait for button to be ready
            await asyncio.sleep(0.5)
            
            logger.info(f"   -> Clicking Next Month... (attempt {retry + 1}/{max_retries})")
            await next_month_btns[0].click()
            
            # Wait for the calendar month to change
            for _ in range(20):
                await asyncio.sleep(0.5)
                cal_date_els = await tab.xpath(XP_CAL_CURRENT_DATE)
                if cal_date_els:
                    new_cal_date_text = cal_date_els[0].text.strip()
                    if new_cal_date_text != old_cal_date_text:
                        month_changed = True
                        # Short pause to let page fully render
                        await asyncio.sleep(0.5)
                        break
            
            if month_changed:
                break
            else:
                logger.warning(f"   Month did not change, retrying...")
        
        if not month_changed:
            raise ElementMissingError("Failed to navigate to next month after retries. Stopping calendar scan.")
    
    logger.info(f"Calendar scan complete. Found {len(auction_dates)} auction dates.")
    return auction_dates


# --- 4. MAIN EXECUTION ---

async def main():
    browser = await n.start(browser_args=['--start-maximized'])
    
    try:
        # Get initial tab
        tab = await browser.get("about:blank")
        await asyncio.sleep(1)
        
        # Step 1: Collect all auction dates from the calendar
        auction_dates = await collect_auction_dates_from_calendar(tab)
        
        logger.info(f"Will process {len(auction_dates)} auction dates.")
        
        # Step 2: Process each auction date
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Parcel ID", "Address", "Sale Amount", "Assessed Value", "Opening Bid", "Link"])
            
            logger.info(f"Scraper Initialized. Output: {OUTPUT_FILE}")
            
            for i, auction_date in enumerate(auction_dates):
                logger.info(f"Processing auction date {i+1}/{len(auction_dates)}: {auction_date}")
                
                # Skip future auction dates - they can't have sold items
                try:
                    auction_dt = datetime.strptime(auction_date, "%m/%d/%Y")
                    if auction_dt.date() > datetime.now().date():
                        logger.info(f"   Skipping {auction_date} - future date, cannot have sold auctions.")
                        continue
                except ValueError:
                    pass  # If date parsing fails, try to process anyway
                
                # Navigate to auction page for this date
                auction_url = AUCTION_URL_TEMPLATE.format(date=auction_date)
                await tab.get(auction_url)
                await asyncio.sleep(3)
                
                # Check if this auction has closed sales
                should_skip = await step_check_stop_condition(tab)
                if should_skip:
                    logger.info(f"   Skipping {auction_date} - no closed sales (waiting auctions only).")
                    continue
                
                # Get the date string from the page header
                try:
                    date_str = await step_get_date(tab)
                except ElementMissingError:
                    logger.warning(f"   Could not get date from page for {auction_date}. Skipping.")
                    continue
                
                logger.info(f"   Page shows: {date_str}")
                
                # Inner Loop: Extract items from all pages
                while True:
                    try:
                        await step_extract_items(tab, date_str, writer, f)
                    except ElementMissingError as e:
                        logger.warning(f"   {e}")
                        break
                    
                    has_next_page = await step_next_page_of_items(tab)
                    if not has_next_page:
                        break
        
        logger.info("Scraping complete!")
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        browser.stop()

if __name__ == '__main__':
    n.loop().run_until_complete(main())
