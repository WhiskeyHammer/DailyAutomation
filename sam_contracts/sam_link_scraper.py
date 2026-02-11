"""
SAM.gov Contract Opportunities Scraper using nodriver.

Navigates to a SAM.gov search results page, waits for dynamic content to load
using a stabilization-check loop, extracts all h3 > a links, and paginates
through every page of results.

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

START_URL = (
    "https://sam.gov/search/?page=1&pageSize=25&sort=-modifiedDate&index=ac"
    "&sfm%5BsimpleSearch%5D%5BkeywordRadio%5D=ALL"
    "&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B0%5D%5Bkey%5D=drone"
    "&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B0%5D%5Bvalue%5D=drone"
    "&sfm%5BsimpleSearch%5D%5BkeywordEditorTextarea%5D="
    "&sfm%5Bstatus%5D%5Bis_active%5D=true"
    "&sfm%5Bstatus%5D%5Bis_inactive%5D=false"
)

# --- Configuration ---
STABLE_ITERATIONS = 5       # Number of consecutive stable checks before considering page loaded
STABLE_CHECK_DELAY = 0.5    # Seconds between each stability check
INITIAL_LOAD_WAIT = 3       # Seconds to wait after initial page load / next-page click
MAX_WAIT_CYCLES = 60        # Safety cap: max stability checks before giving up


async def wait_for_links_stable(page, selector="h3 > a"):
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
                    f"  Page stabilised with {current_count} links "
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


async def extract_links(page):
    """Return a list of dicts with 'text' and 'href' for every h3 > a on the page."""
    elements = await page.query_selector_all("h3 > a")
    links = []
    for elem in elements:
        text = elem.text or ""
        href = elem.attrs.get("href", "") if elem.attrs else ""
        # SAM.gov uses relative links — make them absolute
        if href and not href.startswith("http"):
            href = f"https://sam.gov{href}"
        links.append({"text": text.strip(), "href": href})
    return links


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


async def main():
    all_links = []

    logger.info("Launching browser …")
    browser = await uc.start()

    logger.info(f"Navigating to SAM.gov search …")
    page = await browser.get(START_URL)

    # Give the SPA a moment to bootstrap
    await page.sleep(INITIAL_LOAD_WAIT)
    await page

    page_num = 0
    while True:
        page_num += 1
        logger.info(f"--- Scraping page {page_num} ---")

        # 1. Wait for links to stabilise
        link_count = await wait_for_links_stable(page)

        if link_count == 0:
            logger.warning("  No links found on this page. Stopping.")
            break

        # 2. Extract the links
        links = await extract_links(page)
        logger.info(f"  Extracted {len(links)} links")
        all_links.extend(links)

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

    # --- Save results ---
    output_file = "sam_gov_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "scraped_at": datetime.now().isoformat(),
                "total_links": len(all_links),
                "results": all_links,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    logger.info(f"Done! Saved {len(all_links)} links to {output_file}")
    browser.stop()


if __name__ == "__main__":
    uc.loop().run_until_complete(main())