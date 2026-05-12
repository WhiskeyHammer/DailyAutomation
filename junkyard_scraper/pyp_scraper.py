"""
Pick Your Parts (PYP) Junkyard Inventory Scraper
Uses NoDriver to scrape Dodge Dakota inventory from 1987-1996
Supports Orlando and Daytona locations
"""

import asyncio
import nodriver as uc
from typing import List, Dict, Any
from datetime import datetime
from bs4 import BeautifulSoup


async def scrape_pyp_inventory(
    locations: List[str] = None,
    make: str = "DODGE",
    model: str = "DAKOTA",
    min_year: int = 1987,
    max_year: int = 1996,
    headless: bool = False,
    browser_args: list = None,
) -> List[Dict[str, Any]]:
    """
    Scrape Pick Your Parts inventory for specified locations/make/model/year range.

    Args:
        locations: List of location slugs (default: ["orlando-1134", "daytona-1225"])
        make: Vehicle make (default: DODGE)
        model: Vehicle model (default: DAKOTA)
        min_year: Minimum year inclusive (default: 1987)
        max_year: Maximum year inclusive (default: 1996)
        headless: Run browser in headless mode (default: True)
        browser_args: Additional browser arguments

    Returns:
        List of dictionaries with vehicle data
    """

    if locations is None:
        locations = ["orlando-1134", "daytona-1225"]

    browser = await uc.start(headless=headless, browser_args=browser_args or [], no_sandbox=True)

    all_vehicles = []

    try:
        for location in locations:
            try:
                url = f"https://www.pyp.com/parts/{location}/?make={make}&model={model}"

                page = await browser.get(url)

                # Maximize window if not headless
                if not headless:
                    await page.evaluate("window.moveTo(0, 0); window.resizeTo(screen.width, screen.height);")

                await page.sleep(3)

                try:
                    await page.find("table", timeout=10)
                except Exception:
                    pass

                page_source = await page.get_content()

                if not page_source:
                    print(f"[PYP] Could not get page source for {location}")
                    continue

                soup = BeautifulSoup(page_source, 'html.parser')

                table = soup.find('table')
                if not table:
                    print(f"[PYP] No inventory table found for {location}")
                    continue

                rows = table.find_all('tr')

                if len(rows) < 2:
                    print(f"[PYP] No data rows found in table for {location}")
                    continue

                for row in rows[1:]:
                    try:
                        cells = row.find_all('td')

                        if len(cells) < 5:
                            continue

                        year_str = cells[0].get_text(strip=True)
                        make_val = cells[1].get_text(strip=True)
                        model_val = cells[2].get_text(strip=True)
                        stock_val = cells[3].get_text(strip=True)
                        row_val = cells[4].get_text(strip=True)

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

                            all_vehicles.append(vehicle)

                    except Exception as e:
                        print(f"[PYP] Error processing row for {location}: {e}")
                        continue

                print(f"[PYP] Found {len([v for v in all_vehicles if v['scraped_at']])} vehicles for {location}")

            except Exception as e:
                print(f"[PYP] Error scraping location {location}: {e}")
                continue

        return all_vehicles

    finally:
        browser.stop()


async def main():
    """Main entry point for the scraper."""
    print("Scraping Pick Your Parts (Orlando & Daytona) for Dodge Dakota 1987-1996...")

    vehicles = await scrape_pyp_inventory(
        locations=["orlando-1134", "daytona-1225"],
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
