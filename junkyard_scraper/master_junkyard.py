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

from sam_contracts.sam_db import TursoClient
from junkyard_scraper.ace_scrape import scrape_ace_inventory
from junkyard_scraper.go_scraper import scrape_gopullit_inventory
from browser_config import BROWSER_ARGS, HEADLESS

MAX_SCRAPER_RETRIES = 3
RETRY_DELAY = 5  # seconds


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


def normalize_cars(cars):
    """Normalize inventory results for stable comparison."""
    normalized = []
    for c in cars:
        stock = str(c.get('stock_number', '') or '').strip()
        year = str(c.get('year', ''))
        make = str(c.get('make', '') or '').strip().upper()
        model = str(c.get('model', '') or '').strip().upper()
        vin = str(c.get('vin', '') or '').strip().upper()
        normalized.append((stock, year, make, model, vin))
    return tuple(sorted(normalized))


def choose_consensus_result(attempt_results):
    """Pick the most stable inventory from multiple scraper attempts."""
    from collections import Counter, defaultdict

    if not attempt_results:
        return []

    buckets = defaultdict(list)
    for entry in attempt_results:
        key = normalize_cars(entry['cars'])
        buckets[key].append(entry['cars'])

    if not buckets:
        return []

    most_common = Counter({key: len(values) for key, values in buckets.items()})
    consensus_key, consensus_count = most_common.most_common(1)[0]

    if consensus_count >= 2:
        logger.info(f"Consensus reached on attempt result after {consensus_count} matching runs")
        return buckets[consensus_key][0]

    non_empty_runs = [entry['cars'] for entry in attempt_results if entry['cars']]
    if non_empty_runs:
        selected = max(non_empty_runs, key=len)
        logger.info(
            "No stable consensus was reached; selecting the largest non-empty result "
            f"({len(selected)} cars) from {len(non_empty_runs)} successful runs"
        )
        return selected

    return []


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


async def scrape_with_retry(name, scrape_fn, **kwargs):
    """Run a scraper function with retries until a stable inventory result is reached."""
    attempt_results = []

    for attempt in range(1, MAX_SCRAPER_RETRIES + 1):
        try:
            result = await scrape_fn(**kwargs)
            attempt_results.append({'cars': result})

            if attempt > 1 and normalize_cars(result) == normalize_cars(attempt_results[-2]['cars']):
                logger.info(f"{name} stable result achieved on attempt {attempt}")
                return result

            if not result:
                logger.warning(f"{name} attempt {attempt}/{MAX_SCRAPER_RETRIES} returned no cars")
            else:
                logger.info(f"{name} attempt {attempt}/{MAX_SCRAPER_RETRIES} returned {len(result)} cars")

        except Exception as e:
            logger.error(f"{name} attempt {attempt}/{MAX_SCRAPER_RETRIES} failed: {e}")
            attempt_results.append({'cars': []})
            if attempt < MAX_SCRAPER_RETRIES:
                logger.info(f"{name} retrying in {RETRY_DELAY}s...")
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error(f"{name} FAILED after {MAX_SCRAPER_RETRIES} attempts\n{traceback.format_exc()}")
            continue

        if attempt < MAX_SCRAPER_RETRIES:
            logger.info(f"{name} retrying in {RETRY_DELAY}s...\n")
            await asyncio.sleep(RETRY_DELAY)

    consensus = choose_consensus_result(attempt_results)
    if consensus is not attempt_results[-1]['cars']:
        logger.info(f"{name} returning consensus result with {len(consensus)} cars")
    return consensus


async def main():
    client = TursoClient()
    init_junkyard_schema(client)
    
    # --- Ace scraper (with retry) ---
    ace_cars = await scrape_with_retry(
        "Ace scraper",
        scrape_ace_inventory,
        headless=HEADLESS,
        browser_args=BROWSER_ARGS,
    )
    logger.info(f"Ace scraper returned {len(ace_cars)} cars")
    
    for c in ace_cars:
        c['yard'] = 'Ace'
        
    # --- GO Pull-It scraper (with retry) ---
    go_cars = await scrape_with_retry(
        "GO Pull-It scraper",
        scrape_gopullit_inventory,
        headless=HEADLESS,
        browser_args=BROWSER_ARGS,
    )
    logger.info(f"GO Pull-It scraper returned {len(go_cars)} cars")
    
    for c in go_cars:
        c['yard'] = 'GO'
        
    all_cars = ace_cars + go_cars
    logger.info(f"Total cars scraped: {len(all_cars)} (Ace={len(ace_cars)}, GO={len(go_cars)})")
    
    new_cars = []
    existing_cars = []
    now_dt = datetime.now()
    now = now_dt.isoformat()
    
    for car in all_cars:
        yard = car['yard']
        stock = car['stock_number']
        try:
            rs = client.execute(
                "SELECT first_seen_at FROM junkyard_vehicles WHERE yard = :y AND stock_number = :s",
                {'y': yard, 's': stock}
            )
            
            if not rs['rows']:
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
                client.execute(
                    "UPDATE junkyard_vehicles SET last_seen_at = :now, row_location = :row_location WHERE yard = :y AND stock_number = :s",
                    {'now': now, 'row_location': car.get('row_location'), 'y': yard, 's': stock}
                )
                existing_cars.append(car)
        except Exception as e:
            logger.error(f"DB upsert FAILED for {yard}/{stock}: {e}\n{traceback.format_exc()}")
            
    logger.info(f"DB results: {len(new_cars)} new, {len(existing_cars)} existing")
    
    # --- Email decision ---
    # Always send on new cars immediately.
    # Otherwise, send a daily digest on the first successful run of each day.
    today_str = now_dt.strftime("%Y-%m-%d")
    
    rs = client.execute("SELECT value FROM app_state WHERE key = 'last_junkyard_email_date'")
    last_sent_date = rs['rows'][0][0] if rs['rows'] else ""
    is_first_run_today = last_sent_date != today_str

    should_send_email = bool(new_cars) or is_first_run_today

    if should_send_email:
        if new_cars:
            subject = f"Junkyard Scrape: {len(new_cars)} NEW, {len(existing_cars)} Existing"
        else:
            subject = f"Junkyard Daily Digest: {len(existing_cars)} In Stock (no new)"
        
        body = format_car_table("NEWLY SCRAPED CARS", new_cars) + format_car_table("ALL OTHER IN STOCK", existing_cars)
        send_email(subject, body)
        logger.info(f"Email sent: {subject}")
        
        client.execute(
            "INSERT INTO app_state (key, value) VALUES ('last_junkyard_email_date', :val) "
            "ON CONFLICT(key) DO UPDATE SET value = :val",
            {'val': today_str}
        )
    else:
        logger.info("Skipping email — already sent today and no new cars")
    
    logger.info("Junkyard main() complete")

if __name__ == "__main__":
    asyncio.run(main())