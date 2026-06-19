"""
bulk_site_check.py — Health check for all scraping sites (CLI wrapper).

The actual test logic lives in test_engine.py (shared with the web UI).
This script adds the CLI argument parsing, colour output, and summary
printing on top of that shared engine.

Run from the price_monitor root directory:
    python testers_and_fixers/bulk_site_check2.py

Options:
    --geo au          Only test AU sites
    --geo nz           Only test NZ sites
    --tier light       Only test light-tier sites
    --concurrency 3    How many sites to test in parallel (default: 3)
    --timeout 90       Scrape.do timeout in seconds (default: 90)
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from testers_and_fixers.test_engine import run_site_tests, select_sites, summarize

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
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


async def main(geo_filter, tier_filter, concurrency, timeout):
    sites = select_sites(geo_filter, tier_filter)

    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}  BULK SITE HEALTH CHECK — Price Monitor{RESET}")
    print(f"{'='*80}")
    print(f"  Sites     : {len(sites)}")
    print(f"  Threshold : {MATCH_THRESHOLD}%  |  Concurrency: {concurrency}  |  Timeout: {timeout}s")
    print(f"  Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")

    completed = 0
    total = len(sites)

    async def on_progress(results_so_far):
        nonlocal completed
        completed = len(results_so_far)
        r = results_so_far[-1]
        verdict = r["verdict"]
        if verdict == "OK":
            icon, color = f"{GREEN}✓{RESET}", GREEN
        elif verdict == "SKIP":
            icon, color = f"{DIM}−{RESET}", DIM
        elif verdict == "PARSE_OK_NO_MATCH":
            icon, color = f"{YELLOW}~{RESET}", YELLOW
        else:
            icon, color = f"{RED}✗{RESET}", RED

        name_str    = f"{r['name']:<28}"
        domain_str  = f"{DIM}{r['domain']:<38}{RESET}"
        verdict_str = f"{color}{verdict:<20}{RESET}"
        stats_str   = f"items={r['items']:<3} matched={r['matched']:<3} {r['elapsed']:.1f}s"
        err_str     = f"  {RED}{r['error']}{RESET}" if r["error"] else ""
        print(f"  [{completed:>2}/{total}] {icon} {name_str} {domain_str} {verdict_str} {stats_str}{err_str}")

    results = await run_site_tests(
        site_products=SITE_PRODUCTS,
        threshold=MATCH_THRESHOLD,
        geo_filter=geo_filter,
        tier_filter=tier_filter,
        concurrency=concurrency,
        timeout=timeout,
        on_progress=on_progress,
    )

    summary = summarize(results)
    fetch_fail = [r for r in results if r["verdict"] == "FETCH_FAIL"]
    parse_fail = [r for r in results if r["verdict"] == "PARSE_FAIL"]
    parse_ok   = [r for r in results if r["verdict"] == "PARSE_OK_NO_MATCH"]

    print(f"\n{'='*80}")
    print(f"{BOLD}  SUMMARY{RESET}")
    print(f"{'='*80}")
    print(f"  {GREEN}✓ Working        : {summary['ok']}{RESET}")
    print(f"  {YELLOW}~ Parse OK / No match : {summary['parse_ok_no_match']}{RESET}")
    print(f"  {RED}✗ Fetch failed   : {summary['fetch_fail']}{RESET}")
    print(f"  {RED}✗ Parse failed   : {summary['parse_fail']}{RESET}")
    print(f"  {DIM}− Skipped        : {summary['skipped']}{RESET}")

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

    print(f"\n  Total time : {summary['total_elapsed']:.1f}s  (wall clock will be less due to concurrency)")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk site health check for all scraping sites")
    parser.add_argument("--geo",         default=None,  help="Filter by geo: au or nz")
    parser.add_argument("--tier",        default=None,  help="Filter by tier: light/medium/heavy")
    parser.add_argument("--concurrency", default=3,     type=int, help="Parallel requests (default: 3)")
    parser.add_argument("--timeout",     default=90,    type=int, help="Timeout per request in seconds (default: 90)")
    args = parser.parse_args()

    asyncio.run(main(args.geo, args.tier, args.concurrency, args.timeout))
