import asyncio
import random
import nodriver as n
import csv
import os
import sys
import glob
from lxml import html
from datetime import datetime

# --- 1. GLOBAL CONFIGURATION ---

# Get the project root directory (two levels up from this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# --- PROXY SETUP ---
sys.path.append(PROJECT_ROOT)
try:
    from proxy_manager import create_proxy_auth_extension, get_random_proxy
except ImportError:
    print("Warning: Could not import proxy_manager. Running without proxy.")
    get_random_proxy = lambda x: None
    create_proxy_auth_extension = lambda x, y: None

PROXY_FILE = os.path.join(PROJECT_ROOT, "proxies.txt")
# -------------------

# Find the most recent tax_sales CSV file
AUCTION_DIR = os.path.dirname(SCRIPT_DIR)
PAST_AUCTIONS_DIR = os.path.join(AUCTION_DIR, "past_auctions")
tax_sales_files = glob.glob(os.path.join(PAST_AUCTIONS_DIR, "tax_sales_*.csv"))
INPUT_CSV = sorted(tax_sales_files)[-1] if tax_sales_files else os.path.join(PAST_AUCTIONS_DIR, "tax_sales.csv")

PARCEL_HISTORY_DIR = os.path.join(AUCTION_DIR, "parcel_history")
os.makedirs(PARCEL_HISTORY_DIR, exist_ok=True)

# Generate timestamp for output files (down to the second)
RUN_TIMESTAMP = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

# --- OVERRIDES ---

# Option A: Single URL Override (Parcel ID is CRITICAL for Clay tests now)
# Format: ("URL", "Date", "Price", "Parcel ID", "County")
TEST_OVERRIDE = None 
# Example for Clay Test:
# TEST_OVERRIDE = ("IGNORE_THIS_URL", "11/19/2025", "$18,900", "19-08-24-007802-044-00", "Clay")

# Option B: Single County Override (set to None to process all counties)
OVERRIDE_COUNTY = os.environ.get("OVERRIDE_COUNTY")

