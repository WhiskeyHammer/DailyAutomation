import asyncio
import nodriver as uc
import json
from datetime import datetime

async def load_with_logging():
    print("\n" + "="*70)
    print("LOADING USED AUTO PARTS FL WITH INTERACTION LOGGER")
    print("="*70)
    print("\nSimply:")
    print("1. Do your search for DODGE DAKOTA")
    print("2. Close the browser when done")
    print("3. All interactions will be automatically saved\n")
    print("="*70 + "\n")

    browser = await uc.start(headless=False)
    try:
        page = await browser.get("https://www.usedautopartsfl.com/parts")

        # Maximize window
        await page.evaluate("window.moveTo(0, 0); window.resizeTo(screen.width, screen.height);")

        # Inject comprehensive logging JavaScript
        logging_script = """
window.interactions = [];
window.pageSnapshots = [];

// Log all clicks
document.addEventListener('click', (e) => {
    const element = e.target;
    const log = {
        type: 'CLICK',
        tag: element.tagName,
        id: element.id || 'NO_ID',
        class: element.className || 'NO_CLASS',
        text: element.innerText?.substring(0, 100) || '',
        name: element.name || '',
        value: element.value || '',
        xpath: getXPath(element),
        timestamp: new Date().toISOString()
    };
    window.interactions.push(log);
}, true);

// Log all form input changes
document.addEventListener('change', (e) => {
    const element = e.target;
    const log = {
        type: 'CHANGE',
        tag: element.tagName,
        id: element.id || 'NO_ID',
        name: element.name || '',
        value: element.value || '',
        xpath: getXPath(element),
        timestamp: new Date().toISOString()
    };
    window.interactions.push(log);
}, true);

// Log all input/text changes
document.addEventListener('input', (e) => {
    const element = e.target;
    const log = {
        type: 'INPUT',
        tag: element.tagName,
        id: element.id || 'NO_ID',
        name: element.name || '',
        value: element.value || '',
        placeholder: element.placeholder || '',
        xpath: getXPath(element),
        timestamp: new Date().toISOString()
    };
    window.interactions.push(log);
}, true);

// Log all form submissions
document.addEventListener('submit', (e) => {
    const log = {
        type: 'SUBMIT',
        formId: e.target.id || 'NO_ID',
        formName: e.target.name || 'NO_NAME',
        formAction: e.target.action || 'NO_ACTION',
        formMethod: e.target.method || 'NO_METHOD',
        timestamp: new Date().toISOString()
    };
    window.interactions.push(log);
}, true);

// Log all select changes
document.addEventListener('change', (e) => {
    if (e.target.tagName === 'SELECT') {
        const select = e.target;
        const selectedOption = select.options[select.selectedIndex];
        const log = {
            type: 'SELECT_CHANGE',
            selectName: select.name || 'NO_NAME',
            selectId: select.id || 'NO_ID',
            selectedValue: select.value,
            selectedText: selectedOption?.text || '',
            xpath: getXPath(select),
            timestamp: new Date().toISOString()
        };
        window.interactions.push(log);
    }
}, true);

// Helper function to get XPath
function getXPath(element) {
    if (element.id !== '')
        return "//*[@id='" + element.id + "']";
    if (element === document.body)
        return element.tagName.toLowerCase();

    var ix = 0;
    var siblings = element.parentNode.childNodes;
    for (var i = 0; i < siblings.length; i++) {
        var sibling = siblings[i];
        if (sibling === element)
            return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
        if (sibling.nodeType === 1 && sibling.tagName.toLowerCase() === element.tagName.toLowerCase())
            ix++;
    }
}

console.log('✅ LOGGER INITIALIZED');
"""

        await page.evaluate(logging_script)
        print("[LOGGER ACTIVE] Perform your search now. Waiting 5 minutes...\n")

        # Keep browser open for 5 minutes or until interrupted
        import time
        start_time = time.time()
        timeout = 300  # 5 minutes

        while time.time() - start_time < timeout:
            await page.sleep(1)

    except KeyboardInterrupt:
        print("\n[STOPPING]")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Extracting logged interactions...")

        try:
            # Extract all interactions from the page
            interactions = await page.evaluate("window.interactions")

            # Save to file
            output_file = r"c:\Users\Whisk\OneDrive\Desktop\Code\DailyAutomation\usedautopartsfl_interactions.json"

            with open(output_file, 'w') as f:
                json.dump({
                    "site": "Used Auto Parts FL",
                    "url": "https://www.usedautopartsfl.com/parts",
                    "timestamp": datetime.now().isoformat(),
                    "total_interactions": len(interactions),
                    "interactions": interactions
                }, f, indent=2)

            print(f"\n[SUCCESS] Saved {len(interactions)} interactions to:")
            print(f"   {output_file}")
            print(f"\nAnalyzing interactions...")

            # Print summary
            clicks = [i for i in interactions if i['type'] == 'CLICK']
            changes = [i for i in interactions if i['type'] == 'CHANGE']
            inputs = [i for i in interactions if i['type'] == 'INPUT']
            selects = [i for i in interactions if i['type'] == 'SELECT_CHANGE']
            submits = [i for i in interactions if i['type'] == 'SUBMIT']

            print(f"\n[SUMMARY]")
            print(f"   Total clicks: {len(clicks)}")
            print(f"   Total form changes: {len(changes)}")
            print(f"   Total text inputs: {len(inputs)}")
            print(f"   Total select changes: {len(selects)}")
            print(f"   Total form submissions: {len(submits)}")

            if selects:
                print(f"\n[SELECT CHANGES]")
                for sel in selects:
                    print(f"   - {sel.get('selectName', 'unknown')}: {sel.get('selectedText', sel.get('selectedValue', 'N/A'))}")

            if clicks:
                print(f"\n[KEY CLICKS]")
                for click in clicks[-10:]:  # Last 10 clicks
                    print(f"   - {click.get('id', click.get('class', 'unknown'))}: {click.get('text', '')[:50]}")

        except Exception as e:
            print(f"Error extracting interactions: {e}")

        browser.stop()
        print("\n[DONE] Check the JSON file for complete interaction log.")

if __name__ == "__main__":
    asyncio.run(load_with_logging())
