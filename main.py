"""
Combined service runner:
  1. Workout tracker keep-alive  — every 1-3 minutes
  2. Junkyard scraper            — every hour
  3. SAM.gov contract scraper    — every hour (with email summary)
"""

import asyncio
import logging
import os
import random
import sys
import time

import nodriver as uc
from dotenv import load_dotenv

from browser_config import BROWSER_ARGS, HEADLESS
from sam_contracts.master_sam import run_sam_pipeline
from junkyard_scraper.master_junkyard import main as run_junkyard_pipeline

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timeouts (seconds) — prevents hung browsers from blocking the loop forever
# ---------------------------------------------------------------------------
SAM_TIMEOUT = 900       # 15 minutes
JUNKYARD_TIMEOUT = 600  # 10 minutes
WORKOUT_TIMEOUT = 120   # 2 minutes


# ---------------------------------------------------------------------------
# 1.  Workout Tracker keep-alive
# ---------------------------------------------------------------------------
WORKOUT_URL = "https://workout-tracker-hxg5.onrender.com/"


async def check_workout_site():
    browser = None
    try:
        browser = await uc.start(headless=HEADLESS, browser_args=BROWSER_ARGS)
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
# 2.  Main loop
# ---------------------------------------------------------------------------
SAM_INTERVAL = 3600  # 1 hour
JUNKYARD_INTERVAL = 3600  # 1 hour


async def run_loop():
    logger.info("=== SERVICE STARTING ===")
    logger.info(f"SAM timeout: {SAM_TIMEOUT}s | Junkyard timeout: {JUNKYARD_TIMEOUT}s | Workout timeout: {WORKOUT_TIMEOUT}s")
    sys.stdout.flush()

    last_sam_run = 0
    last_junkyard_run = 0
    loop_count = 0

    while True:
        loop_count += 1
        now = time.time()
        logger.info(f"--- Loop iteration {loop_count} | {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        sys.stdout.flush()

        # Junkyard scraper (hourly) — runs first
        if now - last_junkyard_run >= JUNKYARD_INTERVAL:
            try:
                logger.info("=" * 60)
                logger.info("Junkyard pipeline starting")
                logger.info("=" * 60)
                await asyncio.wait_for(run_junkyard_pipeline(), timeout=JUNKYARD_TIMEOUT)
                logger.info("Junkyard pipeline complete ✓")
            except asyncio.TimeoutError:
                logger.error(f"Junkyard pipeline TIMED OUT after {JUNKYARD_TIMEOUT}s — moving on")
            except Exception as exc:
                logger.error(f"Junkyard pipeline top-level error: {exc}")
            last_junkyard_run = time.time()

        # SAM scraper (hourly)
        if now - last_sam_run >= SAM_INTERVAL:
            try:
                await asyncio.wait_for(run_sam_pipeline(), timeout=SAM_TIMEOUT)
            except asyncio.TimeoutError:
                logger.error(f"SAM pipeline TIMED OUT after {SAM_TIMEOUT}s — moving on")
            except Exception as exc:
                logger.error(f"SAM pipeline top-level error: {exc}")
            last_sam_run = time.time()

        # Workout keep-alive (every 1-3 min)
        try:
            await asyncio.wait_for(check_workout_site(), timeout=WORKOUT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.error(f"Workout check TIMED OUT after {WORKOUT_TIMEOUT}s — moving on")
        except Exception as exc:
            logger.error(f"Workout check error: {exc}")

        sleep_secs = random.randint(60, 180)
        logger.info(f"Sleeping {sleep_secs}s …")
        sys.stdout.flush()
        await asyncio.sleep(sleep_secs)


if __name__ == "__main__":
    uc.loop().run_until_complete(run_loop())