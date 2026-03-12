"""
SAM.gov Master Pipeline

Runs the full SAM.gov scraping workflow:
  1. Scrape index pages for contract opportunities
  2. Upsert to Turso DB
  3. Identify new/updated (stale) notices
  4. Scrape detail pages for stale notices
  5. Send email summary

Can be run standalone:  python -m sam_contracts.master_sam
Or imported:            from sam_contracts.master_sam import run_sam_pipeline
"""

import asyncio
import logging
import os
import smtplib
import sys
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser_config import BROWSER_ARGS, HEADLESS
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

logger = logging.getLogger(__name__)

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
# Pipeline
# ---------------------------------------------------------------------------

async def run_sam_pipeline():
    """Full SAM.gov pipeline: scrape → upsert → detail-scrape → email."""
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
        all_rows = await scrape_index(headless=HEADLESS, browser_args=BROWSER_ARGS)

        # Step 2: Upsert index rows to DB
        for row in all_rows:
            upsert_notice(db, row)
        logger.info(f"Upserted {len(all_rows)} notices")

        # Step 3: Find notices that need detail scraping
        stale = get_stale_notices(db)
        logger.info(f"Stale (new/updated) notices: {len(stale)}")

        # Step 4: Scrape details for stale notices + upsert
        if stale:
            urls = [row["href"] for row in stale]
            details = await scrape_details(urls, headless=HEADLESS, browser_args=BROWSER_ARGS)
            for i, detail in enumerate(details):
                if "error" not in detail:
                    detail["notice_id"] = stale[i]["notice_id"]
                    upsert_notice_detail(db, detail)
            logger.info(f"Detail-scraped {len(details)} notices")

        logger.info("SAM.gov pipeline complete ✓")

    except Exception as exc:
        logger.error(f"SAM pipeline error: {exc}")

    # Send email regardless
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
# Standalone entry point
# ---------------------------------------------------------------------------

async def main():
    """Run the SAM pipeline once and exit."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    await run_sam_pipeline()


if __name__ == "__main__":
    asyncio.run(main())