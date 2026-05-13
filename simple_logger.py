import asyncio
import nodriver as uc
import json
from datetime import datetime

async def main():
    print("\n" + "="*70)
    print("LOADING U PULL AND PAY - SEARCHING FOR DODGE DAKOTA")
    print("="*70)

    browser = await uc.start(headless=False)
    try:
        page = await browser.get("https://www.upullandpay.com/inventory/search/")

        # Maximize
        await page.evaluate("window.moveTo(0, 0); window.resizeTo(screen.width, screen.height);")

        print("\n[BROWSER LOADED] Now searching for DODGE DAKOTA manually...")
        print("[WAITING 10 MINUTES FOR YOUR SEARCH]\n")

        # Inject logger
        await page.evaluate("""
window.allClicks = [];
window.allChanges = [];
document.addEventListener('click', e => {
    window.allClicks.push({
        tag: e.target.tagName,
        id: e.target.id,
        name: e.target.name,
        class: e.target.className,
        text: e.target.innerText?.substring(0,50),
        time: new Date().toISOString()
    });
}, true);
document.addEventListener('change', e => {
    window.allChanges.push({
        tag: e.target.tagName,
        id: e.target.id,
        name: e.target.name,
        value: e.target.value,
        time: new Date().toISOString()
    });
}, true);
console.log('LOGGER READY');
""")

        # Wait 10 minutes
        import time
        start = time.time()
        while time.time() - start < 600:
            await page.sleep(1)

    finally:
        print("\n[EXTRACTING DATA]")

        # Get all interactions
        clicks = await page.evaluate("window.allClicks")
        changes = await page.evaluate("window.allChanges")

        print(f"Captured {len(clicks)} clicks and {len(changes)} changes")

        # Save
        data = {
            "timestamp": datetime.now().isoformat(),
            "clicks": clicks,
            "changes": changes,
            "total_events": len(clicks) + len(changes)
        }

        with open("interactions_log.json", "w") as f:
            json.dump(data, f, indent=2)

        print(f"Saved to: interactions_log.json")
        print(f"Total events: {data['total_events']}")

        browser.stop()

asyncio.run(main())
