"""
Dumps Bunnings AU rendered HTML to diagnose parser failure.
Run: python testers_and_fixers/dump_bunnings.py
"""
import requests, re, os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

TOKEN = settings.SCRAPE_DO_TOKEN

r = requests.get("https://api.scrape.do", params={
    "token":     TOKEN,
    "url":       "https://www.bunnings.com.au/search/products?q=drill",
    "geoCode":   "au",
    "render":    "true",
    "waitUntil": "networkidle0",
}, timeout=90)

print(f"Status: {r.status_code}  Size: {len(r.text):,}")
html = r.text

# Key diagnostics
print("\n--- Patterns found ---")
for term in ["product-list", "product-tile", "ProductTile", "data-testid",
             "article", "Dewalt", "dewalt", "drill", "price", "Price",
             "$", "__NEXT_DATA__", "product-item", "search-result"]:
    c = html.count(term)
    if c:
        idx = html.find(term)
        ctx = html[max(0,idx-60):idx+100].replace('\n',' ')
        print(f"  '{term}': {c}x  …{ctx[:130]}…")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bunnings_raw.html")
open(out, "w", encoding="utf-8").write(html)
print(f"\nSaved: {out}  — upload to Claude.")
