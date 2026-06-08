"""
Tests BigW's storefront JSON API via Scrape.do super_norender.
This bypasses the React rendering issue entirely.
Run: python testers_and_fixers/test_bigw_api.py
"""
import requests, json, re, sys, os
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

TOKEN = settings.SCRAPE_DO_TOKEN

# BigW storefront API — returns JSON directly, no JS needed
API_URL = "https://api.bigw.com.au/storefront/v1/search?query=DJI+Mini+4K+Fly+More+Combo&page=1&pageSize=5"

print(f"Fetching: {API_URL}")
print("Tier: super_norender (super=true, no render)")

r = requests.get("https://api.scrape.do", params={
    "token":   TOKEN,
    "url":     API_URL,
    "geoCode": "au",
    "super":   "true",
    # NO render=true — we want the raw JSON response
}, timeout=60)

print(f"Status: {r.status_code}  Size: {len(r.text):,}")
print()

if r.status_code != 200:
    print(f"FAILED: {r.text[:200]}")
    exit(1)

html = r.text

# Scrape.do may wrap JSON in HTML envelope — try to extract JSON
raw_json = None

# Strategy 1: inside <pre> tag
m = re.search(r'<pre[^>]*>(.*?)</pre>', html, re.DOTALL)
if m:
    raw_json = m.group(1).strip()
    print("JSON found inside <pre> tag")

# Strategy 2: starts with { directly
if not raw_json:
    for marker in ['{"products"', '{"results"', '{"data"', '[{']:
        pos = html.find(marker)
        if pos != -1:
            chunk = html[pos:]
            chunk = re.sub(r'(</(pre|body|html)>.*$)', '', chunk,
                          flags=re.DOTALL | re.IGNORECASE).strip()
            raw_json = chunk
            print(f"JSON found starting with: {marker}")
            break

# Strategy 3: raw
if not raw_json and (html.strip().startswith('{') or html.strip().startswith('[')):
    raw_json = html.strip()
    print("JSON is raw response")

if not raw_json:
    print("No JSON found — Scrape.do returned HTML shell")
    print("First 500 chars:")
    print(repr(html[:500]))
    exit(1)

# Parse and inspect
try:
    data = json.loads(raw_json)
    print(f"Top-level keys: {list(data.keys())}")
    print()

    # Try common product list keys
    products = (
        data.get("products") or
        data.get("results") or
        data.get("data", {}).get("products") or
        []
    )

    print(f"Products found: {len(products)}")
    if products:
        print(f"\nFirst product keys: {list(products[0].keys())}")
        print(f"\nFirst product full:\n{json.dumps(products[0], indent=2)[:800]}")
    else:
        print("No products — full response:")
        print(json.dumps(data, indent=2)[:1000])

except json.JSONDecodeError as e:
    print(f"JSON parse error: {e}")
    print(f"Raw first 500: {repr(raw_json[:500])}")
