import asyncio
import httpx
from config import settings

SCRAPE_DO_BASE = "https://api.scrape.do"

# Limit concurrent requests to stay within Scrape.do plan limits
# Free plan = 5 concurrent, paid plans can go higher
_semaphore = asyncio.Semaphore(5)


async def fetch_page(url: str, tier: str, geo: str) -> str | None:
    """Fetch a page via Scrape.do API. Returns HTML string or None on failure."""
    params = {
        "token": settings.SCRAPE_DO_TOKEN,
        "url": url,
        "geoCode": geo,
    }
    if tier in ("heavy", "medium"):
        params["waitFor"] = "5000"
        params["render"] = "true"
    if tier == "heavy":
        params["super"] = "true"

    async with _semaphore:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(SCRAPE_DO_BASE, params=params)
                if response.status_code == 200:
                    return response.text
                else:
                    print(f"[SCRAPER] Non-200 from Scrape.do for {url}: {response.status_code}")
                    return None
        except Exception as e:
            print(f"[SCRAPER] Exception fetching {url}: {e}")
            return None


async def fetch_all(tasks: list[dict]) -> list[dict]:
    """
    Fire all Scrape.do requests with concurrency limit.
    Each task: {url, tier, geo, site, domain}
    Returns same list with 'html' key added (str or None).
    """
    async def _fetch_one(task: dict) -> dict:
        html = await fetch_page(task["url"], task["tier"], task["geo"])
        return {**task, "html": html}

    results = await asyncio.gather(*[_fetch_one(t) for t in tasks])
    return list(results)
