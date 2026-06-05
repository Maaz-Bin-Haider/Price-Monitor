import asyncio, sys, os
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
import httpx, urllib.parse

async def save(product):
    query = urllib.parse.quote_plus(product)
    url = f"https://photogear.co.nz/search-results?search_query_adv={query}"
    params = {
        "token": settings.SCRAPE_DO_TOKEN,
        "url": url,
        "geoCode": "nz",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get("https://api.scrape.do", params=params)
        print(f"Status: {resp.status_code}  Size: {len(resp.text):,}")
        with open("photogear_rendered.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print("Saved to photogear_rendered.html")

asyncio.run(save("Sony ZV-1 Digital Vlogging Camera"))
