"""
Single site tester. Fetches, parses and matches results for one site at a time.

Usage:
    python test_site.py
    python test_site.py --site jbhifi.com.au
    python test_site.py --site jbhifi.com.au --product "Sony WH-1000XM5"
    python test_site.py --site jbhifi.com.au --product "iPhone 16 Pro" --threshold 60
    python test_site.py --list
"""
import asyncio
import argparse
import sys
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import SITES, settings
from scraper.parsers import parse_results
from matcher.engine import filter_matches

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_PRODUCT   = "Sony WH-1000XM5"
DEFAULT_THRESHOLD = 60
DEFAULT_SITE      = "jbhifi.com.au"


def list_sites():
    """Print all available site domains."""
    print(f"\n{BOLD}Available Sites:{RESET}\n")
    au = [s for s in SITES if s["geo"] == "au"]
    nz = [s for s in SITES if s["geo"] == "nz"]

    print(f"  {BOLD}🇦🇺 Australia:{RESET}")
    for s in au:
        print(f"    {CYAN}{s['domain']:<35}{RESET} {DIM}{s['name']} ({s['tier']}){RESET}")

    print(f"\n  {BOLD}🇳🇿 New Zealand:{RESET}")
    for s in nz:
        print(f"    {CYAN}{s['domain']:<35}{RESET} {DIM}{s['name']} ({s['tier']}){RESET}")

    print(f"\n  Total: {len(SITES)} sites\n")


async def fetch_html(site: dict, product: str) -> tuple[str | None, str, int]:
    """
    Fetch the search page HTML via Scrape.do.
    Returns (html, url, http_status_code).
    """
    import urllib.parse
    import httpx

    query = urllib.parse.quote_plus(product)
    url   = site["search_url"].format(query=query)

    params = {
        "token":   settings.SCRAPE_DO_TOKEN,
        "url":     url,
        "geoCode": site["geo"],
    }
    if site["tier"] in ("heavy", "medium"):
        params["render"] = "true"
    if site["tier"] == "heavy":
        params["super"] = "true"
    if site["tier"] in ("heavy", "medium"):
        params["waitFor"] = "12000"

    print(f"\n  {DIM}Fetching: {url[:90]}{RESET}")
    print(f"  {DIM}Scrape.do params: tier={site['tier']} render={'true' if 'render' in params else 'false'} super={'true' if 'super' in params else 'false'}{RESET}\n")

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.get("https://api.scrape.do", params=params)
            return resp.text if resp.status_code == 200 else None, url, resp.status_code
    except Exception as e:
        print(f"  {RED}Fetch error: {e}{RESET}")
        return None, url, 0


def print_separator(char="─", width=80):
    print(char * width)


