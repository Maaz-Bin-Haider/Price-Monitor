"""
Dumps the medium-tier (JS-rendered) Scrape.do response for jacobsdigital.co.nz
Save to testers_and_fixers/ and run from price_monitor root:
    python testers_and_fixers\dump_jacobsdigital.py
"""
import asyncio, sys, os
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx, urllib.parse
from config import settings

async def dump():
    query = urllib.parse.quote_plus("Minelab GPX 6000 Metal Detector")
    url = f"https://www.jacobsdigital.co.nz/search?type=product&q={query}"

    params = {
        "token":     settings.SCRAPE_DO_TOKEN,
        "url":       url,
        "geoCode":   "nz",
        "render":    "true",
        "waitUntil": "networkidle0",
    }

    print(f"Fetching (medium tier, JS rendered): {url}")
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get("https://api.scrape.do", params=params)

    raw = resp.text
    print(f"HTTP status : {resp.status_code}")
    print(f"Total length: {len(raw):,} chars")

    # Show first and last for structure clues
    print(f"\n{'='*60}\nFIRST 3000 chars:\n{'='*60}")
    print(repr(raw[:3000]))
    print(f"\n{'='*60}\nLAST 500 chars:\n{'='*60}")
    print(repr(raw[-500:]))

    # Key diagnostic: search for boost-pfs product items
    import re
    hits = re.findall(r'boost-pfs-filter-product-item["\s]', raw)
    print(f"\nboost-pfs-filter-product-item occurrences: {len(hits)}")

    # Search for any product card containers
    for selector in ['boost-pfs-filter-product-item', 'grid-product', 'product-card',
                     'product-item', 'Minelab', 'minelab', 'price_min', 'price']:
        count = raw.count(selector)
        if count:
            print(f"  '{selector}': {count} occurrences")

    # Save full file
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jacobsdigital_rendered.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(raw)
    print(f"\nFull rendered HTML saved to: {out}")
    print("Open that file in a browser or text editor to inspect the structure.")

asyncio.run(dump())
