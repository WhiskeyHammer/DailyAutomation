"""
SAM.gov Contract Opportunities Scraper using nodriver.

Navigates to a SAM.gov search results page, waits for dynamic content to load
using a stabilization-check loop, extracts row data (link, notice ID, updated
date) from each result, and paginates through every page.

Requirements:
    pip install nodriver

Usage:
    python sam_scraper.py
"""

import asyncio
import json
import logging
import re
from datetime import datetime

import nodriver as uc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

START_URL = ("https://sam.gov/search/?page=1&pageSize=25&sort=-modifiedDate&sfm%5BsimpleSearch%5D%5BkeywordRadio%5D=ANY&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B0%5D%5Bkey%5D=%22C-UAS%22&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B0%5D%5Bvalue%5D=%22C-UAS%22&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B1%5D%5Bkey%5D=drone&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B1%5D%5Bvalue%5D=drone&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B2%5D%5Bkey%5D=suas&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B2%5D%5Bvalue%5D=suas&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B3%5D%5Bkey%5D=fpv&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B3%5D%5Bvalue%5D=fpv&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B4%5D%5Bkey%5D=uas&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B4%5D%5Bvalue%5D=uas&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B5%5D%5Bkey%5D=uav&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B5%5D%5Bvalue%5D=uav&sfm%5Bstatus%5D%5Bis_active%5D=true")

# --- Configuration ---
STABLE_ITERATIONS = 5       # Number of consecutive stable checks before considering page loaded
STABLE_CHECK_DELAY = 0.5    # Seconds between each stability check
INITIAL_LOAD_WAIT = 3       # Seconds to wait after initial page load / next-page click
MAX_WAIT_CYCLES = 60        # Safety cap: max stability checks before giving up


async def wait_for_rows_stable(page, selector="app-opportunity-result"):
    """
    Wait until the number of elements matching *selector* stops changing.

    Counts the elements in a loop with a short delay.  Once the count is the
    same for STABLE_ITERATIONS consecutive checks the page is considered fully
    loaded and we return the count.
    """
    stable_count = 0
    previous_count = -1

    for cycle in range(MAX_WAIT_CYCLES):
        try:
            elements = await page.query_selector_all(selector)
            current_count = len(elements) if elements else 0
        except Exception:
            current_count = 0

        if current_count == previous_count and current_count > 0:
            stable_count += 1
            if stable_count >= STABLE_ITERATIONS:
                logger.info(
                    f"  Page stabilised with {current_count} rows "
                    f"(stable for {STABLE_ITERATIONS} checks)"
                )
                return current_count
        else:
            stable_count = 0

        previous_count = current_count
        await page.sleep(STABLE_CHECK_DELAY)

    # If we exhaust cycles, return whatever we have
    logger.warning(
        f"  Stability cap reached after {MAX_WAIT_CYCLES} cycles. "
        f"Proceeding with {previous_count} links."
    )
    return previous_count