async def test_site(domain: str, product: str, threshold: float, raw_mode: bool = False):
    """
    Full test pipeline for a single site:
    1. Fetch HTML via Scrape.do
    2. Parse results
    3. Match against product query
    4. Print detailed report
    """

    # Find site config
    site = next((s for s in SITES if s["domain"] == domain), None)
    if not site:
        print(f"\n{RED}Site '{domain}' not found. Run with --list to see all sites.{RESET}\n")
        sys.exit(1)

    # ── Header ────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}  SINGLE SITE TESTER — Price Monitor{RESET}")
    print(f"{'='*80}")
    print(f"  Site     : {CYAN}{site['name']}{RESET}  {DIM}({domain}){RESET}")
    print(f"  Geo      : {site['geo'].upper()}   Tier: {site['tier']}")
    print(f"  Product  : {CYAN}{product}{RESET}")
    print(f"  Threshold: {threshold}%")
    print(f"  Time     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}")

    # ── Step 1: Fetch ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}STEP 1 — Fetching page{RESET}")
    print_separator()

    start = asyncio.get_event_loop().time()
    html, url, status_code = await fetch_html(site, product)
    elapsed = asyncio.get_event_loop().time() - start

    print(f"  URL        : {url[:85]}")
    print(f"  HTTP Status: ", end="")
    if status_code == 200:
        print(f"{GREEN}{status_code} OK{RESET}")
    else:
        print(f"{RED}{status_code}{RESET}")

    print(f"  Time       : {elapsed:.1f}s")
    print(f"  HTML size  : ", end="")

    if html is None:
        print(f"{RED}No HTML received{RESET}")
        print(f"\n{RED}✗ Cannot continue — fetch failed.{RESET}\n")
        return

    size = len(html)
    size_str = f"{size:,} bytes ({size/1024:.1f} KB)"
    if size < 5000:
        print(f"{RED}{size_str}  ← very small, page may be empty or blocked{RESET}")
    elif size < 20000:
        print(f"{YELLOW}{size_str}  ← small, may be missing JS-rendered content{RESET}")
    else:
        print(f"{GREEN}{size_str}{RESET}")

    # Raw HTML snippet (first 500 chars) for debugging
    if raw_mode:
        print(f"\n  {BOLD}Raw HTML preview (first 800 chars):{RESET}")
        print_separator("·")
        snippet = html[:800].replace("\n", " ").replace("\r", "")
        print(f"  {DIM}{snippet}{RESET}")
        print_separator("·")

    # ── Step 2: Parse ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}STEP 2 — Parsing results{RESET}")
    print_separator()

    try:
        raw_items = parse_results(html, domain)
    except Exception as e:
        print(f"  {RED}Parser error: {e}{RESET}")
        raw_items = []

    print(f"  Parser     : {site.get('_type', 'auto-detected')}")
    print(f"  Items found: ", end="")

    if len(raw_items) == 0:
        print(f"{RED}0  ← parser returned nothing{RESET}")
        print(f"\n  {YELLOW}Possible reasons:{RESET}")
        print(f"    - Site changed its HTML structure (selectors need update)")
        print(f"    - Product not in stock / no results page")
        print(f"    - JS-rendered content not captured (tier may need upgrading)")
        print(f"    - Site is blocking the scraper")
    elif len(raw_items) < 3:
        print(f"{YELLOW}{len(raw_items)}  ← few results, page may be partially rendered{RESET}")
    else:
        print(f"{GREEN}{len(raw_items)}{RESET}")

    # Show all raw parsed items
    if raw_items:
        print(f"\n  {BOLD}All {len(raw_items)} parsed items (before matching):{RESET}")
        print_separator("·")
        for i, item in enumerate(raw_items, 1):
            title = item.get("title", "—")
            price = item.get("price")
            link  = item.get("link", "")
            price_str = f"${price:.2f}" if price else "no price"
            print(f"  {DIM}{i:>2}.{RESET} {price_str:<10} {title[:60]}")
            if link:
                print(f"       {DIM}{link[:75]}{RESET}")
        print_separator("·")

    # ── Step 3: Match ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}STEP 3 — Matching against '{product}'{RESET}")
    print_separator()
    print(f"  Threshold  : {threshold}%")

    if not raw_items:
        print(f"  {YELLOW}Skipped — no items to match.{RESET}")
    else:
        # Attach site metadata (same as runner.py does)
        for item in raw_items:
            item["site_name"] = site["name"]
            item["domain"]    = domain
            item["geo"]       = site["geo"]

        try:
            matched = filter_matches(product, raw_items, threshold=threshold)
        except Exception as e:
            print(f"  {RED}Match error: {e}{RESET}")
            matched = []

        print(f"  Matched    : ", end="")
        if len(matched) == 0:
            print(f"{RED}0  ← no items passed the threshold{RESET}")
            print(f"\n  {YELLOW}Top scores from unmatched items:{RESET}")
            # Show top scores even for non-matching items to help with threshold tuning
            from matcher.engine import score as compute_score
            scored_all = []
            for item in raw_items:
                s = compute_score(product, item.get("title", ""))
                scored_all.append((s, item))
            scored_all.sort(key=lambda x: x[0], reverse=True)
            print_separator("·")
            for s, item in scored_all[:8]:
                bar   = "█" * int(s / 10) + "░" * (10 - int(s / 10))
                color = GREEN if s >= threshold else (YELLOW if s >= threshold * 0.75 else RED)
                print(f"  {color}[{bar}] {s:5.1f}%{RESET}  ${item.get('price', 0):.2f}  {item.get('title', '')[:55]}")
            print_separator("·")
            print(f"\n  {DIM}Tip: if these look like valid results, lower --threshold (currently {threshold}){RESET}")
        else:
            print(f"{GREEN}{len(matched)}{RESET}")

            # ── Matched results ────────────────────────────────────────────
            print(f"\n  {BOLD}Matched results (sorted by score):{RESET}")
            print_separator("·")
            for i, m in enumerate(matched, 1):
                score_val = m.get("match_score", 0)
                bar       = "█" * int(score_val / 10) + "░" * (10 - int(score_val / 10))
                color     = GREEN if score_val >= 80 else YELLOW
                print(f"\n  {BOLD}{i}.{RESET} {color}[{bar}] {score_val}%{RESET}")
                print(f"     Title : {m.get('title', '—')[:70]}")
                print(f"     Price : {GREEN}${m.get('price', 0):.2f}{RESET}")
                print(f"     Link  : {DIM}{m.get('link', '—')[:80]}{RESET}")
            print_separator("·")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}  SUMMARY{RESET}")
    print(f"{'='*80}")
    print(f"  Fetched    : {'✓' if html else '✗'}  HTTP {status_code}  ({elapsed:.1f}s)")
    print(f"  Parsed     : {len(raw_items)} items")

    if raw_items and 'matched' in dir():
        print(f"  Matched    : {len(matched)} items above {threshold}% threshold")
        if matched:
            best = matched[0]
            print(f"  Best match : ${best['price']:.2f}  [{best['match_score']}%]  {best['title'][:50]}")
            print(f"  Best link  : {best['link'][:80]}")
            verdict = f"{GREEN}✓ WORKING{RESET}"
        else:
            verdict = f"{YELLOW}~ FETCH+PARSE OK — no matches (try lower threshold or different product){RESET}"
    elif raw_items:
        verdict = f"{YELLOW}~ FETCH+PARSE OK — matching skipped{RESET}"
    elif html and len(html) > 5000:
        verdict = f"{YELLOW}~ PAGE FETCHED — parser returned nothing (selectors may need update){RESET}"
    else:
        verdict = f"{RED}✗ FAILED — could not fetch or page was empty{RESET}"

    print(f"\n  Verdict    : {verdict}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test a single site — fetch, parse and match results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_site.py --list
  python test_site.py --site jbhifi.com.au
  python test_site.py --site harveynorman.com.au --product "Samsung 65 inch TV"
  python test_site.py --site jbhifi.com.au --product "iPhone 16 Pro" --threshold 55
  python test_site.py --site camerapro.com.au --product "Canon EOS R5" --raw
        """
    )
    parser.add_argument("--site",      default=DEFAULT_SITE,      help=f"Site domain to test (default: {DEFAULT_SITE})")
    parser.add_argument("--product",   default=DEFAULT_PRODUCT,   help=f"Product to search (default: {DEFAULT_PRODUCT})")
    parser.add_argument("--threshold", default=DEFAULT_THRESHOLD, type=float, help=f"Match threshold 0-100 (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--list",      action="store_true",        help="List all available site domains and exit")
    parser.add_argument("--raw",       action="store_true",        help="Show raw HTML preview (first 800 chars) for debugging")
    args = parser.parse_args()

    if args.list:
        list_sites()
        sys.exit(0)

    asyncio.run(test_site(args.site, args.product, args.threshold, raw_mode=args.raw))