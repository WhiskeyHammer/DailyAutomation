import asyncio
import nodriver as n
import csv
import os
from lxml import html
from datetime import datetime

# --- 1. CONFIGURATION & VARIABLES ---

INPUT_CSV   = "tax_sales_2026-01-29.csv"
OUTPUT_FILE = "duval_assessment_and_flips.csv" # Renamed slightly to reflect content

# Filter Settings
TARGET_COUNTY = "Duval"

# XPath Targets (Duval Specific)
XP_ROW_2025          = '//table[contains(@id, "gridValues")]//tr[td[contains(text(), "2025")]]'
XP_VAL_BUILDING      = './td[3]' 
XP_VAL_LAND          = './td[2]' 
XP_SALES_TABLE_ROWS  = '//table[contains(@id, "gridSales")]//tr[position()>1]'

# Relative XPaths
XP_SALE_DATE         = './td[1]'
XP_SALE_PRICE        = './td[2]'
XP_DEED_TYPE         = './td[3]'
XP_QUALIFIED         = './td[5]'
XP_VACANT_IMP        = './td[6]'

# --- 2. HELPERS ---

def parse_date(date_str):
    if not date_str:
        return datetime.min
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y")
    except ValueError:
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
    row_2025 = tree.xpath(XP_ROW_2025)
    building_val = "N/A"
    land_val = "N/A"
    if row_2025:
        r = row_2025[0]
        b_nodes = r.xpath(XP_VAL_BUILDING)
        if b_nodes: building_val = b_nodes[0].text_content().strip()
        l_nodes = r.xpath(XP_VAL_LAND)
        if l_nodes: land_val = l_nodes[0].text_content().strip()

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
                    await asyncio.sleep(1) # Fixed: usage of await asyncio.sleep
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