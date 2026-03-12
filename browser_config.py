"""
Shared browser configuration for all nodriver scrapers.
Single source of truth for headless Chrome settings in containerized environments.
"""

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--single-process",
    "--no-zygote",
]

HEADLESS = True