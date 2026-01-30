import asyncio
import nodriver as n
import csv
import os
from lxml import html
from datetime import datetime

# --- 1. CONFIGURATION & VARIABLES ---

INPUT_CSV   = "tax_sales_2026-01-29.csv"
OUTPUT_FILE = "nassau_assessment_and_flips.csv"

# --- DEVELOPMENT OVERRIDE ---
# Format: ("URL", "Date", "Price", "Parcel ID")
# Set to None to run the full CSV. 
# Set to a tuple to ignore CSV and run just this one case.
TEST_OVERRIDE = None
# Example:
# TEST_OVERRIDE = ("https://maps.ncpafl.com/NassauDetails/ParcelSearchResults.html?PIN=16-1N-25-2912-0001-0011", "Wednesday August 28, 2025", "$39,200", "16-1N-25-2912-0001-0011")

# Filter Settings
TARGET_COUNTY = "Nassau"

# XPath Targets (Nassau County Specific - maps.ncpafl.com)
# Value Information from 2024 Certified Values table
# Land Value is in row 1, column 2
XP_VAL_LAND = '//table//tr[td[contains(text(),"Land Value")]]/td[2]'
# Improved Value (Building) is in row 2, column 2
XP_VAL_BUILDING = '//table//tr[td[contains(text(),"Improved Value")]]/td[2]'

# Sales Information table rows (in LayoutTable under SALES INFORMATION)
XP_SALES_TABLE_ROWS = '//div[contains(.,"SALES INFORMATION")]/following-sibling::*//tr[position()>1]'

# Relative XPaths for sales table columns (Nassau County structure)
# Columns: Sale Date, Book Page, Price, Instr, Qual, Imp, Grantor, Grantee
XP_SALE_DATE = './td[1]'   # Sale Date
XP_SALE_PRICE = './td[3]'  # Price
XP_DEED_TYPE = './td[4]'   # Instr (Instrument type: TD, WD, QC)
XP_QUALIFIED = './td[5]'   # Qual (Q = Qualified, U = Unqualified)
XP_VACANT_IMP = './td[6]'  # Imp (V = Vacant, I = Improved)

# --- 2. HELPERS ---

def parse_date(date_str):
    clean_str = date_str.strip()
    formats = [
        "%A %B %d, %Y",  # Long: Wednesday September 10, 2025
        "%m/%d/%Y",      # Short: 09/10/2025
        "%Y-%m-%d",      # ISO: 2025-09-10 (Nassau County format)
        "%d/%m/%Y",      # European: 10/09/2025
    ]
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue
    print(f"Warning: Could not parse date '{date_str}'")
    return datetime.min

def clean_price(price_str):
    if not price_str:
        return "0"
    return price_str.replace('$', '').replace(',', '').strip()

# --- 3. EXTRACTION LOGIC ---

async def parse_and_filter_flips(page_html, input_url, input_date_str, input_price_str, input_parcel_id):
    tree = html.fromstring(page_html)
    found_flips = []

    # A. Parse Input Data
    target_date = parse_date(input_date_str)
    target_price_clean = clean_price(input_price_str)
    
    # B. Extract 2024 Values (Nassau County shows 2024 Certified Values)
    b_nodes = tree.xpath(XP_VAL_BUILDING)
    building_val = b_nodes[0].text_content().strip() if b_nodes else "N/A"
    
    l_nodes = tree.xpath(XP_VAL_LAND)
    land_val = l_nodes[0].text_content().strip() if l_nodes else "N/A"

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

            # CHECK 1: Skip the reference row
            if hist_date == target_date and hist_price_clean == target_price_clean:
                continue

            # CHECK 2: Is this a "Flip" (Newer sale)?
            if hist_date > target_date:
                hist_deed   = get_col(XP_DEED_TYPE)
                hist_qual   = get_col(XP_QUALIFIED)
                hist_vacant = get_col(XP_VACANT_IMP)

                record = [
                    input_url,
                    input_parcel_id,
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

    # D. FALLBACK: Save assessment data even if no flips
    if not found_flips:
        record = [
            input_url,
            input_parcel_id,
            input_date_str, 
            input_price_str, 
            building_val,
            land_val,
            "N/A", "N/A", "N/A", "N/A", "N/A"
        ]
        found_flips.append(record)

    return found_flips

# --- 4. MAIN EXECUTION ---

async def main():
    browser = await n.start(browser_args=['--start-maximized'])

    tasks = []

    # 1. GET LIST OF TARGETS
    if TEST_OVERRIDE:
        print(f"\n!!! USING TEST OVERRIDE MODE !!!")
        print(f"Target: {TEST_OVERRIDE[0]}\n")
        tasks.append(TEST_OVERRIDE)
    else:
        if os.path.exists(INPUT_CSV):
            with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                required_cols = ['Link', 'Date', 'Sale Amount', 'County', 'Parcel ID']
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
                    pid = row.get('Parcel ID', 'N/A')
                    
                    if url and url != "N/A":
                        tasks.append((url, date, price, pid))
        else:
            print(f"Error: {INPUT_CSV} not found.")
            return
        
        print(f"Loaded {len(tasks)} properties for {TARGET_COUNTY}...")

    # 2. PROCESS TASKS
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "URL", "Parcel ID", "Tax Deed Date", "Tax Deed Price", 
            "2024 Bldg", "2024 Land", 
            "FLIP Date", "FLIP Price", "Instrument", "Qualified", "Vacant/Imp"
        ])

        for url, date, price, pid in tasks:
            print(f"Processing: {url}")
            
            try:
                page = await browser.get(url)
                
                # Wait for the page to load - look for SALES INFORMATION section
                try:
                    await page.wait_for("SALES INFORMATION", timeout=15)
                    await asyncio.sleep(2)  # Extra time for dynamic content
                except:
                    print("  -> Page load failed or timeout")
                    continue

                content = await page.get_content()
                
                results = await parse_and_filter_flips(content, url, date, price, pid)

                has_flips = any(r[6] != "N/A" for r in results)
                
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
