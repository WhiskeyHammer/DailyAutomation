import asyncio
import nodriver as n
import csv
import os
from lxml import html
from datetime import datetime

# --- 1. CONFIGURATION & VARIABLES ---

INPUT_CSV   = "tax_sales_2026-01-29.csv"
OUTPUT_FILE = "duval_assessment_and_flips.csv"

# --- DEVELOPMENT OVERRIDE ---
# Format: ("URL", "Date", "Price")
# Set to None to run the full CSV. 
# Set to a tuple to ignore CSV and run just this one case.
TEST_OVERRIDE = None
# Example:
# TEST_OVERRIDE = ("https://paopropertysearch.coj.net/Basic/Detail.aspx?RE=1062010010", "Wednesday September 10, 2025", "$141,100.00 ")

# Filter Settings
TARGET_COUNTY = "Duval"

# XPath Targets (Duval Specific)
XP_VAL_BUILDING      = '(//span[contains(@id,"BuildingValue")])[2]' 
XP_VAL_LAND          = '(//span[contains(@id,"LandValueMarket")])[2]' 
XP_SALES_TABLE_ROWS  = '//table[contains(@id, "gridSales")]//tr[position()>1]'

# Relative XPaths
XP_SALE_DATE         = './td[2]'
XP_SALE_PRICE        = './td[3]'
XP_DEED_TYPE         = './td[4]'
XP_QUALIFIED         = './td[5]'
XP_VACANT_IMP        = './td[6]'

# --- 2. HELPERS ---

def parse_date(date_str):
    """
    Robust date parser that tries multiple formats.
    1. CSV Input Format: "Wednesday September 10, 2025" (%A %B %d, %Y)
    2. Website Table Format: "09/10/2025" (%m/%d/%Y)
    """

    clean_str = date_str.strip()
    
    # List of formats to try
    formats = [
        "%A %B %d, %Y",  # Long: Wednesday September 10, 2025
        "%m/%d/%Y",      # Short: 09/10/2025
        "%Y-%m-%d"       # ISO: 2025-09-10 (Just in case)
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue
            
    # If all fail, return min date so it doesn't crash
    print(f"Warning: Could not parse date '{date_str}'")
    return datetime.min

def clean_price(price_str):
    if not price_str:
        return "0"
    return price_str.replace('$', '').replace(',', '').strip()

# --- 3. EXTRACTION LOGIC ---

async def parse_and_filter_flips(page_html, input_url, input_date_str, input_price_str):
    tree = html.fromstring(page_html)
    found_flips = []

    # A. Parse Input Data
    target_date = parse_date(input_date_str)
    target_price_clean = clean_price(input_price_str)
    
    # B. Extract 2025 Values (Always needed)
    building_val = tree.xpath(XP_VAL_BUILDING)
    land_val = tree.xpath(XP_VAL_LAND)

    # C. Iterate History
    sales_rows = tree.xpath(XP_SALES_TABLE_ROWS)
    
    if sales_rows:
        for row in sales_rows:
            def get_col(xpath):
                nodes = row.xpath(xpath)
                return nodes[0].text_content().strip() if nodes else "N/A"

            hist_date_str  = get_col(XP_SALE_DATE)
            hist_price_str = get_col(XP_SALE_PRICE)
            
            hist_date = parse_date(hist_date_str)
            hist_price_clean = clean_price(hist_price_str)

            # CHECK 1: Skip the reference row (the tax deed sale itself)
            if hist_date == target_date and hist_price_clean == target_price_clean:
                continue

            # CHECK 2: Is this a "Flip" (Newer sale)?
            if hist_date > target_date:
                hist_deed   = get_col(XP_DEED_TYPE)
                hist_qual   = get_col(XP_QUALIFIED)
                hist_vacant = get_col(XP_VACANT_IMP)

                record = [
                    input_url, 
                    input_date_str, 
                    input_price_str, 
                    building_val, 
                    land_val,
                    hist_date_str, 
                    hist_price_str, 
                    hist_deed, 
                    hist_qual, 
                    hist_vacant
                ]
                found_flips.append(record)

    # D. FALLBACK: If no flips found, save the assessment data anyway
    if not found_flips:
        record = [
            input_url, 
            input_date_str, 
            input_price_str, 
            building_val, 
            land_val,
            "N/A", "N/A", "N/A", "N/A", "N/A" # Fill flip cols with N/A
        ]
        found_flips.append(record)

    return found_flips

# --- 4. MAIN EXECUTION ---

async def main():
    browser = await n.start(browser_args=['--start-maximized'])

    tasks = []

    # 1. GET LSIT OF TARGETS TO SCRAPE (override URL or filter a csv)
    if TEST_OVERRIDE:
        print(f"\n!!! USING TEST OVERRIDE MODE !!!")
        print(f"Target: {TEST_OVERRIDE[0]}\n")
        tasks.append(TEST_OVERRIDE)
    else:
        # Normal CSV Processing
        if os.path.exists(INPUT_CSV):
            with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                required_cols = ['Link', 'Date', 'Sale Amount', 'County']
                if not all(col in reader.fieldnames for col in required_cols):
                    print(f"Error: CSV missing columns. Found: {reader.fieldnames}")
                    return

                for row in reader:
                    county = row.get('County', '').strip()
                    if county.lower() != TARGET_COUNTY.lower():
                        continue

                    url = row.get('Link')
                    date = row.get('Date')
                    price = row.get('Sale Amount')
                    
                    if url and url != "N/A":
                        tasks.append((url, date, price))
        else:
            print(f"Error: {INPUT_CSV} not found.")
            return
        
        print(f"Loaded {len(tasks)} properties for {TARGET_COUNTY}...")

    # 2. PROCESS TASKS
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "URL", "Tax Deed Date", "Tax Deed Price", 
            "2025 Bldg", "2025 Land", 
            "FLIP Date", "FLIP Price", "Instrument", "Qualified", "Vacant/Imp"
        ])

        for url, date, price in tasks:
            print(f"Processing: {url}")
            
            try:
                page = await browser.get(url)
                
                try:
                    await page.wait_for("#propValue")
                    await asyncio.sleep(1) 
                except:
                    print("  -> Page load failed")
                    continue

                content = await page.get_content()
                
                # Returns either Flip rows OR a single 'Assessment Only' row
                results = await parse_and_filter_flips(content, url, date, price)

                # Output logging logic
                has_flips = any(r[5] != "N/A" for r in results)
                
                if has_flips:
                    print(f"  -> FOUND {len(results)} NEW SALE(S)!")
                else:
                    print("  -> No new sales. Saving assessment data.")

                writer.writerows(results)
                f.flush()
                
                await asyncio.sleep(1.5)

            except Exception as e:
                print(f"Error processing {url}: {e}")

    # browser.stop()

if __name__ == '__main__':
    n.loop().run_until_complete(main())