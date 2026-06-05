from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    SCRAPE_DO_TOKEN: str = "your_scrape_do_token_here"
    DATABASE_URL: str = "sqlite:///./monitor.db"
    EMAIL_FROM: str = "your_email@gmail.com"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_PASSWORD: str = "your_app_password_here"
    SENDGRID_API_KEY: Optional[str] = None
    USE_SENDGRID: bool = False
    MATCH_THRESHOLD: float = 72.0
    SCHEDULE_DEFAULT_HOUR: int = 8
    SECRET_KEY: str = "change_this_to_a_random_32_char_hex_string"

    class Config:
        env_file = ".env"


settings = Settings()

SITES = [
    # ── HEAVY ────────────────────────────────────────────────────────
    {
        "name": "JB Hi-Fi AU",
        "domain": "jbhifi.com.au",
        "tier": "heavy",
        "geo": "au",
        "search_url": "https://www.jbhifi.com.au/search?q={query}",
    },
    {
        "name": "Harvey Norman AU",
        "domain": "harveynorman.com.au",
        "tier": "heavy",
        "geo": "au",
        "search_url": "https://www.harveynorman.com.au/catalogsearch/result/?q={query}",
    },
    {
        "name": "JB Hi-Fi NZ",
        "domain": "jbhifi.co.nz",
        "tier": "heavy",
        "geo": "nz",
        "search_url": "https://www.jbhifi.co.nz/search?q={query}",
    },
    {
        "name": "Harvey Norman NZ",
        "domain": "harveynorman.co.nz",
        "tier": "heavy",
        "geo": "nz",
        "search_url": "https://www.harveynorman.co.nz/index.php?subcats=Y&status=A&pshort=N&pfull=N&pname=Y&pkeywords=Y&search_performed=Y&q={query}&dispatch=products.search",
    },
    # ── MEDIUM ───────────────────────────────────────────────────────
    {
        "name": "Big W",
        "domain": "bigw.com.au",
        "tier": "medium",
        "geo": "au",
        "search_url": "https://www.bigw.com.au/search?q={query}",
    },
    {
        "name": "Officeworks",
        "domain": "officeworks.com.au",
        "tier": "light",
        "geo": "au",
        "search_url": "https://k535caawve-dsn.algolia.net/1/indexes/prod-product-wc-bestmatch-personal?query={query}&hitsPerPage=12&attributesToRetrieve=sku,name,price,seoPath&x-algolia-application-id=K535CAAWVE&x-algolia-api-key=8a831febe0110932cfa06ff0e2024b4f",
    },
    {
        "name": "The Good Guys",
        "domain": "thegoodguys.com.au",
        "tier": "medium",
        "geo": "au",
        "search_url": "https://www.thegoodguys.com.au/search?q={query}",
    },
    {
        "name": "Bunnings AU",
        "domain": "bunnings.com.au",
        "tier": "medium",
        "geo": "au",
        "search_url": "https://www.bunnings.com.au/search/products?q={query}",
    },
    {
        "name": "Costco AU",
        "domain": "costco.com.au",
        "tier": "medium",
        "geo": "au",
        "search_url": "https://www.costco.com.au/c/search?q={query}",
    },
    {
        "name": "Anaconda AU",
        "domain": "anacondastores.com",
        "tier": "medium",
        "geo": "au",
        "search_url": "https://www.anacondastores.com/en-au/search?q={query}",
    },
    {
        "name": "BCF",
        "domain": "bcf.com.au",
        "tier": "medium",
        "geo": "au",
        "search_url": "https://www.bcf.com.au/search?q={query}",
    },
    {
        "name": "Noelle Leeming",
        "domain": "noelleeming.co.nz",
        "tier": "medium",
        "geo": "nz",
        "search_url": "https://www.noelleeming.co.nz/search?q={query}",
    },
    {
        "name": "PB Tech",
        "domain": "pbtech.co.nz",
        "tier": "medium",
        "geo": "nz",
        "search_url": "https://www.pbtech.co.nz/search?q={query}",
    },
    {
        "name": "Bunnings NZ",
        "domain": "bunnings.co.nz",
        "tier": "medium",
        "geo": "nz",
        "search_url": "https://www.bunnings.co.nz/search/products?q={query}",
    },
    {
        "name": "Auckland Airport Mall",
        "domain": "themall.aucklandairport.co.nz",
        "tier": "medium",
        "geo": "nz",
        "search_url": "https://themall.aucklandairport.co.nz/en/intl-duty-free/search/product?q={query}",
    },
    # ── LIGHT ────────────────────────────────────────────────────────
    {
        "name": "Digi Direct",
        "domain": "digidirect.com.au",
        "tier": "medium",
        "geo": "au",
        "search_url": "https://www.digidirect.com.au/catalogsearch/result/?q={query}",
    },
    {
        "name": "Camera Pro",
        "domain": "camerapro.com.au",
        "tier": "medium",
        "geo": "au",
        "search_url": "https://www.camerapro.com.au/catalogsearch/result/?q={query}",
    },
    {
        "name": "Rubber Monkey AU",
        "domain": "rubbermonkey.com.au",
        "tier": "light",
        "geo": "au",
        "search_url": "https://www.rubbermonkey.com.au/Search?searchText={query}",
    },
    {
        "name": "Rubber Monkey NZ",
        "domain": "rubbermonkey.co.nz",
        "tier": "light",
        "geo": "nz",
        "search_url": "https://www.rubbermonkey.co.nz/Search?searchText={query}",
    },
    {
        "name": "Photo Gear",
        "domain": "photogear.co.nz",
        "tier": "medium",
        "geo": "nz",
        "search_url": "https://photogear.co.nz/search-results-page?q={query}",
        "cache_bust": True,
    },
    {
        "name": "Photo Warehouse",
        "domain": "photowarehouse.co.nz",
        "tier": "light",
        "geo": "au",
        "search_url": "https://www.photowarehouse.co.nz/shop/shop-by-product?searchfilter=Keyword~{query}&sort=relevant",
    },
    {
        "name": "Jacobs Digital",
        "domain": "jacobsdigital.co.nz",
        "tier": "light",
        "geo": "nz",
        "search_url": "https://www.jacobsdigital.co.nz/search?type=product&q={query}",
    },
]

SITES_BY_DOMAIN = {site["domain"]: site for site in SITES}
