"""
SAM.gov Detail Page Scraper module.

Provides scrape_details(urls) which launches one browser session,
visits each URL, and returns a list of structured result dicts.
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


async def _scrape_page(page, url):
    """Scrape a single detail page. Assumes the browser is already running."""
    logger.info(f"Navigating to {url}")
    await page.get(url)

    title = await get_text(page, 'h1[aria-role="heading"]')
    notice_id = await get_text(page, 'h5[aria-describedby="notice-id"]')

    poc_names = await get_all_texts(page, ".contact-title-2")
    poc_emails = await get_all_texts(page, 'h6[aria-describedby="email"]')
    poc_phones = await get_all_texts(page, 'h6[aria-describedby="phone"]')

    address_lines = await get_all_texts(page, "div:has(h2)>div>h6")

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

    logger.info(f"  Title:     {title}")
    logger.info(f"  Notice ID: {notice_id}")
    logger.info(f"  Contacts:  {len(contacts)}")
    logger.info(f"  Address:   {address_lines}")

    return result


async def scrape_details(urls, headless=False, browser_args=None):
    """
    Scrape a list of SAM.gov detail page URLs.

    Launches one browser session, visits each URL in sequence,
    and returns a list of result dicts.
    """
    browser = await uc.start(headless=headless, browser_args=browser_args or [])
    page = await browser.get("about:blank")

    results = []
    for i, url in enumerate(urls, 1):
        logger.info(f"--- Detail {i}/{len(urls)} ---")
        try:
            result = await _scrape_page(page, url)
            results.append(result)
        except Exception as exc:
            logger.error(f"  Failed to scrape {url}: {exc}")
            results.append({"url": url, "error": str(exc)})

    browser.stop()
    return results