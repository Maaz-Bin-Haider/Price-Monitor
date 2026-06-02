"""
Reads HTML already saved by test_all_sites.py and finds the correct
selectors for each broken site. Run AFTER test_all_sites.py has run.

Usage: python fix_selectors.py
"""
import asyncio, sys, os, re, json
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

import httpx
from config import SITES, settings
from bs4 import BeautifulSoup

# Sites that need selector inspection
INSPECT = [
    "harveynorman.com.au",
    "bigw.com.au",
    "bunnings.com.au",
    "bunnings.co.nz",
    "costco.com.au",
    "anacondastores.com",
    "bcf.com.au",
    "noelleeming.co.nz",
    "pbtech.co.nz",
    "rubbermonkey.com.au",
    "rubbermonkey.co.nz",
    "aucklandairport.co.nz",
]

# Sites still 404 — try alternative URL formats
URL_RETRY = {
    "harveynorman.co.nz": [
        "https://www.harveynorman.co.nz/index.php?subcats=Y&status=A&pshort=N&pfull=N&pname=Y&pkeywords=Y&search_performed=Y&q={query}&dispatch=products.search",
        "https://www.harveynorman.co.nz/search?q={query}",
    ],
    "officeworks.com.au": [
        "https://www.officeworks.com.au/information/search?q={query}&view=grid&page=1&sortby=tmp_priceSort&ascending=true",
        "https://www.officeworks.com.au/shop/officeworks/c/q={query}",
    ],
    "photogear.co.nz": [
        "https://photogear.co.nz/search?type=product&q={query}",
        "https://www.photogear.co.nz/search?type=product&q={query}",
    ],
    "photowarehouse.co.nz": [
        "https://www.photowarehouse.co.nz/search?type=product&q={query}",
        "https://photowarehouse.co.nz/search?q={query}",
    ],
    "jacobsdigital.co.nz": [
        "https://www.jacobsdigital.co.nz/search?type=product&q={query}",
        "https://jacobsdigital.co.nz/search?q={query}",
    ],
}

SITE_MAP = {s["domain"]: s for s in SITES}
semaphore = asyncio.Semaphore(3)


async def fetch_html(domain, url_override=None):
    site = SITE_MAP.get(domain, {})
    import urllib.parse
    query = urllib.parse.quote_plus("Sony headphones")
    url = url_override.format(query=query) if url_override else site["search_url"].format(query=query)

    params = {
        "token":   settings.SCRAPE_DO_TOKEN,
        "url":     url,
        "geoCode": site.get("geo", "au"),
    }
    tier = site.get("tier", "medium")
    if tier in ("heavy", "medium"):
        params["render"] = "true"
    if tier == "heavy":
        params["super"] = "true"

    async with semaphore:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.get("https://api.scrape.do", params=params)
                return domain, r.status_code, r.text, url
        except Exception as e:
            return domain, 0, "", url


