"""
test_engine.py — Reusable site health-check engine.

This is the importable core extracted from bulk_site_check2.py, with all
printing/argparse removed so it can be driven from both the CLI script and
the web UI. Same retry-on-502 fetch logic, same parse + match pipeline.
"""

import asyncio
import time
import urllib.parse
from typing import Optional

import httpx

from config import SITES, settings
from scraper.parsers import parse_results
from matcher.engine import filter_matches

_502_MAX_RETRIES = 3
_502_RETRY_DELAY = 5.0

DEFAULT_TEST_PRODUCT = "Sony WH-1000XM5"


async def fetch_site(site: dict, product: str, timeout: int) -> dict:
    """Fetch one site via Scrape.do, retrying up to 3x on 502."""
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
                    await asyncio.sleep(_502_RETRY_DELAY)
                    continue
                return {"html": None, "status": 502, "elapsed": elapsed, "url": url}

            return {"html": None, "status": resp.status_code, "elapsed": elapsed, "url": url}

        except Exception as e:
            elapsed = time.time() - start
            if attempt < _502_MAX_RETRIES:
                await asyncio.sleep(_502_RETRY_DELAY)
                continue
            return {"html": None, "status": 0, "elapsed": elapsed, "url": url, "error": str(e)}

    return {"html": None, "status": 0, "elapsed": time.time() - start, "url": url, "error": "retry exhausted"}


async def test_one_site(site: dict, product: str, threshold: float,
                         semaphore: asyncio.Semaphore, timeout: int) -> dict:
    """Test a single site: fetch → parse → match. Returns a result dict."""
    domain = site["domain"]

    if site.get("skip"):
        return {
            "domain": domain, "name": site["name"], "geo": site["geo"],
            "tier": site["tier"], "product": product,
            "verdict": "SKIP", "status": 0,
            "items": 0, "matched": 0, "elapsed": 0,
            "error": "marked skip in config",
            "sample_items": [],
        }

    async with semaphore:
        fetch = await fetch_site(site, product, timeout)

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
            "sample_items": [],
        }

    try:
        items = parse_results(html, domain)
    except Exception:
        items = []

    matched_items = []
    if items:
        for item in items:
            item["site_name"] = site["name"]
            item["domain"]    = domain
            item["geo"]       = site["geo"]
        try:
            matched_items = filter_matches(product, items, threshold=threshold)
        except Exception:
            matched_items = []

    if matched_items:
        verdict = "OK"
    elif len(items) > 0:
        verdict = "PARSE_OK_NO_MATCH"
    else:
        verdict = "PARSE_FAIL"

    # Keep a small sample of matched items for the results UI (title + price + url)
    sample = []
    for it in matched_items[:5]:
        sample.append({
            "title": it.get("title", ""),
            "price": it.get("price"),
            "url":   it.get("url", ""),
        })

    return {
        "domain": domain, "name": site["name"], "geo": site["geo"],
        "tier": site["tier"], "product": product,
        "verdict": verdict, "status": status,
        "items": len(items), "matched": len(matched_items), "elapsed": elapsed,
        "error": "",
        "sample_items": sample,
    }


def select_sites(
    geo_filter: Optional[str] = None,
    tier_filter: Optional[str] = None,
    selected_domains: Optional[list[str]] = None,
) -> list[dict]:
    sites = SITES
    if selected_domains is not None:
        domain_set = set(selected_domains)
        sites = [s for s in sites if s["domain"] in domain_set]
    if geo_filter:
        sites = [s for s in sites if s["geo"] == geo_filter]
    if tier_filter:
        sites = [s for s in sites if s["tier"] == tier_filter]
    return sites


async def run_site_tests(
    site_products: dict,
    threshold: float = 50.0,
    geo_filter: Optional[str] = None,
    tier_filter: Optional[str] = None,
    selected_domains: Optional[list[str]] = None,
    concurrency: int = 3,
    timeout: int = 90,
    on_progress=None,
) -> list[dict]:
    """
    Run the full test suite.

    site_products:    {domain: product_name} — falls back to DEFAULT_TEST_PRODUCT
                       for any selected site not present in this dict.
    selected_domains: if provided, only these exact domains are tested
                       (takes priority over geo_filter/tier_filter, which
                       can still be combined to further narrow the set).
    on_progress:       optional async callback(results_so_far: list[dict])
                       called after every site completes — used to persist
                       live progress.
    """
    sites = select_sites(geo_filter, tier_filter, selected_domains)
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        test_one_site(
            site,
            site_products.get(site["domain"], DEFAULT_TEST_PRODUCT),
            threshold,
            semaphore,
            timeout,
        )
        for site in sites
    ]

    results = []
    for coro in asyncio.as_completed(tasks):
        r = await coro
        results.append(r)
        if on_progress:
            await on_progress(list(results))

    return results


def summarize(results: list[dict]) -> dict:
    """Build summary counts + total elapsed time from a results list."""
    ok         = [r for r in results if r["verdict"] == "OK"]
    parse_ok   = [r for r in results if r["verdict"] == "PARSE_OK_NO_MATCH"]
    fetch_fail = [r for r in results if r["verdict"] == "FETCH_FAIL"]
    parse_fail = [r for r in results if r["verdict"] == "PARSE_FAIL"]
    skipped    = [r for r in results if r["verdict"] == "SKIP"]
    return {
        "ok": len(ok), "parse_ok_no_match": len(parse_ok),
        "fetch_fail": len(fetch_fail), "parse_fail": len(parse_fail),
        "skipped": len(skipped), "total": len(results),
        "total_elapsed": sum(r["elapsed"] for r in results if r.get("elapsed")),
    }
