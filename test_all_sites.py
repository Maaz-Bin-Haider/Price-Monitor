"""
Full site accuracy test. Tests all 22 sites and produces a clear report.

Usage:
    python test_all_sites.py
    python test_all_sites.py --product "iPhone 16 Pro"
    python test_all_sites.py --product "Sony WH-1000XM5" --threshold 60
"""
import asyncio
import argparse
import sys
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from config import SITES
from scraper.client import fetch_page
from scraper.parsers import parse_results
from matcher.engine import filter_matches

# ── Config ────────────────────────────────────────────────────────────────
DEFAULT_PRODUCT   = "Starlink standard kit"
DEFAULT_THRESHOLD = 60   # lower than production so we see near-misses too

# ── ANSI colours ─────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"


async def test_site(site: dict, product: str, threshold: float) -> dict:
    import urllib.parse
    query = urllib.parse.quote_plus(product)
    url   = site["search_url"].format(query=query)

    result = {
        "name":    site["name"],
        "domain":  site["domain"],
        "geo":     site["geo"],
        "tier":    site["tier"],
        "url":     url,
        "status":  "unknown",
        "http_code": None,
        "html_size": 0,
        "raw_parsed": 0,
        "matched": [],
        "error":   None,
    }

    # Fetch
    try:
        import httpx
        from config import settings
        params = {
            "token":   settings.SCRAPE_DO_TOKEN,
            "url":     url,
            "geoCode": site["geo"],
        }
        if site["tier"] in ("heavy", "medium"):
            params["render"] = "true"
        if site["tier"] == "heavy":
            params["super"] = "true"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get("https://api.scrape.do", params=params)
            result["http_code"] = resp.status_code
            if resp.status_code != 200:
                result["status"] = "http_error"
                result["error"]  = f"HTTP {resp.status_code}"
                return result
            html = resp.text
            result["html_size"] = len(html)
    except Exception as e:
        result["status"] = "fetch_error"
        result["error"]  = str(e)[:80]
        return result

    # Parse
    try:
        raw = parse_results(html, site["domain"])
        result["raw_parsed"] = len(raw)
        for item in raw:
            item["site_name"] = site["name"]
            item["domain"]    = site["domain"]
            item["geo"]       = site["geo"]
    except Exception as e:
        result["status"] = "parse_error"
        result["error"]  = str(e)[:80]
        return result

    # Match
    try:
        matched = filter_matches(product, raw, threshold=threshold)
        result["matched"] = matched[:5]
    except Exception as e:
        result["error"] = f"match error: {str(e)[:60]}"

    # Status
    if result["matched"]:
        result["status"] = "ok"
    elif result["raw_parsed"] > 0:
        result["status"] = "parsed_no_match"
    elif result["html_size"] > 5000:
        result["status"] = "no_products_parsed"
    else:
        result["status"] = "empty_page"

    return result


