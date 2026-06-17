import asyncio
import httpx
from config import settings

SCRAPE_DO_BASE = "https://api.scrape.do"

# Limit concurrent requests to stay within Scrape.do plan limits
# Free plan = 5 concurrent, paid plans can go higher
_semaphore = asyncio.Semaphore(5)

# Retry settings for 502 Bad Gateway responses
_502_MAX_RETRIES = 3        # number of sequential attempts before giving up
_502_RETRY_DELAY = 5.0      # seconds to wait between 502 retry attempts


async def fetch_page(url: str, tier: str, geo: str, wait_for: str = None) -> str | None:
    """Fetch a page via Scrape.do API. Returns HTML string or None on failure.

    On HTTP 502 (Bad Gateway) the request is retried up to _502_MAX_RETRIES
    times with a short delay between each attempt before giving up and
    returning None.  All other non-200 responses fail immediately.
    """
    params = {
        "token": settings.SCRAPE_DO_TOKEN,
        "url": url,
        "geoCode": geo,
    }
    if tier in ("heavy", "medium"):
        params["render"] = "true"
    if tier == "heavy":
        params["super"] = "true"
    # Give JS-heavy sites extra time to load dynamic content
    if tier in ("heavy", "medium"):
        params["waitUntil"] = "networkidle0"
    if wait_for:
        params["waitFor"] = wait_for

    async with _semaphore:
        for attempt in range(1, _502_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    response = await client.get(SCRAPE_DO_BASE, params=params)

                if response.status_code == 200:
                    return response.text

                if response.status_code == 502:
                    if attempt < _502_MAX_RETRIES:
                        print(
                            f"[SCRAPER] 502 from Scrape.do for {url} "
                            f"(attempt {attempt}/{_502_MAX_RETRIES}) — retrying in {_502_RETRY_DELAY}s"
                        )
                        await asyncio.sleep(_502_RETRY_DELAY)
                        continue  # next attempt
                    else:
                        print(
                            f"[SCRAPER] 502 from Scrape.do for {url} "
                            f"(attempt {attempt}/{_502_MAX_RETRIES}) — giving up"
                        )
                        return None

                # Any other non-200 status: fail immediately (no retry)
                print(f"[SCRAPER] Non-200 from Scrape.do for {url}: {response.status_code}")
                return None

            except Exception as e:
                print(f"[SCRAPER] Exception fetching {url} (attempt {attempt}/{_502_MAX_RETRIES}): {e}")
                # Network-level exceptions on the last attempt give up; otherwise retry
                if attempt < _502_MAX_RETRIES:
                    await asyncio.sleep(_502_RETRY_DELAY)
                    continue
                return None

    # Should never reach here, but satisfy the type checker
    return None


async def fetch_all(tasks: list[dict]) -> list[dict]:
    """
    Fire all Scrape.do requests with concurrency limit.
    Each task: {url, tier, geo, site, domain}
    Returns same list with 'html' key added (str or None).
    """
    async def _fetch_one(task: dict) -> dict:
        html = await fetch_page(task["url"], task["tier"], task["geo"], task.get("wait_for"))
        return {**task, "html": html}

    results = await asyncio.gather(*[_fetch_one(t) for t in tasks])
    return list(results)