def analyse_html(domain, html):
    """Deep analysis of HTML to find product selectors."""
    if not html or len(html) < 1000:
        return

    soup = BeautifulSoup(html, "lxml")
    title = soup.title.string[:80] if soup.title else "no title"
    print(f"\n{'─'*60}")
    print(f"  {domain}  ({len(html):,} bytes)")
    print(f"  Page: {title}")
    print(f"{'─'*60}")

    # 1. Check for Shopify JSON
    shopify = re.findall(
        r'"handle":"([^"]+)","variants":\[{"id":\d+,"price":(\d+),"name":"([^"]+)"',
        html[:200000]
    )
    if shopify:
        print(f"  ✓ SHOPIFY JSON: {len(shopify)} products")
        for h, p, n in shopify[:2]:
            print(f"    ${int(p)/100:.2f} — {n[:50]}")
        return

    # 2. Check for Next.js __NEXT_DATA__
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if nd:
        print(f"  ✓ __NEXT_DATA__ found ({len(nd.group(1)):,} chars)")
        # Try to find products in it
        data_str = nd.group(1)
        prices = re.findall(r'"price[^"]*"\s*:\s*"?(\d+\.?\d*)"?', data_str[:5000])
        names  = re.findall(r'"(?:name|title|productName)"\s*:\s*"([^"]{5,60})"', data_str[:5000])
        if prices and names:
            print(f"    Products in NEXT_DATA: names={names[:2]}, prices={prices[:2]}")
        return

    # 3. Look for product-like CSS classes
    class_counts = {}
    for el in soup.find_all(True, class_=True):
        for cls in el.get("class", []):
            cl = cls.lower()
            if any(kw in cl for kw in ["product", "item", "tile", "card", "result", "listing", "prod"]):
                key = f"<{el.name}[class*='{cls}']>"
                class_counts[key] = class_counts.get(key, 0) + 1

    top = sorted(class_counts.items(), key=lambda x: -x[1])[:6]
    if top:
        print(f"  Product-like CSS classes:")
        for k, v in top:
            print(f"    {v:3}x  {k}")

    # 4. Look for data-testid
    tids = {}
    for el in soup.find_all(attrs={"data-testid": True}):
        tid = el["data-testid"]
        if any(kw in tid.lower() for kw in ["product","item","tile","card","price","result","name"]):
            tids[tid] = tids.get(tid, 0) + 1
    if tids:
        print(f"  data-testid attributes:")
        for k, v in sorted(tids.items(), key=lambda x: -x[1])[:5]:
            print(f"    {v:3}x  [{k}]")

    # 5. Check for automation-id (Costco)
    aids = {}
    for el in soup.find_all(attrs={"automation-id": True}):
        aid = el["automation-id"]
        if any(kw in aid.lower() for kw in ["product","price","item","name"]):
            aids[aid] = aids.get(aid, 0) + 1
    if aids:
        print(f"  automation-id attributes:")
        for k, v in sorted(aids.items(), key=lambda x: -x[1])[:5]:
            print(f"    {v:3}x  [{k}]")

    # 6. Sample first product element
    for tag in ["article", "li", "div"]:
        els = [el for el in soup.find_all(tag, class_=True)
               if any(kw in " ".join(el.get("class",[])).lower()
                      for kw in ["product","tile","card","prod-","item"])]
        if els:
            sample = str(els[0])[:500]
            print(f"  First product-like element:")
            print(f"    {sample}")
            break

    # 7. Look for price patterns
    prices_in_text = re.findall(r'\$[\d,]+\.?\d*', html[:100000])
    print(f"  Price-like strings in HTML: {len(prices_in_text)} found, e.g. {prices_in_text[:3]}")

    # 8. Check for embedded JSON arrays
    json_arrays = re.findall(r'"products"\s*:\s*\[', html[:500000])
    if json_arrays:
        print(f"  JSON 'products' array found: {len(json_arrays)} occurrences")

    items_arrays = re.findall(r'"items"\s*:\s*\[', html[:500000])
    if items_arrays:
        print(f"  JSON 'items' array found: {len(items_arrays)} occurrences")


async def main():
    print("="*60)
    print("  SELECTOR FIXER — Fetching HTML from broken sites")
    print("="*60)

    # Fetch all broken sites
    tasks = [fetch_html(d) for d in INSPECT]
    results = await asyncio.gather(*tasks)

    for domain, code, html, url in results:
        if code == 200 and html:
            analyse_html(domain, html)
            # Save for manual inspection
            fname = os.path.join(os.path.dirname(__file__), f"debug_{domain.replace('.','_')}.html")
            with open(fname, "w", encoding="utf-8", errors="ignore") as f:
                f.write(html)
        else:
            print(f"\n  {domain}: HTTP {code} for {url}")

    # Try alternative URLs for 404 sites
    print(f"\n{'='*60}")
    print(f"  TRYING ALTERNATIVE URLS FOR 404 SITES")
    print(f"{'='*60}")
    for domain, urls in URL_RETRY.items():
        for url_tpl in urls:
            _, code, html, url = await fetch_html(domain, url_tpl)
            status = f"HTTP {code}" if code != 200 else f"✓ OK ({len(html):,} bytes)"
            print(f"  {domain}: {status}")
            print(f"    URL: {url}")
            if code == 200 and html:
                # Save HTML file for manual inspection
                fname = os.path.join(os.path.dirname(__file__), f"debug_{domain.replace('.','_')}.html")
                with open(fname, "w", encoding="utf-8", errors="ignore") as f2:
                    f2.write(html)
                print(f"    Saved to {fname}")
                analyse_html(domain, html)
                break
        else:
            print(f"  {domain}: All URLs failed")

asyncio.run(main())