# --- COUNTY DEFINITIONS ---
COUNTY_CONFIGS = {
    "Duval": {
        "banned_phrases": ["No Results Found"],
        "output_file": os.path.join(AUCTION_DIR, "parcel_history", f"duval_assessment_and_flips_{RUN_TIMESTAMP}.csv"),
        "wait_target": "//*[@id='propValue']",
        "xp_val_bldg": '(//span[contains(@id,"BuildingValue")])[2]',
        "xp_val_land": '(//span[contains(@id,"LandValueMarket")])[2]',
        "xp_rows": '//table[contains(@id, "gridSales")]//tr[position()>1]',
        "xp_date": './td[2]',
        "xp_price": './td[3]',
        "xp_deed": './td[4]',
        "xp_qual": './td[5]',
        "xp_vacant": './td[6]',
    },
    "Baker": {
        "output_file": os.path.join(AUCTION_DIR, "parcel_history", f"baker_assessment_and_flips_{RUN_TIMESTAMP}.csv"),
        "wait_target": "//*[contains(text(), 'Value Information')]",
        "xp_val_bldg": '//div[contains(text(),"BUILDING VALUE:")]/following-sibling::div',
        "xp_val_land": '//div[contains(text(),"LAND VALUE:")]/following-sibling::div',
        "xp_rows": '//h4[contains(text(),"RECENTS SALES")]/following-sibling::div//table//tr[position()>1]',
        "xp_date": './td[2]',
        "xp_price": './td[8]',
        "xp_deed": './td[3]',
        "xp_qual": './td[4]',
        "xp_vacant": './td[5]',
    },
    "Clay": {
        "output_file": os.path.join(AUCTION_DIR, "parcel_history", f"clay_assessment_and_flips_{RUN_TIMESTAMP}.csv"),
        # --- NEW SEARCH WORKFLOW CONFIG ---
        "click_agree": "//a[text()='Agree']",
        "search_url": "https://qpublic.schneidercorp.com/Application.aspx?AppID=830&LayerID=15008&PageTypeID=2&PageID=6754",
        "search_input_xpath": "//input[contains(@name,'txtParcelID')]",
        "search_btn": "//section[.//*[contains(text(),'Search by Parcel Number with Sec/Twp/Rng')]]//a[@searchintent='ParcelID']",
        # Phrases that indicate wrong page - add phrases here to trigger retry
        "banned_phrases": [],
        "failure_phrases": ["500 Results (Maximum)", "403 Forbidden", "we apologize for the inconvenience"],
        # ----------------------------------
        "wait_target": "//*[text()='Valuation']",
        "xp_val_bldg": '//table[contains(@class,"table")]//tr[contains(.,"Building Value")]/td[2]',
        "xp_val_land": '//table[contains(@class,"table")]//tr[contains(.,"Land Value") and not(contains(.,"Agricultural"))]/td[2]',
        "xp_rows": '//table[caption[contains(text(),"Sales")]]//tbody/tr',
        "xp_date": './th[1]',
        "xp_price": './td[1]',
        "xp_deed": './td[2]',
        "xp_qual": './td[5]',
        "xp_vacant": './td[8]',
    },
    "Nassau": {
        "output_file": os.path.join(AUCTION_DIR, "parcel_history", f"nassau_assessment_and_flips_{RUN_TIMESTAMP}.csv"),
        "wait_target": "SALES INFORMATION",
        "xp_val_bldg": '//table//tr[td[contains(text(),"Improved Value")]]/td[2]',
        "xp_val_land": '//table//tr[td[contains(text(),"Land Value")]]/td[2]',
        "xp_rows": '//div[contains(.,"SALES INFORMATION")]/following-sibling::*//tr[position()>1]',
        "xp_date": './td[1]',
        "xp_price": './td[3]',
        "xp_deed": './td[4]',
        "xp_qual": './td[5]',
        "xp_vacant": './td[6]',
    }
}

# --- 2. HELPERS ---

def parse_date(date_str):
    if not date_str: return datetime.min
    clean_str = date_str.strip()
    formats = ["%A %B %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"]
    for fmt in formats:
        parsed = None
        try: 
            parsed = datetime.strptime(clean_str, fmt)
        except ValueError: 
            continue
        if parsed:
            return parsed
    return datetime.min

def clean_price(price_str):
    if not price_str: return "0"
    return price_str.replace('$', '').replace(',', '').strip()

async def safe_get_text(tree, xpath):
    nodes = tree.xpath(xpath)
    return nodes[0].text_content().strip() if nodes else "N/A"

async def wait_for_xpath(page, xpath, attempts, pause_length):
    elem = []
    for _ in range(attempts):
        try:
            elem = await page.xpath(xpath)
            if elem:
                return
            await asyncio.sleep(pause_length)
        except:
            pass
    raise Exception("Element not found")        


