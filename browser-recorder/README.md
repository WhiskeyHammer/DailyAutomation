# Browser Interaction Recorder

A Playwright-based tool that launches a browser and records all your user interactions (clicks, typing, form submissions, navigation).

## Quick Start

```bash
node recorder.js
```

This will:
1. Launch a visible Chrome browser
2. Start recording all your interactions
3. When you close the browser, save all interactions to a JSON file

## Output

The script generates a JSON log file with the following format:

```json
{
  "recordingDuration": 45000,
  "startTime": "2026-04-21T15:30:00.000Z",
  "endTime": "2026-04-21T15:30:45.000Z",
  "totalInteractions": 23,
  "interactions": [
    {
      "timestamp": "2026-04-21T15:30:05.123Z",
      "type": "navigation",
      "url": "https://example.com",
      "previousUrl": "about:blank"
    },
    {
      "timestamp": "2026-04-21T15:30:10.456Z",
      "type": "click",
      "element": {
        "tag": "BUTTON",
        "id": "submit-btn",
        "class": "btn btn-primary",
        "text": "Click me"
      },
      "x": 123,
      "y": 456
    },
    {
      "timestamp": "2026-04-21T15:30:12.789Z",
      "type": "input",
      "element": {
        "tag": "INPUT",
        "id": "search-field",
        "name": "q",
        "type": "text"
      },
      "value": "my search query"
    },
    {
      "timestamp": "2026-04-21T15:30:15.321Z",
      "type": "submit",
      "element": {
        "tag": "FORM",
        "id": "search-form",
        "class": "search-container"
      }
    }
  ]
}
```

## Recorded Events

- **click**: Button clicks, link clicks, element clicks (includes x/y coordinates)
- **input**: Text input, textarea input, select changes (includes the value typed)
- **submit**: Form submissions
- **navigation**: Page navigations and URL changes

## Interaction Properties

Each interaction includes:
- `timestamp`: ISO 8601 timestamp of when the interaction happened
- `type`: The type of interaction (click, input, submit, navigation)
- `element`: Information about the element that was interacted with
  - `tag`: HTML tag name
  - `id`: Element ID (if present)
  - `class`: Element classes (if present)
  - `name`: Element name (for form elements)
  - `type`: Input type (for form elements)
  - `text`: Element text content (first 100 chars)
  - `value`: Input value (for input events, first 100 chars)
- `x`, `y`: Mouse coordinates (for click events only)

## Tips

- The browser starts at `about:blank` — navigate to any URL you want to record
- All interactions are timestamped for accurate sequencing
- Element information helps you identify exactly what was clicked/typed
- The JSON output is perfect for analysis, automation, or testing

## Files Generated

- `interaction-log-<timestamp>.json`: Complete interaction log with all metadata
