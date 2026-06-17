"""
bulk_site_check.py — Health check for all 22 scraping sites.

Each site is tested with a product known to be listed on that site.
Run from the price_monitor root directory:
    python testers_and_fixers/bulk_site_check.py

Options:
    --geo au          Only test AU sites
    --geo nz          Only test NZ sites
    --tier light      Only test light-tier sites
    --concurrency 3   How many sites to test in parallel (default: 3)
    --timeout 90      Scrape.do timeout in seconds (default: 90)
"""

import asyncio
import argparse
import sys
import os
import time
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from config import SITES, settings
from scraper.parsers import parse_results
from matcher.engine import filter_matches

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

# ── Per-site test products ─────────────────────────────────────────────────────
# Each value is a product reliably listed on that site.
# Change any of these to whatever product you want to test for that site.
SITE_PRODUCTS = {
    # ── Australia ──────────────────────────────────────────────────────────────
    "jbhifi.com.au":          "Sony WH-1000XM5 Headphones",
    "harveynorman.com.au":    "Sony WH-1000XM5 Headphones",
    "bigw.com.au":            "Apple AirPods Pro 3",
    "officeworks.com.au":     "Apple AirPods Pro 3",
    "thegoodguys.com.au":     "Sony WH-1000XM5 Headphones",
    "bunnings.com.au":        "Canon Xa65 4k Camcorder",
    "costco.com.au":          "Apple AirPods Pro",
    "anacondastores.com":     "Minelab Equinox 900 Metal Detector",
    "bcf.com.au":             "Minelab Gold Monster 1000 Metal Detector",
    "digidirect.com.au":      "Sony A7 Camera",
    "camerapro.com.au":       "Canon EOS Camera",
    "rubbermonkey.com.au":    "DJI Mini 5 Pro",
    # ── New Zealand ────────────────────────────────────────────────────────────
    "jbhifi.co.nz":           "Sony WH-1000XM5 Headphones",
    "harveynorman.co.nz":     "Sony WH-1000XM5 Headphones",
    "noelleeming.co.nz":      "Sony WH-1000XM5 Headphones",
    "pbtech.co.nz":           "Samsung SSD",
    "bunnings.co.nz":         "Starlink Standard 4 X",
    "themall.aucklandairport.co.nz": "DJI Neo Drone Fly More Combo",
    "rubbermonkey.co.nz":     "DJI Mini 5 Pro",
    "photogear.co.nz":        "DJI Mini 5 Pro Fly More Combo",
    "photowarehouse.co.nz":   "Sony Camera",
    "jacobsdigital.co.nz":    "Minelab Vanquish 360 Metal Detector",
} 

MATCH_THRESHOLD = 50   # lower than normal since test products are broad


# ── Fetch ─────────────────────────────────────────────────────────────────────

_502_MAX_RETRIES = 3    # sequential attempts before giving up on a 502
_502_RETRY_DELAY = 5.0  # seconds to wait between 502 retry attempts


