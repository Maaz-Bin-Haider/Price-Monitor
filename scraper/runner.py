import time
import urllib.parse
from config import SITES
from scraper.client import fetch_all
from scraper.parsers import parse_results
from matcher.engine import filter_matches
from logic.evaluator import evaluate


async def run_search(
    job_id: int,
    product_name: str,
    target_price: float,
    selected_sites: list[str],
) -> dict:
    """
    Full price-search pipeline for a single watchlist job.
    Returns dict with: results, lowest_price, lowest_site, lowest_link,
                       below_target, should_alert, error_sites
    """
    # Step 1 — Filter SITES to only selected domains
    filtered_sites = [s for s in SITES if s["domain"] in selected_sites]

    if not filtered_sites:
        return {
            "results": [],
            "lowest_price": None,
            "lowest_site": None,
            "lowest_link": None,
            "below_target": [],
            "should_alert": False,
            "error_sites": [],
        }

    # Step 2 — Build tasks
    tasks = []
    for site in filtered_sites:
        query = urllib.parse.quote_plus(product_name)
        url = site["search_url"].format(query=query)
        # Cache bust for sites that use JS search widgets (Snize, Klevu etc)
        # Adds a unique timestamp so scrape.do never serves cached skeleton HTML
        if site.get("cache_bust"):
            url += f"&_ts={int(time.time())}"
        tasks.append({
            "url":       url,
            "tier":      site["tier"],
            "geo":       site["geo"],
            "site":      site["name"],
            "domain":    site["domain"],
            "wait_for":  site.get("waitFor"),   # optional CSS selector to wait for
        })

    # Step 3 — Fetch all concurrently via Scrape.do
    fetched = await fetch_all(tasks)

    # Step 4 — Parse results, attach site metadata, track errors
    all_items = []
    error_sites = []

    for result in fetched:
        domain = result["domain"]
        html = result.get("html")

        if html is None:
            error_sites.append(domain)
            continue

        parsed = parse_results(html, domain)

        # Attach site metadata to each parsed item
        for item in parsed:
            item["site_name"] = result["site"]
            item["domain"] = domain
            item["geo"] = result["geo"]

        all_items.extend(parsed)

    # Step 5 — Match: filter by product name similarity, top 3 per domain
    matched = filter_matches(product_name, all_items)

    # Keep top 3 per domain
    per_domain_count: dict[str, int] = {}
    top_matched = []
    for item in matched:
        domain = item["domain"]
        count = per_domain_count.get(domain, 0)
        if count < 3:
            top_matched.append(item)
            per_domain_count[domain] = count + 1

    # Step 6 — Evaluate
    evaluation = evaluate(product_name, target_price, top_matched)

    # Step 7 — Return unified result dict
    return {
        "results": evaluation["results"],
        "lowest_price": evaluation["lowest_price"],
        "lowest_site": evaluation["lowest_site"],
        "lowest_link": evaluation["lowest_link"],
        "below_target": evaluation["below_target"],
        "should_alert": evaluation["should_alert"],
        "error_sites": error_sites,
        "sites_checked": [t["domain"] for t in fetched if t.get("html") is not None],
    }


async def run_availability_search(
    job_id: int,
    product_name: str,
    selected_sites: list[str],
) -> dict:
    """
    Availability-scout pipeline — same as run_search but no target price.
    Returns dict with: results, available_sites, lowest_price, lowest_site,
                       lowest_link, found, error_sites, sites_checked
    """
    from logic.evaluator import evaluate_availability

    filtered_sites = [s for s in SITES if s["domain"] in selected_sites]

    if not filtered_sites:
        return {
            "results": [],
            "available_sites": [],
            "lowest_price": None,
            "lowest_site": None,
            "lowest_link": None,
            "found": False,
            "error_sites": [],
            "sites_checked": [],
        }

    tasks = []
    for site in filtered_sites:
        query = urllib.parse.quote_plus(product_name)
        url = site["search_url"].format(query=query)
        # Cache bust for sites that use JS search widgets
        if site.get("cache_bust"):
            url += f"&_ts={int(time.time())}"
        tasks.append({
            "url":       url,
            "tier":      site["tier"],
            "geo":       site["geo"],
            "site":      site["name"],
            "domain":    site["domain"],
            "wait_for":  site.get("waitFor"),   # optional CSS selector to wait for
        })

    fetched = await fetch_all(tasks)

    all_items = []
    error_sites = []

    for result in fetched:
        domain = result["domain"]
        html = result.get("html")
        if html is None:
            error_sites.append(domain)
            continue
        parsed = parse_results(html, domain)
        for item in parsed:
            item["site_name"] = result["site"]
            item["domain"] = domain
            item["geo"] = result["geo"]
        all_items.extend(parsed)

    matched = filter_matches(product_name, all_items)

    # Keep top 3 per domain
    per_domain_count: dict[str, int] = {}
    top_matched = []
    for item in matched:
        domain = item["domain"]
        count = per_domain_count.get(domain, 0)
        if count < 3:
            top_matched.append(item)
            per_domain_count[domain] = count + 1

    evaluation = evaluate_availability(product_name, top_matched)

    return {
        "results": evaluation["results"],
        "available_sites": evaluation["available_sites"],
        "lowest_price": evaluation["lowest_price"],
        "lowest_site": evaluation["lowest_site"],
        "lowest_link": evaluation["lowest_link"],
        "found": evaluation["found"],
        "error_sites": error_sites,
        "sites_checked": [t["domain"] for t in fetched if t.get("html") is not None],
    }
