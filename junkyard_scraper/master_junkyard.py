import asyncio
import logging
import os
import smtplib
import sys
import traceback
from datetime import datetime
from email.mime.text import MIMEText

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

try:
    from sam_contracts.sam_db import TursoClient
    logger.info("[DIAG] Imported TursoClient OK")
except Exception as e:
    logger.error(f"[DIAG] Failed to import TursoClient: {e}")
    raise

try:
    from junkyard_scraper.ace_scrape import scrape_ace_inventory
    logger.info("[DIAG] Imported scrape_ace_inventory OK")
except Exception as e:
    logger.error(f"[DIAG] Failed to import ace_scrape: {e}")
    raise

try:
    from junkyard_scraper.go_scraper import scrape_gopullit_inventory
    logger.info("[DIAG] Imported scrape_gopullit_inventory OK")
except Exception as e:
    logger.error(f"[DIAG] Failed to import go_scraper: {e}")
    raise

try:
    from browser_config import BROWSER_ARGS, HEADLESS
    logger.info(f"[DIAG] Browser config loaded: HEADLESS={HEADLESS}, ARGS={BROWSER_ARGS}")
except Exception as e:
    logger.error(f"[DIAG] Failed to import browser_config: {e}")
    raise


def init_junkyard_schema(client):
    schema = [
        "CREATE TABLE IF NOT EXISTS junkyard_vehicles ("
        "yard TEXT, stock_number TEXT, year INTEGER, make TEXT, model TEXT, "
        "engine TEXT, transmission TEXT, drive_type TEXT, vin TEXT, "
        "row_location TEXT, date_in_yard TEXT, first_seen_at TEXT, last_seen_at TEXT, "
        "PRIMARY KEY (yard, stock_number))",
        "CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT)"
    ]
    client.batch([(sql, None) for sql in schema])

def send_email(subject, body):
    gmail_user = os.getenv("GMAIL_ADDRESS", "")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")
    if not gmail_user or not gmail_pass:
        return
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = gmail_user
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
    except Exception:
        pass

def format_car_table(title, cars):
    if not cars:
        return f"{title}\nNone\n\n"
    lines = [title, "-" * 95]
    header = f"{'YARD':<6} | {'YR':<4} | {'MAKE':<6} | {'MODEL':<8} | {'ENGINE':<15} | {'ROW':<6} | {'DATE IN':<10} | {'STOCK':<8}"
    lines.append(header)
    lines.append("-" * 95)
    for c in cars:
        yard = str(c.get('yard', ''))[:6]
        yr = str(c.get('year', ''))[:4]
        make = str(c.get('make', ''))[:6]
        model = str(c.get('model', ''))[:8]
        eng = str(c.get('engine') or '')[:15]
        row = str(c.get('row_location', ''))[:6]
        din = str(c.get('date_in_yard', ''))[:10]
        stk = str(c.get('stock_number', ''))[:8]
        lines.append(f"{yard:<6} | {yr:<4} | {make:<6} | {model:<8} | {eng:<15} | {row:<6} | {din:<10} | {stk:<8}")
    return "\n".join(lines) + "\n\n"

