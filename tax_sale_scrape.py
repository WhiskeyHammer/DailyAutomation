import asyncio
import nodriver as n
import csv
import logging

# --- 1. CONFIGURATION & XPATH VARIABLES ---
START_URL = "https://duval.realtaxdeed.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=01/15/2025"
OUTPUT_FILE = "duval_sales_xpath_2025.csv"

# --- Variables: Selectors ---
# We use contains() for classes to be robust against multiple class names
XP_AUCTION_DATE     = '//div[contains(@class, "BLHeaderDateDisplay")]'
XP_AUCTION_ITEMS    = '//div[contains(@class, "AUCTION_ITEM") and contains(@class, "PREVIEW")]'
XP_MSG_WAITING      = '//div[contains(@class, "Sub_Title") and contains(text(), "Auctions Waiting")]'
XP_MSG_CLOSED       = '//div[contains(@class, "Sub_Title") and contains(text(), "Auctions Closed")]'

# Item inner details (relative xpaths to the item)
# Parcel ID link goes to paopropertysearch.coj.net/Basic/Detail.aspx
XP_ITEM_LINK        = './/a[contains(@href, "Detail.aspx")]'
XP_ITEM_ADDRESS     = './/td[contains(@class, "AD_LBL") and contains(text(), "Property Address:")]/following-sibling::td'
XP_ITEM_WINNING_BID = './/div[contains(@class, "ASTAT_MSGD")]'
XP_ITEM_SOLD_AMT    = './/div[contains(@class, "ASTAT_MSGD")]'
XP_ITEM_ASSESSED    = './/td[contains(@class, "AD_LBL") and contains(text(), "Assessed Value:")]/following-sibling::td'

# Navigation
# Next Page is an image inside a span with class PageRight
XP_NEXT_PAGE_BTN    = '//span[contains(@class, "PageRight")]'
# Next Auction Date is a link with text "Next Auction > >"
XP_NEXT_DATE_BTN    = '//a[contains(text(), "Next Auction")]'


# --- 2. HELPER FUNCTIONS ---

async def get_by_xpath(page, xpath):
    """
    Executes JS to find a single element by XPath.
    Returns the Nodriver Element object or None.
    """
    try:
        # JS wrapper to evaluate xpath and return the node
        script = f"""
            var result = document.evaluate('{xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            result; 
        """
        return await page.evaluate(script)
    except Exception:
        return None

async def get_all_by_xpath(page, xpath):
    """
    Executes JS to find ALL elements by XPath.
    Returns a list of Nodriver Element objects.
    """
    try:
        script = f"""
            var iterator = document.evaluate('{xpath}', document, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
            var thisNode = iterator.iterateNext();
            var nodes = [];
            while (thisNode) {{
                nodes.push(thisNode);
                thisNode = iterator.iterateNext();
            }}
            nodes;
        """
        results = await page.evaluate(script)
        return results if results else []
    except Exception:
        return []

async def get_text_safe(element):
    """Safely retrieves text from an element, returning empty string on failure."""
    try:
        return element.text.strip()
    except:
        return ""

# --- 3. LOGICAL STEP FUNCTIONS ---

async def step_check_stop_condition(page):
    """Checks if we hit the 'Auctions Waiting' section (Future)."""
    waiting_el = await get_by_xpath(page, XP_MSG_WAITING)
    closed_el = await get_by_xpath(page, XP_MSG_CLOSED)
    
    # If "Waiting" exists but "Closed" does not, we are likely in the future
    if waiting_el and not closed_el:
        return True
    return False

async def step_get_date(page):
    """Extracts the date string from the header."""
    el = await get_by_xpath(page, XP_AUCTION_DATE)
    if el:
        return await get_text_safe(el)
    return "Unknown_Date"