def normalize_date(raw_date):
    """
    Convert a human-readable date string from SAM.gov into ISO 8601 format
    so it can be compared with scraped_at timestamps in the database.

    Handles common SAM.gov formats:
        'Jan 15, 2025'   -> '2025-01-15T00:00:00'
        '01/15/2025'     -> '2025-01-15T00:00:00'
        '2025-01-15'     -> '2025-01-15T00:00:00'
    Returns the original string unchanged if no format matches.
    """
    if not raw_date:
        return raw_date

    formats = [
        "%b %d, %Y",   # Jan 15, 2025
        "%B %d, %Y",   # January 15, 2025
        "%m/%d/%Y",    # 01/15/2025
        "%Y-%m-%d",    # 2025-01-15
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw_date.strip(), fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue

    logger.warning(f"Could not parse date '{raw_date}' – storing as-is")
    return raw_date


async def extract_rows(page):
    """Extract link, ID, and updated date from each app-opportunity-result row."""
    rows = await page.query_selector_all("app-opportunity-result")
    results = []
    for row in rows:
        # Link
        link_elem = await row.query_selector("h3 > a")
        title = (link_elem.text or "").strip() if link_elem else ""
        href = ""
        if link_elem and link_elem.attrs:
            href = link_elem.attrs.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://sam.gov{href}"

        # Notice ID
        id_elem = await row.query_selector("div.margin-y-1 > h3")
        notice_id = (id_elem.text or "").strip().removeprefix("Notice ID: ") if id_elem else ""

        # Updated date – normalize to ISO 8601 so DB comparisons work
        date_elem = await row.query_selector(".grid-col-auto > div:nth-of-type(3) .sds-field__value")
        raw_date = (date_elem.text or "").strip() if date_elem else ""
        updated_date = normalize_date(raw_date)

        results.append({
            "title": title,
            "href": href,
            "notice_id": notice_id,
            "updated_date": updated_date,
        })
    return results


async def get_pagination_info(page):
    """
    Return (current_page, total_pages) by parsing the aria-label on
    #bottomPagination-currentPage.

    The label follows the pattern "Page X of Y", e.g. "Page 1 of 3".
    """
    current_page = None
    total_pages = None

    try:
        cur_elem = await page.query_selector("#bottomPagination-currentPage")
        if cur_elem:
            label = cur_elem.attrs.get("aria-label", "")
            match = re.search(r"Page\s+(\d+)\s+of\s+(\d+)", label, re.IGNORECASE)
            if match:
                current_page = int(match.group(1))
                total_pages = int(match.group(2))
    except Exception as exc:
        logger.debug(f"  Could not read pagination info: {exc}")

    return current_page, total_pages


async def click_next_page(page):
    """Click the 'Next page' button and wait for new results to start loading."""
    try:
        next_btn = await page.query_selector("#bottomPagination-nextPage")
        if next_btn:
            await next_btn.click()
            await page.sleep(INITIAL_LOAD_WAIT)
            # Let the page "breathe" so the DOM can update
            await page
            return True
    except Exception as exc:
        logger.error(f"  Error clicking next page: {exc}")
    return False


async def scrape_index(headless=False, browser_args=None):
    """
    Scrape all index pages and return the list of row dicts.

    Each row has: title, href, notice_id, updated_date.
    """
    all_rows = []

    logger.info("Launching browser …")
    browser = await uc.start(headless=headless, browser_args=browser_args or [])

    logger.info(f"Navigating to SAM.gov search …")
    page = await browser.get(START_URL)

    # Give the SPA a moment to bootstrap
    await page.sleep(INITIAL_LOAD_WAIT)
    await page

    page_num = 0
    while True:
        page_num += 1
        logger.info(f"--- Scraping page {page_num} ---")

        # 1. Wait for rows to stabilise
        row_count = await wait_for_rows_stable(page)

        if row_count == 0:
            logger.warning("  No rows found on this page. Stopping.")
            break

        # 2. Extract row data
        rows = await extract_rows(page)
        logger.info(f"  Extracted {len(rows)} rows")
        all_rows.extend(rows)

        # 3. Read pagination info
        current_page, total_pages = await get_pagination_info(page)
        logger.info(f"  Pagination: page {current_page} of {total_pages}")

        # 4. Decide whether to continue
        if current_page is not None and total_pages is not None:
            if current_page >= total_pages:
                logger.info("  Reached the last page.")
                break
        else:
            # Fallback: if we can't read pagination, try clicking next anyway
            logger.warning("  Could not determine pagination — attempting next page.")

        # 5. Click next
        if not await click_next_page(page):
            logger.info("  No next-page button found. Done.")
            break

    logger.info(f"Done! Scraped {len(all_rows)} rows")
    browser.stop()
    return all_rows


async def main():
    """Standalone entry point — scrapes and saves to JSON."""
    rows = await scrape_index()

    output_file = "sam_gov_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "scraped_at": datetime.now().isoformat(),
                "total_rows": len(rows),
                "results": rows,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    logger.info(f"Saved {len(rows)} rows to {output_file}")


if __name__ == "__main__":
    uc.loop().run_until_complete(main())