async def get_to_parcel_page(config, browser, pid, url, agree_clicked=False, search_page=None):
    """
    Navigate to a parcel page. Returns (page, agree_clicked, needs_manual_review, search_page).
    If needs_manual_review is True, the page contains banned phrases and should be skipped.
    For search-based counties (Clay), reuses the search page instead of reloading it each time.
    """
    max_retries = 10
    banned_phrases = config.get("banned_phrases", [])
    failure_phrases = config.get("failure_phrases", [])

    for attempt in range(max_retries):
        try:
            if "search_url" in config:
                # Only load the search page if we don't have one yet (first property or after error)
                if search_page is None or attempt > 0:
                    search_page = await browser.get(config['search_url'])
                    await force_active_session(search_page)

                    # Handle 'Agree' button - only if not already clicked
                    if 'click_agree' in config and not agree_clicked:
                        await wait_for_xpath(search_page, config['click_agree'], 10, 1)
                        btn = await search_page.xpath(config['click_agree'])
                        await btn[0].click()
                        agree_clicked = True
                        print("  -> Agree button clicked, will skip on future runs")
                        await asyncio.sleep(random.uniform(1, 2))
                else:
                    # Navigate back to search page without full reload
                    await search_page.back()
                    await asyncio.sleep(random.uniform(1.5, 3))

                # Find Input & Type PID
                await wait_for_xpath(search_page, config['search_input_xpath'], 10, 1)
                await asyncio.sleep(random.uniform(0.5, 1.5))
                input_el = await search_page.xpath(config['search_input_xpath'])
                if input_el:
                    await input_el[0].clear_input()
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                    await input_el[0].send_keys(pid)

                    await wait_for_xpath(search_page, config["search_btn"], 10, 1)
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    search_btn = await search_page.xpath(config["search_btn"])
                    await search_btn[0].scroll_into_view()
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                    await search_btn[0].click()
                    await asyncio.sleep(random.uniform(1, 2))
                else:
                    raise Exception(f"Critical: Search input not found for {pid}")

                page = search_page
            else:
                # >>> STANDARD WORKFLOW (Direct URL) >>>
                page = await browser.get(url)
                await asyncio.sleep(1)

            # --- COMMON WAIT & PARSE ---
            
            # 3. Check for banned phrases - if found, mark for manual review (no retry)
            if banned_phrases:
                page_content = await page.get_content()
                for phrase in banned_phrases:
                    if phrase.lower() in page_content.lower():
                        print(f"  -> BANNED PHRASE DETECTED: '{phrase}' - marking for manual review")
                        return page, agree_clicked, True  # needs_manual_review = True
                    
            # 3. Check for failure indicator phrases - if found, raise error and retry
            if failure_phrases:
                page_content = await page.get_content()
                for phrase in failure_phrases:
                    if phrase.lower() in page_content.lower():
                        print(f"  -> FAILURE PHRASE DETECTED: '{phrase}' - retrying")
                        raise   Exception("Found a failure indicator")

            # 4. Wait for Property Page Load
            await wait_for_xpath(page, config['wait_target'], 10, 1)
            await asyncio.sleep(1.5)
            
            return page, agree_clicked, False, search_page

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  -> Failed to load property page (attempt {attempt + 1}/{max_retries}), retrying...")
                await asyncio.sleep(1)
                search_page = None  # Force full reload on retry
                continue
            # All retries exhausted - mark for manual review instead of crashing
            print(f"  -> FAILED after {max_retries} attempts - marking for manual review")
            return None, agree_clicked, True, None

    # Should not reach here, but just in case
    print(f"  -> FAILED to navigate to property page for {pid} - marking for manual review")
    return None, agree_clicked, True, None

async def force_active_session(page):
    """
    Tricks the browser into thinking the window has focus and is active.
    This prevents the site from redirecting/blocking searches when running in the background.
    """
    # 1. CDP Command: Force Chrome to report "focused" to the page
    # This is the most powerful method as it handles the browser engine level.
    try:
        await page.send(n.cdp.emulation.set_focus_emulation_enabled(True))
    except Exception:
        pass # Fail silently if strict CDP types aren't loaded, JS fallback below catches it.

    # 2. JS Injection: Overwrite the visibility and focus properties
    # This catches scripts that manually check document.hidden or window.onblur
    await page.evaluate("""
        Object.defineProperty(document, 'visibilityState', {get: () => 'visible'});
        Object.defineProperty(document, 'hidden', {get: () => false});
        Document.prototype.hasFocus = function() { return true; };
        window.onblur = null;
        window.onfocus = null;
    """)
    
# --- 3. CORE LOGIC ---

