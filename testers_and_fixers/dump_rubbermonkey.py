"""
Dumps Rubber Monkey AU HTML to diagnose parser failure.
Run: python testers_and_fixers/dump_rubbermonkey.py
"""
import requests, re, os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

r = requests.get("https://api.scrape.do", params={
    "token":   settings.SCRAPE_DO_TOKEN,
    "url":     "https://www.rubbermonkey.com.au/Search?searchText=DJI+Osmo+Pocket+4",
    "geoCode": "au",
}, timeout=60)

print(f"Status: {r.status_code}  Size: {len(r.text):,}")
html = r.text

from bs4 import BeautifulSoup
soup = BeautifulSoup(html, 'lxml')

print("\n--- Key patterns ---")
for term in ["product-tile", "ProductTile", "product-card", "ProductCard",
             "data-testid", "DJI", "Osmo", "price", "search-result",
             "product-list", "product-item", "ProductItem"]:
    c = html.count(term)
    if c:
        idx = html.find(term)
        ctx = html[max(0,idx-60):idx+100].replace('\n',' ')
        print(f"  '{term}': {c}x  …{ctx[:130]}…")

print("\n--- All class names with product/price/search/result/item/grid ---")
all_classes = set()
for tag in soup.find_all(class_=True):
    for cls in tag.get('class', []):
        if any(k in cls.lower() for k in ['product','price','search','result','item','grid','tile']):
            all_classes.add(cls)
for c in sorted(all_classes):
    print(f"  .{c}")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rubbermonkey_raw.html")
open(out, "w", encoding="utf-8").write(html)
print(f"\nSaved: {out} — upload to Claude.")
