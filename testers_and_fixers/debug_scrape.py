"""
Run this script to debug what HTML Scrape.do returns for a site,
and test if our selectors are finding anything.

Usage: python debug_scrape.py
"""
import asyncio
import os
from bs4 import BeautifulSoup

# Load .env
from dotenv import load_dotenv
load_dotenv()

from scraper.client import fetch_page
from scraper.parsers import SITE_PARSERS, parse_results

# ── CONFIGURE THESE ──────────────────────────────────────────────
PRODUCT = "Starlink standard kit v4"
TEST_SITES = [
    {"name": "JB Hi-Fi AU",  "domain": "jbhifi.com.au",       "tier": "heavy",  "geo": "au", "url": "https://www.jbhifi.com.au/search?q=Starlink+standard+kit+v4"},
    {"name": "The Good Guys","domain": "thegoodguys.com.au",   "tier": "medium", "geo": "au", "url": "https://www.thegoodguys.com.au/search?q=Starlink+standard+kit+v4"},
    {"name": "Big W",        "domain": "bigw.com.au",          "tier": "medium", "geo": "au", "url": "https://www.bigw.com.au/search?q=Starlink+standard+kit+v4"},
]
# ─────────────────────────────────────────────────────────────────

async def debug_site(site):
    print(f"\n{'='*60}")
    print(f"Testing: {site['name']} ({site['domain']})")
    print(f"URL: {site['url']}")
    print(f"{'='*60}")

    html = await fetch_page(site["url"], site["tier"], site["geo"])

    if html is None:
        print("❌ fetch_page returned None (check token / network)")
        return

    print(f"✅ Got HTML ({len(html):,} bytes)")

    # Save HTML to file for manual inspection
    fname = f"debug_{site['domain']}.html"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"📄 Saved to {fname} — open in browser to inspect")

    # Try our selectors
    rules = SITE_PARSERS.get(site["domain"])
    if not rules:
        print("⚠️  No parser defined for this domain")
        return

    soup = BeautifulSoup(html, "lxml")

    print(f"\n🔍 Trying results selector: {rules['results']}")
    cards = []
    for sel in rules["results"].split(","):
        sel = sel.strip()
        found = soup.select(sel)
        print(f"   '{sel}' → {len(found)} cards")
        if found and not cards:
            cards = found

    if not cards:
        print("\n❌ No product cards found with current selectors")
        print("\n📋 Top-level divs/articles on page (to help find right selector):")
        for tag in soup.find_all(["article", "li"], limit=5):
            classes = " ".join(tag.get("class", []))
            print(f"   <{tag.name} class='{classes[:80]}'>")
    else:
        print(f"\n✅ Found {len(cards)} cards")
        # Try parsing
        results = parse_results(html, site["domain"])
        print(f"✅ parse_results returned {len(results)} items")
        for r in results[:3]:
            print(f"   - {r['title'][:60]} | ${r['price']} | {r['link'][:60]}")

async def main():
    for site in TEST_SITES:
        await debug_site(site)
    print("\n\nDone. Check the .html files saved above to inspect page structure.")

asyncio.run(main())
