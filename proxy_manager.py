import os
import random

def create_proxy_auth_extension(proxy_string, plugin_dir):
    """
    Parses a proxy string (ip:port:user:pass) and creates a Chrome extension
    to handle the authentication automatically.
    """
    try:
        # Parse the Webshare format: ip:port:user:pass
        parts = proxy_string.strip().split(':')
        if len(parts) != 4:
            print(f"Invalid proxy format: {proxy_string}")
            return None

        ip, port, user, password = parts

        manifest_json = """
        {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Chrome Proxy",
            "permissions": [
                "proxy",
                "tabs",
                "unlimitedStorage",
                "storage",
                "<all_urls>",
                "webRequest",
                "webRequestBlocking"
            ],
            "background": {
                "scripts": ["background.js"]
            },
            "minimum_chrome_version":"22.0.0"
        }
        """

        background_js = f"""
        var config = {{
                mode: "fixed_servers",
                rules: {{
                  singleProxy: {{
                    scheme: "http",
                    host: "{ip}",
                    port: parseInt({port})
                  }},
                  bypassList: ["localhost"]
                }}
              }};

        chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

        function callbackFn(details) {{
            return {{
                authCredentials: {{
                    username: "{user}",
                    password: "{password}"
                }}
            }};
        }}

        chrome.webRequest.onAuthRequired.addListener(
                    callbackFn,
                    {{urls: ["<all_urls>"]}},
                    ['blocking']
        );
        """

        os.makedirs(plugin_dir, exist_ok=True)
        
        with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
            f.write(manifest_json)

        with open(os.path.join(plugin_dir, "background.js"), "w") as f:
            f.write(background_js)

        return plugin_dir

    except Exception as e:
        print(f"Error creating proxy extension: {e}")
        return None

def get_random_proxy(proxies_file_path):
    """Reads proxies.txt and returns a random proxy string."""
    if not os.path.exists(proxies_file_path):
        print(f"Proxy file not found: {proxies_file_path}")
        return None
        
    with open(proxies_file_path, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    if not lines:
        return None
        
    return random.choice(lines)