async def fetch_site(site: dict, product: str, timeout: int) -> dict:
    """Fetch one site via Scrape.do.

    On HTTP 502 (Bad Gateway) the request is retried up to _502_MAX_RETRIES
    times with a short delay between each attempt before giving up.
    All other non-200 responses fail immediately (no retry).
    """
    import urllib.parse
    query = urllib.parse.quote_plus(product)
    url   = site["search_url"].format(query=query)

    if site.get("cache_bust"):
        url += f"&_ts={int(time.time())}"

    params = {
        "token":   settings.SCRAPE_DO_TOKEN,
        "url":     url,
        "geoCode": site["geo"],
    }
    if site["tier"] in ("heavy", "medium"):
        params["render"]    = "true"
        params["waitUntil"] = "networkidle0"
    if site["tier"] in ("heavy", "super_norender"):
        params["super"] = "true"

    start = time.time()

    for attempt in range(1, _502_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get("https://api.scrape.do", params=params)
            elapsed = time.time() - start

            if resp.status_code == 200:
                return {"html": resp.text, "status": 200, "elapsed": elapsed, "url": url}

            if resp.status_code == 502:
                if attempt < _502_MAX_RETRIES:
                    print(
                        f"{YELLOW}  [RETRY] 502 for {site['domain']} "
                        f"(attempt {attempt}/{_502_MAX_RETRIES}) — retrying in {_502_RETRY_DELAY:.0f}s{RESET}"
                    )
                    await asyncio.sleep(_502_RETRY_DELAY)
                    continue  # next attempt
                else:
                    print(
                        f"{RED}  [RETRY] 502 for {site['domain']} "
                        f"(attempt {attempt}/{_502_MAX_RETRIES}) — giving up{RESET}"
                    )
                    return {"html": None, "status": 502, "elapsed": elapsed, "url": url}

            # Any other non-200: fail immediately
            return {"html": None, "status": resp.status_code, "elapsed": elapsed, "url": url}

        except Exception as e:
            elapsed = time.time() - start
            if attempt < _502_MAX_RETRIES:
                print(
                    f"{YELLOW}  [RETRY] Exception for {site['domain']} "
                    f"(attempt {attempt}/{_502_MAX_RETRIES}): {e} — retrying in {_502_RETRY_DELAY:.0f}s{RESET}"
                )
                await asyncio.sleep(_502_RETRY_DELAY)
                continue
            return {"html": None, "status": 0, "elapsed": elapsed, "url": url, "error": str(e)}

    # Should never reach here
    return {"html": None, "status": 0, "elapsed": time.time() - start, "url": url, "error": "retry exhausted"}


# ── Test one site ──────────────────────────────────────────────────────────────

async def test_one(site: dict, semaphore: asyncio.Semaphore, timeout: int) -> dict:
    domain  = site["domain"]
    product = SITE_PRODUCTS.get(domain, "Sony WH-1000XM5")

    if site.get("skip"):
        return {
            "domain":   domain,
            "name":     site["name"],
            "geo":      site["geo"],
            "tier":     site["tier"],
            "product":  product,
            "verdict":  "SKIP",
            "status":   0,
            "items":    0,
            "matched":  0,
            "elapsed":  0,
            "error":    "marked skip in config",
        }

    async with semaphore:
        fetch  = await fetch_site(site, product, timeout)

    html    = fetch["html"]
    status  = fetch["status"]
    elapsed = fetch["elapsed"]

    if not html:
        return {
            "domain": domain, "name": site["name"], "geo": site["geo"],
            "tier": site["tier"], "product": product,
            "verdict": "FETCH_FAIL", "status": status,
            "items": 0, "matched": 0, "elapsed": elapsed,
            "error": fetch.get("error", f"HTTP {status}"),
        }

    # Parse
    try:
        items = parse_results(html, domain)
    except Exception as e:
        items = []

    # Match
    matched = 0
    if items:
        for item in items:
            item["site_name"] = site["name"]
            item["domain"]    = domain
            item["geo"]       = site["geo"]
        try:
            hits    = filter_matches(product, items, threshold=MATCH_THRESHOLD)
            matched = len(hits)
        except Exception:
            matched = 0

    if matched > 0:
        verdict = "OK"
    elif len(items) > 0:
        verdict = "PARSE_OK_NO_MATCH"
    else:
        verdict = "PARSE_FAIL"

    return {
        "domain": domain, "name": site["name"], "geo": site["geo"],
        "tier": site["tier"], "product": product,
        "verdict": verdict, "status": status,
        "items": len(items), "matched": matched,
        "elapsed": elapsed, "error": "",
    }


# ── Main ───────────────────────────────────────────────────────────────────────

async def main(geo_filter, tier_filter, concurrency, timeout):
    sites = SITES
    if geo_filter:
        sites = [s for s in sites if s["geo"] == geo_filter]
    if tier_filter:
        sites = [s for s in sites if s["tier"] == tier_filter]

    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}  BULK SITE HEALTH CHECK — Price Monitor{RESET}")
    print(f"{'='*80}")
    print(f"  Sites     : {len(sites)}")
    print(f"  Threshold : {MATCH_THRESHOLD}%  |  Concurrency: {concurrency}  |  Timeout: {timeout}s")
    print(f"  Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")

    semaphore = asyncio.Semaphore(concurrency)
    tasks     = [test_one(s, semaphore, timeout) for s in sites]

    results   = []
    completed = 0
    total     = len(tasks)

    # Run and print progress as each completes
    for coro in asyncio.as_completed(tasks):
        r = await coro
        results.append(r)
        completed += 1

        verdict = r["verdict"]
        if verdict == "OK":
            icon  = f"{GREEN}✓{RESET}"
            color = GREEN
        elif verdict == "SKIP":
            icon  = f"{DIM}−{RESET}"
            color = DIM
        elif verdict in ("PARSE_OK_NO_MATCH",):
            icon  = f"{YELLOW}~{RESET}"
            color = YELLOW
        else:
            icon  = f"{RED}✗{RESET}"
            color = RED

        name_str    = f"{r['name']:<28}"
        domain_str  = f"{DIM}{r['domain']:<38}{RESET}"
        verdict_str = f"{color}{verdict:<20}{RESET}"
        stats_str   = f"items={r['items']:<3} matched={r['matched']:<3} {r['elapsed']:.1f}s"
        err_str     = f"  {RED}{r['error']}{RESET}" if r["error"] else ""

        print(f"  [{completed:>2}/{total}] {icon} {name_str} {domain_str} {verdict_str} {stats_str}{err_str}")

    # ── Summary ────────────────────────────────────────────────────────────────
    ok           = [r for r in results if r["verdict"] == "OK"]
    parse_ok     = [r for r in results if r["verdict"] == "PARSE_OK_NO_MATCH"]
    fetch_fail   = [r for r in results if r["verdict"] == "FETCH_FAIL"]
    parse_fail   = [r for r in results if r["verdict"] == "PARSE_FAIL"]
    skipped      = [r for r in results if r["verdict"] == "SKIP"]

    print(f"\n{'='*80}")
    print(f"{BOLD}  SUMMARY{RESET}")
    print(f"{'='*80}")
    print(f"  {GREEN}✓ Working        : {len(ok)}{RESET}")
    print(f"  {YELLOW}~ Parse OK / No match : {len(parse_ok)}{RESET}")
    print(f"  {RED}✗ Fetch failed   : {len(fetch_fail)}{RESET}")
    print(f"  {RED}✗ Parse failed   : {len(parse_fail)}{RESET}")
    print(f"  {DIM}− Skipped        : {len(skipped)}{RESET}")

    if fetch_fail:
        print(f"\n  {BOLD}{RED}Fetch failures (likely Scrape.do / site issues):{RESET}")
        for r in sorted(fetch_fail, key=lambda x: x["domain"]):
            print(f"    {r['domain']:<40}  HTTP {r['status']}  {r['error']}")

    if parse_fail:
        print(f"\n  {BOLD}{YELLOW}Parse failures (selectors may need update):{RESET}")
        for r in sorted(parse_fail, key=lambda x: x["domain"]):
            print(f"    {r['domain']:<40}  {r['items']} items found, 0 parsed")

    if parse_ok:
        print(f"\n  {BOLD}{YELLOW}Fetched+Parsed but no match (check test product name):{RESET}")
        for r in sorted(parse_ok, key=lambda x: x["domain"]):
            print(f"    {r['domain']:<40}  {r['items']} items, product=\"{r['product']}\"")

    print(f"\n  Total time : {sum(r['elapsed'] for r in results if r['elapsed']):.1f}s  "
          f"(wall clock will be less due to concurrency)")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk site health check for all scraping sites")
    parser.add_argument("--geo",         default=None,  help="Filter by geo: au or nz")
    parser.add_argument("--tier",        default=None,  help="Filter by tier: light/medium/heavy")
    parser.add_argument("--concurrency", default=3,     type=int, help="Parallel requests (default: 3)")
    parser.add_argument("--timeout",     default=90,    type=int, help="Timeout per request in seconds (default: 90)")
    args = parser.parse_args()

    asyncio.run(main(args.geo, args.tier, args.concurrency, args.timeout))