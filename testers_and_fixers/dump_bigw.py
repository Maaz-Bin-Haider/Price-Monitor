"""
Dumps the BigW heavy-tier rendered HTML so we can see the actual product card structure.
Run: python testers_and_fixers/dump_bigw.py
"""
import requests, re, os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

TOKEN = settings.SCRAPE_DO_TOKEN

params = {
    "token":     TOKEN,
    "url":       "https://www.bigw.com.au/search?text=DJI+Mini+4K+Fly+More+Combo",
    "geoCode":   "au",
    "render":    "true",
    "super":     "true",
    "waitUntil": "networkidle0",
}

print("Fetching BigW (heavy tier)...")
r = requests.get("https://api.scrape.do", params=params, timeout=90)
print(f"Status: {r.status_code}  Size: {len(r.text):,}")

html = r.text

# Key diagnostics
print("\n--- Key patterns found ---")
checks = [
    "data-testid", "product-tile", "ProductTile", "product-card",
    "ProductCard", "DJI", "dji", "Mini 4K", "price", "Price",
    "$", "listItem", "product", "Product", "article", "grid",
]
for c in checks:
    count = html.count(c)
    if count:
        idx = html.find(c)
        ctx = html[max(0,idx-60):idx+100].replace('\n',' ')
        print(f"  '{c}': {count}x  …{ctx[:120]}…")

# Save full HTML
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bigw_heavy_raw.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"\nSaved: {out}")
print("Upload bigw_heavy_raw.html to Claude for parser fix.")
