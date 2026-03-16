"""
GO Pull-It Junkyard Inventory Scraper
Uses NoDriver to scrape Dodge Dakota inventory from 1987-1996
Includes VIN decoding via NHTSA API
"""

import asyncio
import logging
import requests
import nodriver as uc
from typing import List, Dict, Any
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def decode_vins(vin_list: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Decode VINs using NHTSA vPIC API.
    """
    if not vin_list:
        return {}
    
    base_url = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/"
    vins_string = ";".join(vin_list)
    
    payload = {
        'format': 'json',
        'data': vins_string
    }
    
    try:
        response = requests.post(base_url, data=payload)
        response.raise_for_status()
        results = response.json().get('Results', [])
        
        decoded = {}
        for entry in results:
            vin = entry.get("VIN")
            if vin:
                displacement = entry.get("DisplacementL", "")
                cylinders = entry.get("EngineCylinders", "")
                
                if displacement and cylinders:
                    engine = f"{displacement}L {cylinders}cyl"
                elif displacement:
                    engine = f"{displacement}L"
                elif cylinders:
                    engine = f"{cylinders}cyl"
                else:
                    engine = None
                
                decoded[vin] = {
                    "engine": engine,
                    "engine_model": entry.get("EngineModel"),
                    "transmission_speeds": entry.get("TransmissionSpeeds"),
                    "transmission_style": entry.get("TransmissionStyle"),
                    "drive_type": entry.get("DriveType"),
                    "body_class": entry.get("BodyClass"),
                    "fuel_type": entry.get("FuelTypePrimary"),
                }
        
        return decoded
        
    except Exception as e:
        logger.error(f"VIN decode error: {e}")
        return {}


async def scrape_gopullit_inventory(
    location: str = "jacksonville-fl",
    make: str = "DODGE",
    model: str = "DAKOTA",
    min_year: int = 1987,
    max_year: int = 1996,
    headless: bool = True,
    browser_args: list = None,
) -> List[Dict[str, Any]]:
    """
    Scrape GO Pull-It inventory for specified location/make/model/year range.
    """
    
    inventory_url = f"https://gopullit.com/inventory/?location={location}&make={make}&model={model}"
    
    logger.info(f"[GO] Starting browser...")
    browser = await uc.start(headless=headless, browser_args=browser_args or [])
    logger.info(f"[GO] Browser started OK")
    
    try:
        # Navigate to inventory page
        logger.info(f"[GO] Navigating to {inventory_url}")
        page = await browser.get(inventory_url)
        await page.sleep(3)
        
        # Try to click on "SELECT LOCATION" to open dropdown
        try:
            logger.info(f"[GO] Looking for 'SELECT LOCATION' button...")
            select_location = await page.find("SELECT LOCATION", timeout=5)
            if select_location:
                await select_location.click()
                await page.sleep(1)
                
                logger.info(f"[GO] Looking for 'Jacksonville, FL'...")
                jax_link = await page.find("Jacksonville, FL", timeout=5)
                if jax_link:
                    await jax_link.click()
                    await page.sleep(3)
        except Exception as e:
            logger.info(f"[GO] Location selection skipped: {e}")
        
        # Navigate again to ensure we're on the right page with location set
        logger.info(f"[GO] Second navigation to inventory page")
        page = await browser.get(inventory_url)
        await page.sleep(5)
        
        # Wait for table to load
        page_source = None
        for attempt in range(10):
            page_source = await page.get_content()
            if page_source and '<tbody' in page_source.lower():
                logger.info(f"[GO] Found tbody on attempt {attempt+1}")
                break
            await page.sleep(1)
        
        if not page_source:
            logger.warning("[GO] Could not get page source")
            return []
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser')
        table = soup.find('table')
        
        if not table:
            logger.warning("[GO] No inventory table found")
            return []
        
        # Get all rows from tbody (data rows)
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
        else:
            rows = table.find_all('tr')[1:]
        
        logger.info(f"[GO] Found {len(rows)} table rows")
        
        if not rows:
            return []
        
        vehicles = []
        
        for row in rows:
            try:
                cells = row.find_all('td')
                
                if len(cells) < 7:
                    continue
                
                make_val = cells[0].get_text(strip=True)
                model_val = cells[1].get_text(strip=True)
                year_str = cells[2].get_text(strip=True)
                row_val = cells[3].get_text(strip=True)
                vin_val = cells[4].get_text(strip=True)
                stock_val = cells[5].get_text(strip=True)
                date_val = cells[6].get_text(strip=True)
                
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
                        "engine": None,
                        "transmission": None,
                        "stock_number": stock_val,
                        "row_location": row_val,
                        "date_in_yard": date_in_yard,
                        "vin": vin_val,
                        "scraped_at": datetime.now().isoformat()
                    }
                    
                    vehicles.append(vehicle)
                    
            except Exception as e:
                logger.error(f"[GO] Error processing row: {e}")
                continue
        
        logger.info(f"[GO] Returning {len(vehicles)} matching vehicles")
        return vehicles
        
    finally:
        logger.info(f"[GO] Stopping browser...")
        browser.stop()


async def main():
    """Main entry point for the scraper."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    print("Scraping GO Pull-It Jacksonville for Dodge Dakota 1987-1996...")
    
    vehicles = await scrape_gopullit_inventory(
        location="jacksonville-fl",
        make="DODGE",
        model="DAKOTA",
        min_year=1987,
        max_year=1996
    )
    
    if not vehicles:
        print("No vehicles found matching criteria.")
        return []
    
    print(f"\nFound {len(vehicles)} vehicles. Decoding VINs...")
    
    vins = [v["vin"] for v in vehicles if v.get("vin")]
    vin_data = decode_vins(vins)
    
    for vehicle in vehicles:
        vin = vehicle.get("vin")
        if vin and vin in vin_data:
            decoded = vin_data[vin]
            vehicle["engine"] = decoded.get("engine")
            vehicle["transmission"] = decoded.get("transmission_style")
            vehicle["drive_type"] = decoded.get("drive_type")
    
    print(f"\nEnriched {len(vehicles)} vehicles with VIN data:\n")
    
    for i, vehicle in enumerate(vehicles, 1):
        print(f"--- Vehicle {i} ---")
        for key, value in vehicle.items():
            print(f"  {key}: {value}")
        print()
    
    return vehicles


if __name__ == "__main__":
    asyncio.run(main())