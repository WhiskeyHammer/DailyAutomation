"""
U Pull and Pay Junkyard Inventory Scraper
Uses NoDriver to scrape Dodge Dakota inventory from 1987-1996
"""

import asyncio
import logging
import nodriver as uc
from typing import List, Dict, Any
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def scrape_upullandpay_inventory(
    make: str = "DODGE",
    model: str = "DAKOTA",
    min_year: int = 1987,
    max_year: int = 1996,
    location_id: int = 34,
    headless: bool = False,
    browser_args: list = None,
) -> List[Dict[str, Any]]:
    """
    Scrape U Pull and Pay inventory for DODGE DAKOTA at Orlando.
    Uses hardcoded URL with numeric IDs.

    Args:
        make: Vehicle make (default: DODGE)
        model: Vehicle model (default: DAKOTA)
        min_year: Minimum year inclusive (default: 1987)
        max_year: Maximum year inclusive (default: 1996)
        location_id: Numeric location ID (default: 34 for Orlando)
        headless: Run browser in headless mode (default: False)
        browser_args: Additional browser arguments

    Returns:
        List of dictionaries with vehicle data
    """

    url = "https://www.upullandpay.com/inventory/search/?Locations=34&MakeID=21&Models=202&Years=-1&LocationPage=false&LocationID=0"

    logger.info(f"[UPullAndPay] Starting browser...")
    browser = await uc.start(headless=headless, browser_args=browser_args or [], no_sandbox=True)
    logger.info(f"[UPullAndPay] Browser started OK")

    try:
        logger.info(f"[UPullAndPay] Navigating to {url}")
        page = await browser.get(url)

        # Maximize window if not headless
        if not headless:
            await page.evaluate("window.moveTo(0, 0); window.resizeTo(screen.width, screen.height);")

        # Wait for results to load
        logger.info(f"[UPullAndPay] Waiting for results to load...")
        page_source = None
        for attempt in range(20):
            page_source = await page.get_content()
            if page_source and 'search-results-exact' in page_source.lower():
                logger.info(f"[UPullAndPay] Found results container on attempt {attempt+1}")
                break
            await page.sleep(1)

        if not page_source:
            logger.warning("[UPullAndPay] Could not get page source")
            return []

        soup = BeautifulSoup(page_source, 'html.parser')

        # Find the results container for location 34 (Orlando)
        results_container = soup.find('div', {'data-sortable-table': 'inventorySearchExact34'})

        if not results_container:
            logger.warning("[UPullAndPay] No results container found")
            return []

        # Get all vehicle divs
        vehicle_divs = results_container.find_all('div', class_='col-md-6')
        logger.info(f"[UPullAndPay] Found {len(vehicle_divs)} vehicle divs")

        if not vehicle_divs:
            return []

        vehicles = []

        for vehicle_div in vehicle_divs:
            try:
                year_str = vehicle_div.get('data-year', '')
                make_val = vehicle_div.get('data-make', '')
                model_val = vehicle_div.get('data-model', '')

                try:
                    year = int(year_str)
                except (ValueError, TypeError):
                    continue

                # Filter by year range and make/model
                if not (min_year <= year <= max_year and
                        make_val.upper() == make.upper() and
                        model_val.upper() == model.upper()):
                    continue

                # Extract details from search-result div
                result_div = vehicle_div.find('div', class_='search-result')
                if not result_div:
                    continue

                # Extract row location (e.g., "Row 8")
                row_location = None
                row_span = result_div.find_all('span')
                for span in row_span:
                    text = span.get_text(strip=True)
                    if text.startswith('Row '):
                        row_location = text
                        break

                # Extract date on yard
                date_in_yard = None
                date_span = result_div.find('span', class_='date')
                if date_span:
                    date_text = date_span.get_text(strip=True)
                    if 'Date on Yard:' in date_text:
                        date_in_yard = date_text.replace('Date on Yard:', '').strip()

                # Extract VIN - look in the link or in the text
                vin = None
                recall_link = result_div.find('a', href=lambda x: x and 'vin=' in x.lower())
                if recall_link:
                    href = recall_link.get('href', '')
                    if 'vin=' in href.lower():
                        vin = href.split('vin=')[-1]

                # If no VIN from link, try to find it in the text
                if not vin:
                    for li in result_div.find_all('li'):
                        text = li.get_text(strip=True)
                        if 'VIN:' in text:
                            vin = text.replace('VIN:', '').strip()
                            break

                vehicle = {
                    "year": year,
                    "make": make_val,
                    "model": model_val,
                    "engine": None,
                    "transmission": None,
                    "stock_number": None,
                    "row_location": row_location,
                    "date_in_yard": date_in_yard,
                    "vin": vin,
                    "scraped_at": datetime.now().isoformat()
                }

                vehicles.append(vehicle)

            except Exception as e:
                logger.error(f"[UPullAndPay] Error processing vehicle: {e}")
                continue

        logger.info(f"[UPullAndPay] Returning {len(vehicles)} matching vehicles")
        return vehicles

    finally:
        logger.info(f"[UPullAndPay] Stopping browser...")
        browser.stop()


async def main():
    """Main entry point for the scraper."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("Scraping U Pull and Pay for Dodge Dakota 1987-1996...")

    vehicles = await scrape_upullandpay_inventory(
        make="DODGE",
        model="DAKOTA",
        min_year=1987,
        max_year=1996,
        location_id=34
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