async def main():
    logger.info("[DIAG] main() entered")
    
    # --- DB init ---
    try:
        logger.info("[DIAG] Connecting to Turso...")
        client = TursoClient()
        logger.info("[DIAG] Turso connected, initializing schema...")
        init_junkyard_schema(client)
        logger.info("[DIAG] Schema initialized OK")
    except Exception as e:
        logger.error(f"[DIAG] DB init failed: {e}\n{traceback.format_exc()}")
        return
    
    # --- Ace scraper ---
    ace_cars = []
    try:
        logger.info("[DIAG] >>> Starting Ace scraper...")
        logger.info(f"[DIAG]     headless={HEADLESS}, browser_args={BROWSER_ARGS}")
        ace_cars = await scrape_ace_inventory(headless=HEADLESS, browser_args=BROWSER_ARGS)
        logger.info(f"[DIAG] <<< Ace scraper returned {len(ace_cars)} cars")
    except Exception as e:
        logger.error(f"[DIAG] Ace scraper FAILED: {e}\n{traceback.format_exc()}")
    
    for c in ace_cars:
        c['yard'] = 'Ace'
        
    # --- GO Pull-It scraper ---
    go_cars = []
    try:
        logger.info("[DIAG] >>> Starting GO Pull-It scraper...")
        logger.info(f"[DIAG]     headless={HEADLESS}, browser_args={BROWSER_ARGS}")
        go_cars = await scrape_gopullit_inventory(headless=HEADLESS, browser_args=BROWSER_ARGS)
        logger.info(f"[DIAG] <<< GO Pull-It scraper returned {len(go_cars)} cars")
    except Exception as e:
        logger.error(f"[DIAG] GO Pull-It scraper FAILED: {e}\n{traceback.format_exc()}")
        
    all_cars = ace_cars + go_cars
    logger.info(f"[DIAG] Total cars scraped: {len(all_cars)} (Ace={len(ace_cars)}, GO={len(go_cars)})")
    
    # --- Debug: log the keys of each car dict ---
    for i, car in enumerate(all_cars):
        logger.info(f"[DIAG] Car {i}: yard={car.get('yard', 'MISSING')}, stock={car.get('stock_number', 'MISSING')}, keys={list(car.keys())}")
    
    new_cars = []
    existing_cars = []
    now_dt = datetime.now()
    now = now_dt.isoformat()
    
    for car in all_cars:
        try:
            yard = car['yard']
            stock = car['stock_number']
            logger.info(f"[DIAG] Upserting: yard={yard}, stock={stock}")
            
            rs = client.execute("SELECT first_seen_at FROM junkyard_vehicles WHERE yard = :y AND stock_number = :s", {'y': yard, 's': stock})
            
            if not rs['rows']:
                logger.info(f"[DIAG]   -> INSERT (new car)")
                client.execute(
                    "INSERT INTO junkyard_vehicles (yard, stock_number, year, make, model, engine, transmission, drive_type, vin, row_location, date_in_yard, first_seen_at, last_seen_at) "
                    "VALUES (:yard, :stock_number, :year, :make, :model, :engine, :transmission, :drive_type, :vin, :row_location, :date_in_yard, :now, :now)",
                    {
                        'yard': yard, 'stock_number': stock, 'year': car.get('year'), 'make': car.get('make'),
                        'model': car.get('model'), 'engine': car.get('engine'), 'transmission': car.get('transmission'),
                        'drive_type': car.get('drive_type'), 'vin': car.get('vin'), 'row_location': car.get('row_location'),
                        'date_in_yard': car.get('date_in_yard'), 'now': now
                    }
                )
                new_cars.append(car)
            else:
                logger.info(f"[DIAG]   -> UPDATE (existing car)")
                client.execute(
                    "UPDATE junkyard_vehicles SET last_seen_at = :now, row_location = :row_location WHERE yard = :y AND stock_number = :s",
                    {'now': now, 'row_location': car.get('row_location'), 'y': yard, 's': stock}
                )
                existing_cars.append(car)
        except Exception as e:
            logger.error(f"[DIAG] DB upsert FAILED for car {car}: {e}\n{traceback.format_exc()}")
            
    logger.info(f"[DIAG] DB results: {len(new_cars)} new, {len(existing_cars)} existing")
    
    should_send_email = False
    today_str = now_dt.strftime("%Y-%m-%d")

    if new_cars:
        should_send_email = True
    elif now_dt.hour == 8 and 0 <= now_dt.minute <= 10:
        rs = client.execute("SELECT value FROM app_state WHERE key = 'last_junkyard_email_date'")
        last_sent_date = rs['rows'][0][0] if rs['rows'] else ""
        if last_sent_date != today_str:
            should_send_email = True

    if should_send_email:
        logger.info("[DIAG] Sending email notification...")
        subject = f"Junkyard Scrape: {len(new_cars)} New, {len(existing_cars)} Existing"
        body = format_car_table("NEWLY SCRAPED CARS", new_cars) + format_car_table("ALL OTHER IN STOCK", existing_cars)
        send_email(subject, body)
        
        client.execute(
            "INSERT INTO app_state (key, value) VALUES ('last_junkyard_email_date', :val) "
            "ON CONFLICT(key) DO UPDATE SET value = :val",
            {'val': today_str}
        )
    
    logger.info("[DIAG] main() complete")

if __name__ == "__main__":
    asyncio.run(main())