async def parse_property(page_html, url, date_str, price_str, pid, config):
    tree = html.fromstring(page_html)
    found_rows = []

    # A. Parse Input
    target_date = parse_date(date_str)
    target_price_clean = clean_price(price_str)

    # B. Extract Assessment Values
    bldg_val = await safe_get_text(tree, config['xp_val_bldg'])
    land_val = await safe_get_text(tree, config['xp_val_land'])

    # C. Iterate History
    sales_rows = tree.xpath(config['xp_rows'])
    
    has_flips = False
    if sales_rows:
        for row in sales_rows:
            def get_col(rel_xpath):
                nodes = row.xpath(rel_xpath)
                return nodes[0].text_content().strip() if nodes else "N/A"

            h_date_str = get_col(config['xp_date'])
            h_price_str = get_col(config['xp_price'])
            
            h_date = parse_date(h_date_str)
            h_price_clean = clean_price(h_price_str)

            # Skip the tax deed sale itself
            if h_date == target_date and h_price_clean == target_price_clean:
                continue

            # Check for Flip (Newer than Tax Deed)
            if h_date > target_date:
                hist_deed = get_col(config['xp_deed'])
                
                # Skip if this is a Tax Deed (sometimes registered after actual sale)
                if "tax deed" in hist_deed.lower() or "TD" in hist_deed.upper():
                    continue
                
                has_flips = True
                found_rows.append([
                    url, pid, date_str, price_str, bldg_val, land_val,
                    h_date_str, h_price_str,
                    hist_deed,
                    get_col(config['xp_qual']),
                    get_col(config['xp_vacant'])
                ])

    # D. Fallback (No flips found)
    if not has_flips:
        found_rows.append([
            url, pid, date_str, price_str, bldg_val, land_val,
            "N/A", "N/A", "N/A", "N/A", "N/A"
        ])

    return found_rows

async def process_county_batch(browser, county_name, tasks):
    """
    Process all properties for a county. For Clay, rotates proxy every
    CLAY_PROXY_ROTATE_EVERY properties to avoid rate-limiting.
    Returns the (possibly new) browser instance.
    """
    config = COUNTY_CONFIGS.get(county_name)
    if not config:
        print(f"Skipping unknown county: {county_name}")
        return browser

    agree_clicked = False
    search_page = None
    since_rotate = 0

    output_file = config['output_file']
    print(f"\n--- Starting {county_name} ({len(tasks)} properties) -> {output_file} ---")

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "URL", "Parcel ID", "Tax Deed Date", "Tax Deed Price",
            "Bldg Value", "Land Value",
            "FLIP Date", "FLIP Price", "Instrument", "Qualified", "Vacant/Imp"
        ])

        # Verify proxy on first launch for Clay
        if county_name == "Clay":
            ip = await verify_proxy(browser)
            if ip:
                print(f"  [PROXY] Starting Clay with external IP: {ip}")
            else:
                print(f"  [WARNING] Could not verify proxy — proceeding anyway")

        for i, (url, date, price, pid) in enumerate(tasks):
            # Rotate proxy for Clay every N properties
            if county_name == "Clay" and since_rotate >= CLAY_PROXY_ROTATE_EVERY:
                print(f"\n  >> Rotating proxy (after {since_rotate} properties)...")
                browser.stop()
                await asyncio.sleep(2)
                browser = await launch_browser()
                agree_clicked = False
                search_page = None
                since_rotate = 0

                # Verify the new proxy is actually working
                new_ip = await verify_proxy(browser)
                if new_ip:
                    print(f"  [PROXY] New external IP: {new_ip}")
                else:
                    print(f"  [WARNING] Proxy verification failed — proceeding anyway")

            page, agree_clicked, needs_manual_review, search_page = await get_to_parcel_page(config, browser, pid, url, agree_clicked, search_page)

            if needs_manual_review:
                writer.writerow([
                    url, pid, date, price,
                    "MANUAL REVIEW", "MANUAL REVIEW",
                    "MANUAL REVIEW", "MANUAL REVIEW", "MANUAL REVIEW", "MANUAL REVIEW", "MANUAL REVIEW"
                ])
                f.flush()
                await asyncio.sleep(1)
                continue

            content = await page.get_content()
            results = await parse_property(content, url, date, price, pid, config)

            flips_count = sum(1 for r in results if r[6] != "N/A")
            if flips_count:
                print(f"  -> FOUND {flips_count} NEW SALE(S)!")
            else:
                print("  -> No new sales.")

            writer.writerows(results)
            f.flush()
            since_rotate += 1

            if county_name == "Clay":
                await asyncio.sleep(random.uniform(3, 7))
            else:
                await asyncio.sleep(1)

    return browser