async def run_all(product: str, threshold: float):
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  PRICE MONITOR — Site Accuracy Test{RESET}")
    print(f"  Product : {CYAN}{product}{RESET}")
    print(f"  Threshold: {threshold}%  |  Sites: {len(SITES)}")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{BOLD}{'='*70}{RESET}\n")

    # Run with concurrency limit of 5 (free plan)
    semaphore = asyncio.Semaphore(5)

    async def bounded(site):
        async with semaphore:
            return await test_site(site, product, threshold)

    tasks   = [bounded(s) for s in SITES]
    results = await asyncio.gather(*tasks)

    # ── Summary table ──────────────────────────────────────────────────
    ok            = [r for r in results if r["status"] == "ok"]
    parsed_nomatch= [r for r in results if r["status"] == "parsed_no_match"]
    no_parse      = [r for r in results if r["status"] == "no_products_parsed"]
    http_err      = [r for r in results if r["status"] == "http_error"]
    empty         = [r for r in results if r["status"] == "empty_page"]
    other         = [r for r in results if r["status"] in ("fetch_error","parse_error","unknown")]

    print(f"{BOLD}{'SITE':<28} {'GEO':<4} {'TIER':<7} {'STATUS':<20} {'PARSED':<8} {'MATCHED':<8} BEST RESULT{RESET}")
    print("─" * 110)

    for r in sorted(results, key=lambda x: (x["status"] != "ok", x["name"])):
        if r["status"] == "ok":
            colour = GREEN
            status_str = "✓ OK"
        elif r["status"] == "parsed_no_match":
            colour = YELLOW
            status_str = "~ parsed/no match"
        elif r["status"] == "no_products_parsed":
            colour = YELLOW
            status_str = "~ page ok/no parse"
        elif r["status"] == "http_error":
            colour = RED
            status_str = f"✗ {r['error']}"
        elif r["status"] == "empty_page":
            colour = RED
            status_str = "✗ empty page"
        else:
            colour = RED
            status_str = f"✗ {r['error'] or r['status']}"

        best = ""
        if r["matched"]:
            top = r["matched"][0]
            best = f"${top['price']:.2f}  {top['title'][:35]}  [{top['match_score']}%]"
        elif r["error"] and r["status"] not in ("http_error",):
            best = DIM + str(r["error"])[:50] + RESET

        print(
            f"{colour}{r['name']:<28}{RESET} "
            f"{r['geo']:<4} "
            f"{r['tier']:<7} "
            f"{colour}{status_str:<20}{RESET} "
            f"{r['raw_parsed']:<8} "
            f"{len(r['matched']):<8} "
            f"{best}"
        )

    # ── Detailed results for OK sites ─────────────────────────────────
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  DETAILED MATCHES (sites with results){RESET}")
    print(f"{BOLD}{'='*70}{RESET}\n")

    for r in results:
        if not r["matched"]:
            continue
        print(f"{GREEN}{BOLD}{r['name']}{RESET}  {DIM}({r['domain']}){RESET}")
        for i, m in enumerate(r["matched"][:3], 1):
            print(f"  {i}. ${m['price']:.2f}  [{m['match_score']}%]  {m['title'][:65]}")
            print(f"     {DIM}{m['link'][:90]}{RESET}")
        print()

    # ── Score ──────────────────────────────────────────────────────────
    print(f"{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  SUMMARY{RESET}")
    print(f"{'='*70}")
    print(f"  {GREEN}✓ Working (results found)  : {len(ok)}/{len(SITES)}{RESET}")
    print(f"  {YELLOW}~ Parsed but no match      : {len(parsed_nomatch)}/{len(SITES)}  (product may not be stocked){RESET}")
    print(f"  {YELLOW}~ Page fetched, not parsed : {len(no_parse)}/{len(SITES)}  (selector needs update){RESET}")
    print(f"  {RED}✗ HTTP error (4xx/5xx)     : {len(http_err)}/{len(SITES)}{RESET}")
    print(f"  {RED}✗ Empty/fetch error        : {len(empty) + len(other)}/{len(SITES)}{RESET}")

    if parsed_nomatch:
        print(f"\n  {YELLOW}Sites that fetched+parsed but found no match:{RESET}")
        for r in parsed_nomatch:
            print(f"    - {r['name']}  ({r['raw_parsed']} products parsed, none matched '{product}')")
        print(f"  {DIM}Tip: these sites are working — try a more common product to confirm.{RESET}")

    if no_parse:
        print(f"\n  {YELLOW}Sites with HTML but no products extracted:{RESET}")
        for r in no_parse:
            print(f"    - {r['name']}  (HTML: {r['html_size']:,} bytes)")
        print(f"  {DIM}Tip: run debug_scrape.py on these domains to update their CSS selectors.{RESET}")

    if http_err:
        print(f"\n  {RED}HTTP errors (site-side — not our problem):{RESET}")
        for r in http_err:
            print(f"    - {r['name']}  {r['error']}")

    print(f"\n  Score: {len(ok)}/{len(SITES)} sites returning matched results")
    print(f"{'='*70}\n")

    # Save results to file
    report_path = os.path.join(os.path.dirname(__file__), "test_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(f"{r['name']} | {r['status']} | parsed={r['raw_parsed']} | matched={len(r['matched'])}\n")
            for m in r["matched"][:3]:
                f.write(f"  ${m['price']:.2f} [{m['match_score']}%] {m['title']}\n")
                f.write(f"  {m['link']}\n")
            if r["error"]:
                f.write(f"  ERROR: {r['error']}\n")
            f.write("\n")
    print(f"  Full report saved to: {report_path}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test all 22 sites")
    parser.add_argument("--product",   default=DEFAULT_PRODUCT,   help="Product to search")
    parser.add_argument("--threshold", default=DEFAULT_THRESHOLD, type=float, help="Match threshold (default 60)")
    args = parser.parse_args()
    asyncio.run(run_all(args.product, args.threshold))
