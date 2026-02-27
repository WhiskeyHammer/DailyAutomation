"""
GO Pull-It Junkyard Inventory Scraper
Uses NoDriver to scrape Dodge Dakota inventory from 1987-1996
Includes VIN decoding via NHTSA API
"""

import asyncio
import requests
import nodriver as uc
from typing import List, Dict, Any
from datetime import datetime
from bs4 import BeautifulSoup


def decode_vins(vin_list: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Decode VINs using NHTSA vPIC API.
    
    Args:
        vin_list: List of VIN strings to decode
    
    Returns:
        Dictionary mapping VIN to decoded data
    """
    if not vin_list:
        return {}
    
    base_url = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/"
    
    # The API prefers batches of 50 or fewer
    # Format: VIN;VIN;VIN (semicolon separated)
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
                # Get displacement and cylinders
                displacement = entry.get("DisplacementL", "")
                cylinders = entry.get("EngineCylinders", "")
                
                # Build engine string
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
        print(f"VIN decode error: {e}")
        return {}


async def scrape_gopullit_inventory(
    location: str = "jacksonville-fl",
    make: str = "DODGE",
    model: str = "DAKOTA",
    min_year: int = 1987,
    max_year: int = 1996
) -> List[Dict[str, Any]]:
    """
    Scrape GO Pull-It inventory for specified location/make/model/year range.
    
    Args:
        location: Yard location (default: jacksonville-fl)
        make: Vehicle make (default: DODGE)
        model: Vehicle model (default: DAKOTA)
        min_year: Minimum year inclusive (default: 1987)
        max_year: Maximum year inclusive (default: 1996)
    
    Returns:
        List of dictionaries with vehicle data (key-value pairs)
    """
    
    # Start browser
    browser = await uc.start()
    
    try:
        # Navigate to inventory page
        inventory_url = f"https://gopullit.com/inventory/?location={location}&make={make}&model={model}"
        page = await browser.get(inventory_url)
        await page.sleep(3)
        
        # Try to click on "SELECT LOCATION" to open dropdown
        try:
            select_location = await page.find("SELECT LOCATION", timeout=5)
            if select_location:
                await select_location.click()
                await page.sleep(1)
                
                # Click on Jacksonville, FL
                jax_link = await page.find("Jacksonville, FL", timeout=5)
                if jax_link:
                    await jax_link.click()
                    await page.sleep(3)
        except:
            pass
        
        # Navigate again to ensure we're on the right page with location set
        page = await browser.get(inventory_url)
        await page.sleep(5)
        
        # Wait for table to load
        for _ in range(10):
            page_source = await page.get_content()
            if page_source and '<tbody' in page_source.lower():
                break
            await page.sleep(1)
        
        if not page_source:
            print("Could not get page source")
            return []
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Find the inventory table
        table = soup.find('table')
        
        if not table:
            print("No inventory table found in page source")
            return []
        
        # Get all rows from tbody (data rows)
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
        else:
            # Fallback: get all rows and skip header
            rows = table.find_all('tr')[1:]
        
        if not rows:
            print("No data rows found in table")
            return []
        
        vehicles = []
        
        for row in rows:
            try:
                cells = row.find_all('td')
                
                if len(cells) < 7:
                    continue
                
                # Extract text from each cell
                # Columns: MAKE(0), MODEL(1), YEAR(2), ROW(3), VIN(4), STOCK NUMBER(5), 
                #          DATE PLACED IN YARD(6), LOCATION(7), IMAGES(8), MORE INFO(9)
                
                make_val = cells[0].get_text(strip=True)
                model_val = cells[1].get_text(strip=True)
                year_str = cells[2].get_text(strip=True)
                row_val = cells[3].get_text(strip=True)
                vin_val = cells[4].get_text(strip=True)
                stock_val = cells[5].get_text(strip=True)
                date_val = cells[6].get_text(strip=True)
                
                # Parse year as integer
                try:
                    year = int(year_str)
                except ValueError:
                    continue
                
                # Filter by make, model, and year range
                if (make_val.upper() == make.upper() and 
                    model_val.upper() == model.upper() and 
                    min_year <= year <= max_year):
                    
                    # Parse date if possible (format: MM/DD/YY)
                    date_in_yard = None
                    if date_val and date_val.strip():
                        try:
                            date_in_yard = datetime.strptime(date_val, "%m/%d/%y").date().isoformat()
                        except ValueError:
                            date_in_yard = date_val  # Keep original if can't parse
                    
                    vehicle = {
                        "year": year,
                        "make": make_val,
                        "model": model_val,
                        "engine": None,  # Not available on GO Pull-It
                        "transmission": None,  # Not available on GO Pull-It
                        "stock_number": stock_val,
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
        
    finally:
        # Close browser
        browser.stop()


async def main():
    """Main entry point for the scraper."""
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
    
    # Get list of VINs to decode
    vins = [v["vin"] for v in vehicles if v.get("vin")]
    
    # Decode VINs using NHTSA API
    vin_data = decode_vins(vins)
    
    # Enrich vehicle data with VIN decoded info
    for vehicle in vehicles:
        vin = vehicle.get("vin")
        if vin and vin in vin_data:
            decoded = vin_data[vin]
            vehicle["engine"] = decoded.get("engine")
            vehicle["transmission"] = decoded.get("transmission_style")
            vehicle["drive_type"] = decoded.get("drive_type")
    
    print(f"\nEnriched {len(vehicles)} vehicles with VIN data:\n")
    
    # Print each vehicle as key-value pairs
    for i, vehicle in enumerate(vehicles, 1):
        print(f"--- Vehicle {i} ---")
        for key, value in vehicle.items():
            print(f"  {key}: {value}")
        print()
    
    return vehicles


if __name__ == "__main__":
    asyncio.run(main())
