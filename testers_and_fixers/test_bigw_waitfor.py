"""
Tests BigW with waitFor a product selector instead of networkidle0.
networkidle0 fires before BigW's product API responds.
waitFor makes Scrape.do wait until an actual product tile appears in the DOM.

Run: python testers_and_fixers/test_bigw_waitfor.py
"""
import requests, re, json, sys, os
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

TOKEN = settings.SCRAPE_DO_TOKEN

# Selectors to try — BigW's React components
SELECTORS = [
    "[data-testid='product-tile']",
    "[class*='ProductTile']",
    "[class*='product-tile']",
    "h3[class*='ProductTitle']",
    "[class*='SearchResult']",
]

URL = "https://www.bigw.com.au/search?text=DJI+Mini+4K+Fly+More+Combo"

for selector in SELECTORS:
    print(f"\nTrying waitFor: {selector}")
    r = requests.get("https://api.scrape.do", params={
        "token":    TOKEN,
        "url":      URL,
        "geoCode":  "au",
        "render":   "true",
        "super":    "true",
        "waitFor":  selector,
        # Do NOT use waitUntil — let waitFor be the trigger
    }, timeout=90)

    print(f"  Status: {r.status_code}  Size: {len(r.text):,}")

    if r.status_code != 200:
        print(f"  FAILED: {r.text[:100]}")
        continue

    html = r.text

    # Check if products appeared
    dji_count    = html.count("DJI")
    product_hits = html.count("product-tile") + html.count("ProductTile")
    price_hits   = html.count("$")

    print(f"  DJI mentions: {dji_count}")
    print(f"  product-tile/ProductTile: {product_hits}")
    print(f"  $ signs: {price_hits}")

    if dji_count > 5:
        print(f"  ✓ PRODUCTS FOUND — saving HTML")
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bigw_waitfor_raw.html")
        open(out, "w", encoding="utf-8").write(html)
        print(f"  Saved: {out}")
        print(f"  Upload bigw_waitfor_raw.html to Claude.")
        break
    else:
        print(f"  ✗ Still no products with this selector")
