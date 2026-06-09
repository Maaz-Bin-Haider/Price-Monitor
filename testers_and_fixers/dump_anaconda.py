"""
Dumps Anaconda AU rendered HTML to diagnose the parser issues.
Run: python testers_and_fixers/dump_anaconda.py
"""
import requests, re, os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

TOKEN = settings.SCRAPE_DO_TOKEN

# Use a product Anaconda actually sells
r = requests.get("https://api.scrape.do", params={
    "token":     TOKEN,
    "url":       "https://www.anacondastores.com/en-au/search?q=GoPro",
    "geoCode":   "au",
    "render":    "true",
    "waitUntil": "networkidle0",
}, timeout=90)

print(f"Status: {r.status_code}  Size: {len(r.text):,}")
html = r.text

# Find card-link elements
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, 'lxml')
cards = soup.find_all("a", class_="card-link")
print(f"\ncard-link elements found: {len(cards)}")

if cards:
    print("\n=== First card full HTML ===")
    print(str(cards[0])[:800])
    print("\n=== All card hrefs (to check duplicates) ===")
    for i, c in enumerate(cards[:6]):
        href  = c.get("href","")
        texts = list(c.stripped_strings)
        print(f"  [{i+1}] href: {href[:60]}")
        print(f"       texts: {texts[:5]}")
else:
    print("\nNo card-link found — checking what IS in page...")
    for term in ["card", "product", "GoPro", "gopro", "search-result"]:
        count = html.count(term)
        if count:
            idx = html.find(term)
            print(f"  '{term}': {count}x  {repr(html[max(0,idx-40):idx+80])}")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anaconda_raw.html")
open(out, "w", encoding="utf-8").write(html)
print(f"\nSaved: {out} — upload to Claude.")
