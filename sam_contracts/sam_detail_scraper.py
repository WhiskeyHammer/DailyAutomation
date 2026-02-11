"""
SAM.gov Detail Page Scraper module.

Provides scrape_detail(page, url) which navigates to a SAM.gov listing
and returns structured data (title, notice ID, contacts, address).
"""

import logging

import nodriver as uc

logger = logging.getLogger(__name__)


async def get_text(page, selector):
    """Return the trimmed text of the first element matching selector, or None."""
    try:
        elem = await page.select(selector, timeout=10)
        if elem:
            return (elem.text or "").strip()
    except Exception:
        return None


async def get_all_texts(page, selector):
    """Return a list of trimmed text from all elements matching selector."""
    try:
        elements = await page.select_all(selector, timeout=10)
        if elements:
            return [(e.text or "").strip() for e in elements]
    except Exception:
        pass
    return []


async def scrape_detail(url):
    """
    Navigate to a SAM.gov detail page and extract structured data.

    Launches its own browser session.
    Returns a dict with url, title, notice_id, contacts, and address.
    """
    browser = await uc.start()
    page = await browser.get(url)

    logger.info(f"Navigating to {url}")

    # Wait for the title to appear — that means the page is ready
    title = await get_text(page, 'h1[aria-role="heading"]')
    notice_id = await get_text(page, 'h5[aria-describedby="notice-id"]')

    poc_names = await get_all_texts(page, ".contact-title-2")
    poc_emails = await get_all_texts(page, 'h6[aria-describedby="email"]')
    poc_phones = await get_all_texts(page, 'h6[aria-describedby="phone"]')

    address_lines = await get_all_texts(page, "div:has(h2)>div>h6")

    # Build index-matched contacts list
    max_pocs = max(len(poc_names), len(poc_emails), len(poc_phones), 0)
    contacts = []
    for i in range(max_pocs):
        contacts.append({
            "name": poc_names[i] if i < len(poc_names) else None,
            "email": poc_emails[i] if i < len(poc_emails) else None,
            "phone": poc_phones[i] if i < len(poc_phones) else None,
        })

    result = {
        "url": url,
        "title": title,
        "notice_id": notice_id,
        "contacts": contacts,
        "address": address_lines,
    }

    logger.info(f"Title:     {title}")
    logger.info(f"Notice ID: {notice_id}")
    logger.info(f"Contacts:  {len(contacts)}")
    logger.info(f"Address:   {address_lines}")

    browser.stop()

    return result