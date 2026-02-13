"""
Combined service runner:
  1. Workout tracker keep-alive  — every 1-3 minutes
  2. SAM.gov contract scraper    — every hour
"""

import asyncio
import logging
import random
import time

import nodriver as uc

from sam_contracts.sam_link_scraper import scrape_index
from sam_contracts.sam_detail_scraper import scrape_details
from sam_contracts.sam_db import (
    connect,
    init_schema,
    upsert_notice,
    upsert_notice_detail,
    get_stale_notices,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]

# ---------------------------------------------------------------------------
# 1.  Workout Tracker keep-alive
# ---------------------------------------------------------------------------
WORKOUT_URL = "https://workout-tracker-hxg5.onrender.com/"


async def check_workout_site():
    browser = None
    try:
        browser = await uc.start(headless=True, browser_args=BROWSER_ARGS)
        tab = await browser.get(WORKOUT_URL)
        logger.info(f"Checking {WORKOUT_URL} …")
        pw = await tab.select('input[type="password"]', timeout=15)
        if pw:
            logger.info("Workout tracker: login screen visible ✓")
        else:
            logger.warning("Workout tracker: password field NOT found")
    except Exception as e:
        logger.error(f"Workout tracker error: {e}")
    finally:
        if browser:
            browser.stop()


# ---------------------------------------------------------------------------
# 2.  SAM.gov Pipeline
# ---------------------------------------------------------------------------

async def run_sam_pipeline():
    logger.info("=" * 60)
    logger.info("SAM.gov pipeline starting")
    logger.info("=" * 60)

    db = connect()
    init_schema(db)

    try:
        # Step 1: Scrape index pages
        all_rows = await scrape_index(headless=True, browser_args=BROWSER_ARGS)

        # Step 2: Upsert index rows to DB (does NOT set scraped_at)
        for row in all_rows:
            upsert_notice(db, row)
        logger.info(f"Upserted {len(all_rows)} notices")

        # Step 3: Find notices that need detail scraping
        stale = get_stale_notices(db)
        logger.info(f"Stale (new/updated) notices: {len(stale)}")

        # Step 4: Scrape details for stale notices + upsert
        if stale:
            urls = [row["href"] for row in stale]
            details = await scrape_details(urls, headless=True, browser_args=BROWSER_ARGS)
            for detail in details:
                if "error" not in detail:
                    upsert_notice_detail(db, detail)
            logger.info(f"Detail-scraped {len(details)} notices")

        logger.info("SAM.gov pipeline complete ✓")

    except Exception as exc:
        logger.error(f"SAM pipeline error: {exc}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3.  Main loop
# ---------------------------------------------------------------------------
SAM_INTERVAL = 3600  # 1 hour


async def run_loop():
    logger.info("Starting combined service …")
    last_sam_run = 0  # triggers immediately on first loop

    while True:
        now = time.time()

        # SAM scraper (hourly)
        if now - last_sam_run >= SAM_INTERVAL:
            try:
                await run_sam_pipeline()
            except Exception as exc:
                logger.error(f"SAM pipeline top-level error: {exc}")
            last_sam_run = time.time()

        # Workout keep-alive (every 1-3 min)
        try:
            await check_workout_site()
        except Exception as exc:
            logger.error(f"Workout check error: {exc}")

        sleep_secs = random.randint(60, 180)
        logger.info(f"Sleeping {sleep_secs}s …")
        await asyncio.sleep(sleep_secs)


if __name__ == "__main__":
    uc.loop().run_until_complete(run_loop())