# --- 4. MAIN ---

# How many properties to process before rotating proxy (Clay only)
CLAY_PROXY_ROTATE_EVERY = 5

try:
    from window_utils import get_chrome_window_args, move_chrome_to_vscode_monitor
except ImportError:
    get_chrome_window_args = None
    move_chrome_to_vscode_monitor = None


async def launch_browser():
    """Launch a fresh browser with a random proxy and correct monitor position."""
    browser_args = ['--start-maximized']

    if get_chrome_window_args:
        browser_args.extend(get_chrome_window_args())

    proxy_str = get_random_proxy(PROXY_FILE)
    if proxy_str:
        print(f"Using Proxy: {proxy_str}")
        ext_path = os.path.join(SCRIPT_DIR, "chrome_proxy_auth_ext")
        if create_proxy_auth_extension(proxy_str, ext_path):
            browser_args.append(f"--load-extension={ext_path}")
    else:
        print("No proxy found (or proxies.txt is missing). Running with Direct Connection.")

    browser = await n.start(browser_args=browser_args)

    if move_chrome_to_vscode_monitor:
        await asyncio.sleep(1)
        move_chrome_to_vscode_monitor()

    return browser


async def verify_proxy(browser):
    """Check external IP and return it. Returns None on failure."""
    try:
        tab = await browser.get("https://api.ipify.org")
        await asyncio.sleep(2)
        ip = (await tab.evaluate("document.body.innerText")).strip()
        return ip
    except Exception as e:
        print(f"  [PROXY CHECK FAILED] {e}")
        return None


async def main():
    browser = await launch_browser()

    county_tasks = {k: [] for k in COUNTY_CONFIGS.keys()}

    if TEST_OVERRIDE:
        print(f"\n!!! USING SINGLE TASK OVERRIDE !!!")
        ov_url, ov_date, ov_price, ov_pid, ov_county = TEST_OVERRIDE
        if ov_county in county_tasks:
            county_tasks[ov_county].append((ov_url, ov_date, ov_price, ov_pid))
    
    elif os.path.exists(INPUT_CSV):
        if OVERRIDE_COUNTY:
             print(f"\n!!! USING COUNTY OVERRIDE: {OVERRIDE_COUNTY} !!!")

        with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                c = row.get('County', '').strip()
                c_key = c.capitalize() if c.capitalize() in COUNTY_CONFIGS else c
                
                if OVERRIDE_COUNTY and c_key != OVERRIDE_COUNTY:
                    continue

                if c_key in county_tasks:
                    url = row.get('Link')
                    # For Clay, we accept "N/A" URLs because we search by PID
                    if "search_url" in COUNTY_CONFIGS[c_key] or (url and url != "N/A"):
                        county_tasks[c_key].append((
                            url, 
                            row.get('Date'), 
                            row.get('Sale Amount'), 
                            row.get('Parcel ID', 'N/A')
                        ))
    else:
        print(f"Input file {INPUT_CSV} not found.")
        return

    # Execute batches - Clay first, then the rest
    # (Clay uses a search workflow that requires active session management)
    COUNTY_ORDER = ["Clay", "Duval", "Baker", "Nassau"]
    
    for county in COUNTY_ORDER:
        if county in county_tasks and county_tasks[county]:
            browser = await process_county_batch(browser, county, county_tasks[county])

    # browser.stop()

if __name__ == '__main__':
    n.loop().run_until_complete(main())