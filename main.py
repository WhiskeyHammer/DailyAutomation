"""
Combined service runner:
  1. Workout tracker keep-alive  — every 1-3 minutes
  2. SAM.gov contract scraper    — every hour (with email summary)
"""

import asyncio
import logging
import os
import random
import smtplib
import time
from email.mime.text import MIMEText

import nodriver as uc
from dotenv import load_dotenv

from sam_contracts.sam_link_scraper import scrape_index
from sam_contracts.sam_detail_scraper import scrape_details
from sam_contracts.sam_db import (
    connect,
    init_schema,
    upsert_notice,
    upsert_notice_detail,
    get_stale_notices,
    get_contacts_for_notice,
)

load_dotenv()

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
# Email
# ---------------------------------------------------------------------------
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")


def send_email(subject, body, to_address=None):
    """Send an email via Gmail SMTP. Sends to self if no to_address given."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        logger.warning("Email not configured — skipping notification")
        return

    to_address = to_address or GMAIL_ADDRESS

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_address

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        logger.info(f"Email sent: {subject}")
    except Exception as exc:
        logger.error(f"Failed to send email: {exc}")


def build_pipeline_email(all_rows, stale, details, db):
    """Build subject + body for the pipeline summary email."""
    detail_count = len([d for d in details if "error" not in d]) if details else 0
    error_count = len([d for d in details if "error" in d]) if details else 0

    subject = f"SAM.gov Scraper: {len(all_rows)} listings, {len(stale)} new/updated"

    lines = [
        "SAM.gov Pipeline Summary",
        "=" * 40,
        f"Total index listings:    {len(all_rows)}",
        f"New/updated (stale):     {len(stale)}",
        f"Detail-scraped:          {detail_count}",
        f"Errors:                  {error_count}",
        "",
    ]

    if stale:
        lines.append("New/Updated Notices:")
        lines.append("-" * 40)
        for row in stale:
            lines.append(f"\n  {row.get('title', 'Untitled')}")
            lines.append(f"  ID: {row.get('notice_id', 'N/A')}")
            lines.append(f"  Updated: {row.get('updated_date', 'N/A')}")
            lines.append(f"  Link: {row.get('href', 'N/A')}")

            # Include contacts if we just detail-scraped this notice
            contacts = get_contacts_for_notice(db, row["notice_id"])
            if contacts:
                for c in contacts:
                    contact_parts = []
                    if c.get("name"):
                        contact_parts.append(c["name"])
                    if c.get("email"):
                        contact_parts.append(c["email"])
                    if c.get("phone"):
                        contact_parts.append(c["phone"])
                    lines.append(f"  POC: {' | '.join(contact_parts)}")

    body = "\n".join(lines)
    return subject, body


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

    all_rows = []
    stale = []
    details = []

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
            for i, detail in enumerate(details):
                if "error" not in detail:
                    # Use the known notice_id from DB if scraper didn't find one
                    detail["notice_id"] = stale[i]["notice_id"]
                    upsert_notice_detail(db, detail)
            logger.info(f"Detail-scraped {len(details)} notices")

        logger.info("SAM.gov pipeline complete ✓")

    except Exception as exc:
        logger.error(f"SAM pipeline error: {exc}")

    # Send email regardless of whether there were stale notices
    try:
        subject, body = build_pipeline_email(all_rows, stale, details, db)
        send_email(subject, body)

        if stale:
            send_email(subject, body, to_address="Harrison.jozefowicz@gmail.com")

    except Exception as exc:
        logger.error(f"Email notification error: {exc}")
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