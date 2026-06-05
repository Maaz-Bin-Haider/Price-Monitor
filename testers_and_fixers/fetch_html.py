# save in testers_and_fixers/ as fetch_html.py
import asyncio, sys, os
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import settings
import httpx, urllib.parse

async def save_html(domain, product):
    query = urllib.parse.quote_plus(product)
    url = f"https://themall.aucklandairport.co.nz/en/intl-duty-free/search/product?q={query}"
    params = {
        "token": settings.SCRAPE_DO_TOKEN,
        "url": url,
        "geoCode": "nz",
        "render": "true",
    }
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.get("https://api.scrape.do", params=params)
        with open("auckland_mall.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"Saved {len(resp.text):,} bytes to auckland_mall.html")

asyncio.run(save_html("themall.aucklandairport.co.nz", "Apple AirPods Pro"))