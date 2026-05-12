"""
Used Auto Parts FL Junkyard Inventory Scraper
Uses NoDriver to scrape Dodge Dakota inventory from 1987-1996
Interacts directly with the real site
"""

import asyncio
import logging
import nodriver as uc
from typing import List, Dict, Any
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def scrape_usedautopartsfl_inventory(
    make: str = "DODGE",
    model: str = "DAKOTA",
    min_year: int = 1987,
    max_year: int = 1996,
    headless: bool = False,
    browser_args: list = None,
) -> List[Dict[str, Any]]:
    """
    Scrape Used Auto Parts FL inventory for specified make/model/year range.
    Interacts with the real inventory system on the website.

    Args:
        make: Vehicle make (default: DODGE)
        model: Vehicle model (default: DAKOTA)
        min_year: Minimum year inclusive (default: 1987)
        max_year: Maximum year inclusive (default: 1996)
        headless: Run browser in headless mode (default: True)
        browser_args: Additional browser arguments

    Returns:
        List of dictionaries with vehicle data
    """

    url = "https://www.usedautopartsfl.com/parts"

    logger.info(f"[UsedAutoPartsFL] Starting browser...")
    browser = await uc.start(headless=headless, browser_args=browser_args or [], no_sandbox=True)
    logger.info(f"[UsedAutoPartsFL] Browser started OK")

    try:
        logger.info(f"[UsedAutoPartsFL] Navigating to {url}")
        page = await browser.get(url)

        # Maximize window if not headless
        if not headless:
            await page.evaluate("window.moveTo(0, 0); window.resizeTo(screen.width, screen.height);")

        await page.sleep(5)

        # Try to find and interact with Make input
        logger.info(f"[UsedAutoPartsFL] Looking for make input...")
        try:
            make_input = await page.find("input[placeholder*='Make'], input[name*='make'], select[name*='make']", timeout=10)
            if make_input:
                await make_input.click()
                await page.sleep(0.5)
                await make_input.send_keys(make)
                await page.sleep(1)
                logger.info(f"[UsedAutoPartsFL] Entered make: {make}")
        except Exception as e:
            logger.warning(f"[UsedAutoPartsFL] Could not interact with make input: {e}")

        # Try to find and interact with Model input
        logger.info(f"[UsedAutoPartsFL] Looking for model input...")
        try:
            model_input = await page.find("input[placeholder*='Model'], input[name*='model'], select[name*='model']", timeout=10)
            if model_input:
                await model_input.click()
                await page.sleep(0.5)
                await model_input.send_keys(model)
                await page.sleep(1)
                logger.info(f"[UsedAutoPartsFL] Entered model: {model}")
        except Exception as e:
            logger.warning(f"[UsedAutoPartsFL] Could not interact with model input: {e}")

        # Try to find and click search button
        logger.info(f"[UsedAutoPartsFL] Looking for search button...")
        try:
            search_btn = await page.find("button[type='submit'], button:contains('Search'), button:contains('Find')", timeout=10)
            if search_btn:
                await search_btn.click()
                await page.sleep(3)
                logger.info(f"[UsedAutoPartsFL] Clicked search button")
        except Exception as e:
            logger.warning(f"[UsedAutoPartsFL] Could not find search button: {e}")

        # Wait for results
        logger.info(f"[UsedAutoPartsFL] Waiting for results...")
        page_source = None
        for attempt in range(15):
            page_source = await page.get_content()
            if page_source and '<table' in page_source.lower():
                logger.info(f"[UsedAutoPartsFL] Found results table on attempt {attempt+1}")
                break
            await page.sleep(1)

        if not page_source:
            logger.warning("[UsedAutoPartsFL] Could not get page source")
            return []

        soup = BeautifulSoup(page_source, 'html.parser')

        # Look for tables or result rows
        table = soup.find('table')
        if not table:
            logger.warning("[UsedAutoPartsFL] No table found, looking for result divs...")
            result_divs = soup.find_all('div', class_=['result', 'vehicle', 'item', 'row'])
            if not result_divs:
                logger.warning("[UsedAutoPartsFL] No result elements found")
                return []

        vehicles = []

        if table:
            rows = table.find_all('tr')[1:] if table.find_all('tr') else []
            logger.info(f"[UsedAutoPartsFL] Found {len(rows)} table rows")

            for row in rows:
                try:
                    cells = row.find_all('td')
                    if len(cells) < 3:
                        continue

                    year_str = cells[0].get_text(strip=True)
                    make_val = cells[1].get_text(strip=True)
                    model_val = cells[2].get_text(strip=True)
                    stock_val = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                    row_val = cells[4].get_text(strip=True) if len(cells) > 4 else ""

                    try:
                        year = int(year_str)
                    except ValueError:
                        continue

                    if (make_val.upper() == make.upper() and
                        model_val.upper() == model.upper() and
                        min_year <= year <= max_year):

                        vehicle = {
                            "year": year,
                            "make": make_val,
                            "model": model_val,
                            "engine": None,
                            "transmission": None,
                            "stock_number": stock_val,
                            "row_location": row_val,
                            "date_in_yard": None,
                            "vin": None,
                            "scraped_at": datetime.now().isoformat()
                        }

                        vehicles.append(vehicle)

                except Exception as e:
                    logger.error(f"[UsedAutoPartsFL] Error processing row: {e}")
                    continue

        logger.info(f"[UsedAutoPartsFL] Returning {len(vehicles)} matching vehicles")
        return vehicles

    except Exception as e:
        logger.error(f"[UsedAutoPartsFL] Error scraping: {e}")
        return []
    finally:
        logger.info(f"[UsedAutoPartsFL] Stopping browser...")
        browser.stop()


async def main():
    """Main entry point for the scraper."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("Scraping Used Auto Parts FL for Dodge Dakota 1987-1996...")

    vehicles = await scrape_usedautopartsfl_inventory(
        make="DODGE",
        model="DAKOTA",
        min_year=1987,
        max_year=1996
    )

    if not vehicles:
        print("No vehicles found matching criteria.")
        return []

    print(f"\nFound {len(vehicles)} vehicles:\n")

    for i, vehicle in enumerate(vehicles, 1):
        print(f"--- Vehicle {i} ---")
        for key, value in vehicle.items():
            print(f"  {key}: {value}")
        print()

    return vehicles


if __name__ == "__main__":
    asyncio.run(main())
