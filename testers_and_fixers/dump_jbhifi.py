"""
Dumps JB Hi-Fi AU rendered HTML to diagnose parser failure.
Run: python testers_and_fixers/dump_jbhifi.py
"""
import requests, os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

r = requests.get("https://api.scrape.do", params={
    "token":     settings.SCRAPE_DO_TOKEN,
    "url":       "https://www.jbhifi.com.au/search?query=sony+headphones",
    "geoCode":   "au",
    "render":    "true",
    "super":     "true",
    "waitUntil": "networkidle0",
}, timeout=90)

print(f"Status: {r.status_code}  Size: {len(r.text):,}")
html = r.text

from bs4 import BeautifulSoup
import re

soup = BeautifulSoup(html, 'lxml')

# Check data-testid values
testids = set()
for el in soup.find_all(attrs={"data-testid": True}):
    testids.add(el.get("data-testid"))
print(f"\ndata-testid values ({len(testids)}):")
for t in sorted(testids):
    if any(k in t.lower() for k in ['product','price','tile','card','item','result']):
        print(f"  {t}")

# Check classes
print("\nRelevant classes:")
all_classes = set()
for tag in soup.find_all(class_=True):
    for cls in tag.get('class', []):
        if any(k in cls.lower() for k in ['product','price','tile','card','item','result','search']):
            all_classes.add(cls)
for c in sorted(all_classes)[:30]:
    print(f"  .{c}")

# Check if Sony appears
print(f"\n'Sony' count: {html.count('Sony')}")
print(f"'price' count: {html.count('price')}")

# Save
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jbhifi_raw.html")
open(out, "w", encoding="utf-8").write(html)
print(f"\nSaved: {out} — upload to Claude.")
