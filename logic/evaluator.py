def evaluate(
    product_name: str,
    target_price: float,
    all_site_results: list[dict],
) -> dict:
    """
    Deduplicate results per domain (highest match_score, tie-break by lower price),
    sort by price, identify items below target, return evaluation dict.
    """
    # Step 1 — Deduplicate per domain
    best_per_domain: dict[str, dict] = {}
    for item in all_site_results:
        domain = item.get("domain", "")
        existing = best_per_domain.get(domain)
        if existing is None:
            best_per_domain[domain] = item
        else:
            # Higher match_score wins; tie-break: lower price
            if item.get("match_score", 0) > existing.get("match_score", 0):
                best_per_domain[domain] = item
            elif item.get("match_score", 0) == existing.get("match_score", 0):
                if item.get("price", float("inf")) < existing.get("price", float("inf")):
                    best_per_domain[domain] = item

    deduplicated = list(best_per_domain.values())

    # Step 2 — Sort by price ascending
    deduplicated.sort(key=lambda x: x.get("price", float("inf")))

    # Step 3 — Filter below target
    below_target = [item for item in deduplicated if item.get("price", float("inf")) <= target_price]

    # Step 4 — Lowest
    lowest = deduplicated[0] if deduplicated else None

    # Step 5 — Return
    return {
        "results": deduplicated,
        "below_target": below_target,
        "lowest_price": lowest.get("price") if lowest else None,
        "lowest_site": lowest.get("site_name") if lowest else None,
        "lowest_link": lowest.get("link") if lowest else None,
        "should_alert": len(below_target) > 0,
    }


def evaluate_availability(
    product_name: str,
    all_site_results: list[dict],
) -> dict:
    """
    Like evaluate() but with no target price comparison.
    Deduplicates per domain (best match_score, tie-break lower price),
    sorts by price, and returns ALL results as 'available' sites.
    """
    # Step 1 — Deduplicate per domain
    best_per_domain: dict[str, dict] = {}
    for item in all_site_results:
        domain = item.get("domain", "")
        existing = best_per_domain.get(domain)
        if existing is None:
            best_per_domain[domain] = item
        else:
            if item.get("match_score", 0) > existing.get("match_score", 0):
                best_per_domain[domain] = item
            elif item.get("match_score", 0) == existing.get("match_score", 0):
                if item.get("price", float("inf")) < existing.get("price", float("inf")):
                    best_per_domain[domain] = item

    deduplicated = list(best_per_domain.values())

    # Step 2 — Sort by price ascending
    deduplicated.sort(key=lambda x: x.get("price", float("inf")))

    lowest = deduplicated[0] if deduplicated else None

    return {
        "results": deduplicated,
        "available_sites": deduplicated,   # all matched results = available
        "lowest_price": lowest.get("price") if lowest else None,
        "lowest_site": lowest.get("site_name") if lowest else None,
        "lowest_link": lowest.get("link") if lowest else None,
        "found": len(deduplicated) > 0,
    }
