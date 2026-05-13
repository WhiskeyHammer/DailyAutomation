const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const interactions = [];
const startTime = Date.now();

async function recordInteractions(page) {
  // Inject comprehensive tracking for all user interactions
  await page.evaluateHandle(() => {
    window.__interactions = [];

    // Track all input/textarea/select changes
    const trackInputChange = (element, value) => {
      window.__interactions.push({
        timestamp: new Date().toISOString(),
        type: 'input_change',
        element: {
          tag: element.tagName,
          id: element.id || null,
          name: element.name || null,
          type: element.type || null,
          className: element.className || null,
          placeholder: element.placeholder || null,
          label: document.querySelector(`label[for="${element.id}"]`)?.textContent || null
        },
        value: String(value).slice(0, 200)
      });
    };

    // Monitor input/textarea elements for value changes
    document.addEventListener('input', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        trackInputChange(e.target, e.target.value);
      }
    }, true);

    // Monitor for change events (select dropdowns, checkboxes, radios)
    document.addEventListener('change', (e) => {
      const target = e.target;
      if (target.tagName === 'SELECT') {
        trackInputChange(target, target.value);
      } else if (target.tagName === 'INPUT' && (target.type === 'checkbox' || target.type === 'radio')) {
        window.__interactions.push({
          timestamp: new Date().toISOString(),
          type: 'checkbox_change',
          element: {
            tag: target.tagName,
            id: target.id || null,
            name: target.name || null,
            type: target.type,
            className: target.className || null,
            label: document.querySelector(`label[for="${target.id}"]`)?.textContent || null
          },
          checked: target.checked
        });
      }
    }, true);

    // Track all clicks on buttons and clickable elements
    document.addEventListener('click', (e) => {
      const target = e.target;
      const clickable = target.closest('button, a, [role="button"], input[type="button"], input[type="submit"], .btn, [onclick]');

      if (clickable) {
        window.__interactions.push({
          timestamp: new Date().toISOString(),
          type: 'click',
          element: {
            tag: clickable.tagName,
            id: clickable.id || null,
            name: clickable.name || null,
            type: clickable.type || null,
            className: clickable.className || null,
            text: clickable.textContent?.slice(0, 100) || null,
            href: clickable.href || null,
            ariaLabel: clickable.getAttribute('aria-label') || null
          },
          x: e.clientX,
          y: e.clientY
        });
      }
    }, true);

    // Track form submissions
    document.addEventListener('submit', (e) => {
      const formData = new FormData(e.target);
      const data = {};
      for (let [key, value] of formData) {
        if (!data[key]) {
          data[key] = value;
        } else if (Array.isArray(data[key])) {
          data[key].push(value);
        } else {
          data[key] = [data[key], value];
        }
      }

      window.__interactions.push({
        timestamp: new Date().toISOString(),
        type: 'form_submit',
        element: {
          tag: 'FORM',
          id: e.target.id || null,
          name: e.target.name || null,
          className: e.target.className || null,
          action: e.target.action || null
        },
        formData: data
      });
    }, true);

    // Use MutationObserver to catch React/Vue synthetic event value changes
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === 'attributes' && mutation.attributeName === 'value') {
          const element = mutation.target;
          if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
            trackInputChange(element, element.value);
          }
        }
      });
    });

    // Observe all input elements for attribute changes
    document.querySelectorAll('input, textarea, select').forEach(el => {
      observer.observe(el, { attributes: true, attributeFilter: ['value', 'checked'] });
    });

    // Watch for new inputs added to the DOM
    const domObserver = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.querySelectorAll) {
            node.querySelectorAll('input, textarea, select').forEach(el => {
              observer.observe(el, { attributes: true, attributeFilter: ['value', 'checked'] });
            });
          }
        });
      });
    });

    domObserver.observe(document.body, { childList: true, subtree: true });
  });

  // Track navigation
  page.on('framenavigated', (frame) => {
    interactions.push({
      timestamp: new Date().toISOString(),
      type: 'navigation',
      url: frame.url()
    });
  });

  // Track network requests with details
  page.on('request', (request) => {
    const postData = request.postData();
    if ((request.method() === 'POST' || request.method() === 'GET') &&
        (request.url().includes('search') || request.url().includes('filter') ||
         request.url().includes('api') || request.url().includes('inventory'))) {
      interactions.push({
        timestamp: new Date().toISOString(),
        type: 'api_request',
        method: request.method(),
        url: request.url(),
        data: postData ? postData.slice(0, 300) : null
      });
    }
  });
}

async function saveInteractions(page) {
  try {
    const pageInteractions = await page.evaluate(() => window.__interactions || []);
    interactions.push(...pageInteractions);
  } catch (e) {
    // Page may already be closed
  }

  // Remove duplicates based on timestamp and type
  const seen = new Set();
  const uniqueInteractions = interactions.filter(int => {
    const key = `${int.timestamp}-${int.type}-${int.element?.id || int.element?.name || int.url || ''}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const output = {
    recordingDuration: Date.now() - startTime,
    startTime: new Date(startTime).toISOString(),
    endTime: new Date().toISOString(),
    totalInteractions: uniqueInteractions.length,
    interactions: uniqueInteractions.sort((a, b) =>
      new Date(a.timestamp) - new Date(b.timestamp)
    ),
  };

  const filename = `interaction-log-${Date.now()}.json`;
  const filepath = path.join(__dirname, filename);

  fs.writeFileSync(filepath, JSON.stringify(output, null, 2));
  console.log(`\n✓ Interactions saved to: ${filename}`);
  console.log(`✓ Total interactions recorded: ${uniqueInteractions.length}`);
  console.log(`✓ Recording duration: ${Math.round(output.recordingDuration / 1000)}s`);
}

async function main() {
  const browser = await chromium.launch({
    headless: false,
    args: ['--start-maximized']
  });
  const context = await browser.newContext({
    viewport: null
  });
  const page = await context.newPage();

  console.log('🌐 Browser launched. Recording interactions...');
  console.log('📝 Capturing all clicks, input changes, selections, and form submissions.');
  console.log('⚠️  Close the browser window when done recording.\n');

  // Start recording
  await recordInteractions(page);

  // Navigate to provided URL or default to about:blank
  const url = process.argv[2] || 'about:blank';
  console.log(`🔗 Loading: ${url}\n`);
  await page.goto(url, { waitUntil: 'networkidle' }).catch(() => {
    console.log('⚠️  Page loaded (with network activity still occurring)');
  });

  // Wait for browser to close
  page.on('close', async () => {
    await saveInteractions(page);
    await browser.close();
    process.exit(0);
  });

  context.on('close', async () => {
    await saveInteractions(page);
    await browser.close();
    process.exit(0);
  });

  // Keep the script running
  await new Promise(() => {});
}

main().catch(console.error);
