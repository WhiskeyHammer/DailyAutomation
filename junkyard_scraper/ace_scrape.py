"""
Ace Pick-A-Part Junkyard Inventory Scraper
Uses NoDriver to scrape Dodge Dakota inventory from 1987-1996
"""

import asyncio
import nodriver as uc
from typing import List, Dict, Any
from datetime import datetime
from bs4 import BeautifulSoup


async def scrape_ace_inventory(
    make: str = "DODGE",
    model: str = "DAKOTA",
    min_year: int = 1987,
    max_year: int = 1996
) -> List[Dict[str, Any]]:
    """
    Scrape Ace Pick-A-Part inventory for specified make/model/year range.
    
    Args:
        make: Vehicle make (default: DODGE)
        model: Vehicle model (default: DAKOTA)
        min_year: Minimum year inclusive (default: 1987)
        max_year: Maximum year inclusive (default: 1996)
    
    Returns:
        List of dictionaries with vehicle data (key-value pairs)
    """
    
    url = f"https://acepickapart.com/search-inventory/?make={make}&model={model}"
    
    # Start browser
    browser = await uc.start()
    
    try:
        # Navigate to the page
        page = await browser.get(url)
        
        # Wait for the table to load
        await page.sleep(4)
        
        # Wait specifically for the table element
        try:
            await page.find("table", timeout=10)
        except Exception as e:
            print(f"Could not find table: {e}")
        
        # Get the page source
        page_source = await page.get_content()
        
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
        
        # Get all rows
        rows = table.find_all('tr')
        
        if len(rows) < 2:
            print("No data rows found in table")
            return []
        
        vehicles = []
        
        # Skip header row (index 0)
        for row in rows[1:]:
            try:
                cells = row.find_all('td')
                
                if len(cells) < 11:
                    continue
                
                # Extract text from each cell
                # Columns: Image(0), Year(1), Make(2), Model(3), Exterior(4), 
                #          Interior(5), Engine(6), Trans(7), Stock#(8), Row(9), DateInYard(10)
                
                year_str = cells[1].get_text(strip=True)
                make_val = cells[2].get_text(strip=True)
                model_val = cells[3].get_text(strip=True)
                engine_val = cells[6].get_text(strip=True)
                trans_val = cells[7].get_text(strip=True)
                stock_val = cells[8].get_text(strip=True)
                row_val = cells[9].get_text(strip=True)
                date_val = cells[10].get_text(strip=True)
                
                # Parse year as integer
                try:
                    year = int(year_str)
                except ValueError:
                    continue
                
                # Filter by make, model, and year range
                if (make_val.upper() == make.upper() and 
                    model_val.upper() == model.upper() and 
                    min_year <= year <= max_year):
                    
                    # Parse date if possible
                    date_in_yard = None
                    if date_val and date_val.strip():
                        try:
                            date_in_yard = datetime.strptime(date_val, "%m/%d/%Y").date().isoformat()
                        except ValueError:
                            date_in_yard = date_val  # Keep original if can't parse
                    
                    vehicle = {
                        "year": year,
                        "make": make_val,
                        "model": model_val,
                        "engine": engine_val,
                        "transmission": trans_val,
                        "stock_number": stock_val,
                        "row_location": row_val,
                        "date_in_yard": date_in_yard,
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
    print("Scraping Ace Pick-A-Part for Dodge Dakota 1987-1996...")
    
    vehicles = await scrape_ace_inventory(
        make="DODGE",
        model="DAKOTA",
        min_year=1987,
        max_year=1996
    )
    
    if not vehicles:
        print("No vehicles found matching criteria.")
        return []
    
    print(f"\nFound {len(vehicles)} vehicles:\n")
    
    # Print each vehicle as key-value pairs
    for i, vehicle in enumerate(vehicles, 1):
        print(f"--- Vehicle {i} ---")
        for key, value in vehicle.items():
            print(f"  {key}: {value}")
        print()
    
    return vehicles


if __name__ == "__main__":
    asyncio.run(main())
