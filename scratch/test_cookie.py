import browser_cookie3
import os

try:
    print("Extracting cookies...")
    cookie_jar = browser_cookie3.chrome(domain_name='openrouter.ai')
    cookies = list(cookie_jar)
    print(f"Found {len(cookies)} cookies for openrouter.ai!")
    for c in cookies:
        print(f"- {c.name}")
except Exception as e:
    print(f"Error: {e}")
