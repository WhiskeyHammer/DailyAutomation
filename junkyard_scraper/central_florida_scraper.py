"""
Central Florida Pick and Pay Junkyard Inventory Scraper
Uses NoDriver to scrape Dodge Dakota inventory from 1987-1996
"""

import asyncio
import nodriver as uc
from typing import List, Dict, Any
from datetime import datetime
from bs4 import BeautifulSoup


async def scrape_centralflorida_inventory(
    make: str = "DODGE",
    model: str = "DAKOTA",
    min_year: int = 1987,
    max_year: int = 1996,
    headless: bool = False,
    browser_args: list = None,
) -> List[Dict[str, Any]]:
    """
    Scrape Central Florida Pick and Pay inventory for specified make/model/year range.

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

    url = "https://centralfloridapickandpay.com/vehicle-inventory/"

    browser = await uc.start(headless=headless, browser_args=browser_args or [], no_sandbox=True)

    try:
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
            print("Could not get page source")
            return []

        soup = BeautifulSoup(page_source, 'html.parser')

        tables = soup.find_all('table')
        if not tables:
            print("No tables found")
            return []

        table = None
        for t in tables:
            rows = t.find_all('tr')
            if len(rows) >= 2:
                table = t
                break

        if not table:
            print("No inventory table with data found")
            return []

        rows = table.find_all('tr')

        vehicles = []

        for row in rows[1:]:
            try:
                cells = row.find_all('td')

                if len(cells) < 8:
                    continue

                year_str = cells[0].get_text(strip=True)
                make_val = cells[1].get_text(strip=True)
                model_val = cells[2].get_text(strip=True)
                engine_val = cells[4].get_text(strip=True)
                row_val = cells[5].get_text(strip=True)
                date_val = cells[6].get_text(strip=True)
                vin_val = cells[7].get_text(strip=True)

                try:
                    year = int(year_str)
                except ValueError:
                    continue

                if (make_val.upper() == make.upper() and
                    model_val.upper() == model.upper() and
                    min_year <= year <= max_year):

                    date_in_yard = None
                    if date_val and date_val.strip():
                        try:
                            date_in_yard = datetime.strptime(date_val, "%m/%d/%y").date().isoformat()
                        except ValueError:
                            date_in_yard = date_val

                    vehicle = {
                        "year": year,
                        "make": make_val,
                        "model": model_val,
                        "engine": engine_val if engine_val else None,
                        "transmission": None,
                        "stock_number": vin_val,
                        "row_location": row_val,
                        "date_in_yard": date_in_yard,
                        "vin": vin_val,
                        "scraped_at": datetime.now().isoformat()
                    }

                    vehicles.append(vehicle)

            except Exception as e:
                print(f"Error processing row: {e}")
                continue

        return vehicles

    except Exception as e:
        print(f"Error scraping Central Florida Pick and Pay: {e}")
        return []

    finally:
        browser.stop()


async def main():
    """Main entry point for the scraper."""
    print("Scraping Central Florida Pick and Pay for Dodge Dakota 1987-1996...")

    vehicles = await scrape_centralflorida_inventory(
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