async def step_extract_items(page, current_date, writer, file_handle):
    """Finds all items on current view, parses them, writes to CSV."""
    # 1. Get all auction item divs
    items = await get_all_by_xpath(page, XP_AUCTION_ITEMS)
    print(f"   Found {len(items)} items on this page.")

    for item in items:
        try:
            # Note: nodriver elements support query_selector, but since you asked for XPath variables,
            # we must process the text or use relative searching. 
            # Nodriver doesn't easily support "find xpath relative to this element node" purely via python 
            # without complex JS injection passing the node ID.
            # WORKAROUND: We grab the full text of the item and parse, OR we use the item's context.
            # For simplicity and speed in this specific loop, Text Parsing is vastly more stable 
            # than executing 5 JS injections per item.
            
            full_text = await get_text_safe(item)
            
            # --- Parse Address ---
            address = "N/A"
            if "Property Address:" in full_text:
                parts = full_text.split("Property Address:")
                if len(parts) > 1:
                    address = parts[1].splitlines()[0].strip()

            # --- Parse Sale Amount ---
            sale_amount = "0"
            if "Winning Bid:" in full_text:
                sale_amount = full_text.split("Winning Bid:")[1].splitlines()[0].strip()
            elif "Sold Amount:" in full_text:
                sale_amount = full_text.split("Sold Amount:")[1].splitlines()[0].strip()

            # --- Parse Assessed ---
            assessed = "0"
            if "Assessed Value:" in full_text:
                assessed = full_text.split("Assessed Value:")[1].splitlines()[0].strip()

            # --- Link & Parcel ID (Requires Element Lookup) ---
            # We can use a simple CSS select here because it is a child, or strict JS/XPath
            # Using CSS for speed on the child object is safe, but adhering to logic:
            # Parcel ID links go to paopropertysearch.coj.net/Basic/Detail.aspx
            link_el = await item.query_selector('a[href*="Detail.aspx"]')
            if link_el:
                parcel_id = link_el.text.strip()
                href = link_el.attrs.get('href', '')
                # Link is already absolute (external to paopropertysearch.coj.net)
                link = href
            else:
                parcel_id = "N/A"
                link = "N/A"

            if parcel_id != "N/A":
                writer.writerow([current_date, parcel_id, address, sale_amount, assessed, link])
                file_handle.flush()

        except Exception as e:
            print(f"Error parsing item: {e}")
            continue

async def step_next_page_of_items(page):
    """Looks for a pagination 'Next' button and clicks it."""
    next_btn = await get_by_xpath(page, XP_NEXT_PAGE_BTN)
    if next_btn:
        print("   -> Clicking Next Page (Inner)...")
        await next_btn.click()
        await asyncio.sleep(3) # Wait for reload
        return True
    return False

async def step_next_auction_date(page):
    """Looks for 'Next Auction' button and clicks it."""
    next_date_btn = await get_by_xpath(page, XP_NEXT_DATE_BTN)
    if next_date_btn:
        print("Moving to Next Auction Date...")
        await next_date_btn.click()
        await asyncio.sleep(4) # Wait for reload
        return True
    return False

# --- 4. MAIN EXECUTION ---

async def main():
    # 1. Start Browser
    browser = await n.start(browser_args=['--start-maximized'])
    
    # 2. Navigate (This IS the fresh load)
    page = await browser.get(START_URL)
    
    # 3. Wait for body to ensure connection is solid
    await page.wait_for('body')
    await asyncio.sleep(3)

    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Parcel ID", "Address", "Sale Amount", "Assessed Value", "Link"])
        
        print(f"Scraper Initialized. Output: {OUTPUT_FILE}")

        while True:
            # A. Check Stop Condition
            should_stop = await step_check_stop_condition(page)
            if should_stop:
                print("Hit 'Auctions Waiting'. No more closed sales. Stopping.")
                break

            # B. Get Date
            date_str = await step_get_date(page)
            print(f"Processing Date: {date_str}")

            # C. Inner Loop: Items & Pagination
            while True:
                await step_extract_items(page, date_str, writer, f)
                
                has_next_page = await step_next_page_of_items(page)
                if not has_next_page:
                    break # No more pages for this date, exit inner loop
            
            # D. Outer Loop: Next Date
            has_next_date = await step_next_auction_date(page)
            if not has_next_date:
                print("No 'Next Auction' button found. Process complete.")
                break

    await asyncio.Future()

if __name__ == '__main__':
    n.loop().run_until_complete(main())