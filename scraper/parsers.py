"""
Parsers for all 22 AU/NZ retail sites.
Built from direct HTML analysis of each site's actual structure.
"""
import re, json
from urllib.parse import unquote
from bs4 import BeautifulSoup

SITE_PARSERS = {
    "jbhifi.com.au":         {"_type": "shopify",       "base": "https://www.jbhifi.com.au"},
    "jbhifi.co.nz":          {"_type": "shopify",       "base": "https://www.jbhifi.co.nz"},
    # jacobsdigital uses Boost Commerce (bc-sf-filter) — called directly as a JSON API
    "thegoodguys.com.au":    {"_type": "goodguys"},
    "harveynorman.com.au":   {"_type": "harveynorman",  "base": "https://www.harveynorman.com.au"},
    "harveynorman.co.nz":    {"_type": "cscart",        "base": "https://www.harveynorman.co.nz"},
    "bigw.com.au":           {"_type": "bigw",          "base": "https://www.bigw.com.au"},
    "bunnings.com.au":       {"_type": "bunnings",      "base": "https://www.bunnings.com.au"},
    "bunnings.co.nz":        {"_type": "bunnings",      "base": "https://www.bunnings.co.nz"},
    "officeworks.com.au":    {"_type": "algolia",       "base": "https://www.officeworks.com.au"},
    "costco.com.au":         {"_type": "costco",        "base": "https://www.costco.com.au"},
    "anacondastores.com":    {"_type": "anaconda",      "base": "https://www.anacondastores.com"},
    "bcf.com.au":            {"_type": "bcf",           "base": "https://www.bcf.com.au"},
    "noelleeming.co.nz":     {"_type": "noelleeming",   "base": "https://www.noelleeming.co.nz"},
    "pbtech.co.nz":          {"_type": "pbtech",        "base": "https://www.pbtech.co.nz"},
    "themall.aucklandairport.co.nz": {"_type": "auckland_mall", "base": "https://themall.aucklandairport.co.nz"},
    "digidirect.com.au":     {"_type": "magento",       "base": "https://www.digidirect.com.au"},
    "camerapro.com.au":      {"_type": "magento",       "base": "https://www.camerapro.com.au"},
    "rubbermonkey.com.au":   {"_type": "rubbermonkey",  "base": "https://www.rubbermonkey.com.au"},
    "rubbermonkey.co.nz":    {"_type": "rubbermonkey",  "base": "https://www.rubbermonkey.co.nz"},
    "photogear.co.nz":       {"_type": "klevu",        "base": "https://photogear.co.nz"},
    "photowarehouse.co.nz":  {"_type": "photowarehouse", "base": "https://www.photowarehouse.co.nz"},
    "jacobsdigital.co.nz":   {"_type": "boostcommerce", "base": "https://www.jacobsdigital.co.nz"},
}


def clean_price(raw) -> float | None:
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(raw).strip())
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = parts[0] + "." + parts[1]
    if not cleaned or cleaned == ".":
        return None
    try:
        v = float(cleaned)
        return v if v > 0 else None
    except ValueError:
        return None


def abs_url(href: str, base: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http"):
        return href
    return base + (href if href.startswith("/") else "/" + href)


# ── Shopify JSON (JB Hi-Fi, Jacobs Digital) ───────────────────────────────
def _shopify(html, base, **_):
    pat = (r'\{"id":\d+,"gid":"[^"]*","vendor":"[^"]*","type":"[^"]*",'
           r'"handle":"([^"]+)","variants":\[\{"id":\d+,"price":(\d+),"name":"([^"]+)"')
    results = []
    for handle, cents, name in re.findall(pat, html):
        try:
            results.append({"title": name, "price": int(cents)/100,
                             "link": f"{base}/products/{handle}"})
        except Exception:
            continue
    return results


# ── The Good Guys (React — stable data-testid selectors) ──────────────────
def _goodguys(html, **_):
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.find_all(attrs={"data-testid": "product-card"})
        if not cards:
            cards = soup.select("article[class*='_card']")
        for card in cards[:12]:
            a = card.find("a", attrs={"aria-label": True}) or card.find("a")
            if not a:
                continue
            title = a.get("aria-label", "").replace("View details for ", "").strip()
            if not title:
                title = a.get_text(strip=True)
            href = abs_url(a.get("href", ""), "https://www.thegoodguys.com.au")
            pel = card.find(attrs={"data-testid": "product-card-price-section-price"})
            if not pel:
                pel = card.select_one("[class*='_productPrice']")
            card_text = (pel or card).get_text(" ")
            prices = re.findall(r"[$]\s*([0-9,]+(?:[.][0-9]+)?)", card_text)
            price = float(prices[0].replace(",", "")) if prices else None
            if title and price and href:
                results.append({"title": title, "price": price, "link": href})
    except Exception as e:
        print(f"[PARSER] goodguys: {e}")
    return results


# ── Harvey Norman (GelBrick React components) ─────────────────────────────
def _harveynorman(html, base, **_):
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for card in soup.find_all(attrs={"data-testid": re.compile(r"^product-card_")})[:12]:
            name_a = card.find("a", class_=re.compile("sf-product-card__name__link"))
            if not name_a:
                continue
            title = name_a.get_text(strip=True)
            href  = abs_url(name_a.get("href",""), base)
            # Price: span structure is ['$', '278', 'SAVE $70']
            # Take the second span (numeric part) from the price device
            price_div = card.find(class_=re.compile("sf-price-device-list"))
            price = None
            if price_div:
                spans = price_div.find_all("span")
                for sp in spans:
                    txt = sp.get_text(strip=True)
                    # Skip '$', 'SAVE $X' — take standalone number
                    if re.match(r'^\d[\d,]*(?:\.\d+)?$', txt):
                        price = clean_price(txt)
                        break
            if not price:
                # Fallback: find largest price in card (actual price > SAVE amount)
                all_prices = [clean_price(p) for p in
                              re.findall(r'\$\s*([\d,]+(?:\.\d+)?)', card.get_text())]
                valid = [p for p in all_prices if p and p > 5]
                price = max(valid) if valid else None
            if title and href and price:
                results.append({"title": title, "price": price, "link": href})
    except Exception as e:
        print(f"[PARSER] harveynorman: {e}")
    return results


# ── Bunnings (Next.js — name+route in __NEXT_DATA__, price from CSS) ──────
def _bunnings(html, base, **_):
    results = []
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not nd:
        return results
    raw = nd.group(1)

    name_url = re.findall(
        r'"name"\s*:\s*"([^"]{5,150})"[^}]{0,600}?"productroutingurl"\s*:\s*"([^"]+)"', raw)

    # Get prices from the rendered CSS (p.ebtUXu or sc-bbcf7fe4 class)
    try:
        soup = BeautifulSoup(html, "lxml")
        containers = soup.find_all(attrs={"data-testid": "productTileContainer"})
        prices_css = []
        for ct in containers:
            m = re.search(r'\$\s*([\d,]+(?:\.\d+)?)', ct.get_text())
            prices_css.append(clean_price(m.group(1).replace(",","")) if m else None)
    except Exception:
        prices_css = []

    for i, (name, route) in enumerate(name_url[:12]):
        price = prices_css[i] if i < len(prices_css) else None
        if not price:
            # Try JSON context around this product
            idx = raw.find(f'"name":"{name}"')
            if idx > 0:
                chunk = raw[max(0, idx-100):idx+300]
                m = re.search(r'"price"\s*:\s*"?(\d+\.?\d*)"?', chunk)
                if m:
                    price = float(m.group(1))
        if name and route and price:
            results.append({"title": name, "price": price, "link": abs_url(route, base)})
    return results


# ── Big W (Next.js shell — products via client API, parse what we can) ────
def _bigw(html, base, **_):
    """Big W renders products entirely client-side from their API.
    The 100KB HTML is just a shell. We attempt CSS extraction as fallback."""
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        # Try any product tiles rendered
        for card in soup.select("div[data-testid*='product'], article[class*='product'], "
                                "div[class*='ProductTile'], li[class*='product-item']")[:10]:
            name_el = card.select_one("h3, h2, [class*='title'], [class*='name']")
            price_el = card.select_one("[class*='price'], [class*='Price']")
            link_el  = card.select_one("a")
            title = name_el.get_text(strip=True) if name_el else ""
            price = clean_price(price_el.get_text() if price_el else "")
            href  = abs_url(link_el.get("href","") if link_el else "", base)
            if title and price and href:
                results.append({"title": title, "price": price, "link": href})
    except Exception:
        pass
    return results


# ── Officeworks (Next.js with products in __NEXT_DATA__) ──────────────────
def _nextdata(html, base, **_):
    results = []
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not nd:
        return results
    raw = nd.group(1)
    try:
        data = json.loads(raw)

        def walk(obj, depth=0):
            if depth > 12 or results:
                return
            if isinstance(obj, list) and len(obj) >= 2:
                f = obj[0]
                if isinstance(f, dict):
                    if (set(f) & {'name','title','displayName','productName'} and
                            set(f) & {'price','salePrice','currentPrice','was','now','priceValue'}):
                        for item in obj[:12]:
                            try:
                                name = (item.get('name') or item.get('title') or
                                        item.get('displayName') or item.get('productName',''))
                                praw = (item.get('price') or item.get('salePrice') or
                                        item.get('currentPrice') or item.get('now') or
                                        item.get('priceValue', 0))
                                url  = (item.get('url') or item.get('href') or
                                        item.get('slug') or item.get('urlPath') or '')
                                p = clean_price(str(praw))
                                if name and p and p > 0:
                                    results.append({"title": str(name), "price": p,
                                                    "link": abs_url(str(url), base) if url else base})
                            except Exception:
                                continue
                        return
            if isinstance(obj, dict):
                for v in obj.values():
                    walk(v, depth+1)
            elif isinstance(obj, list):
                for v in obj[:5]:
                    walk(v, depth+1)
        walk(data)
    except Exception:
        pass
    if results:
        return results
    # Regex fallback
    seen = set()
    pat = (r'"(?:name|title|displayName)"\s*:\s*"([^"]{5,150})"'
           r'[^}]{0,400}?"(?:price|salePrice|currentPrice)"\s*:\s*"?(\d+\.?\d*)"?'
           r'[^}]{0,400}?"(?:url|href|slug|urlPath)"\s*:\s*"(/[^"]{3,100})"')
    for name, price_raw, url in re.findall(pat, raw[:2000000], re.DOTALL):
        if name in seen:
            continue
        seen.add(name)
        p = clean_price(price_raw)
        if name and p and p > 0:
            results.append({"title": name, "price": p, "link": abs_url(url, base)})
    return results


# ── Costco AU (Angular app — fully client-side, minimal extraction) ────────
def _costco(html, base, **_):
    """Costco renders via Angular. Try basic CSS extraction."""
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for card in soup.select("div[automation-id='productListItem'], "
                                "div[class*='product-list-item'], "
                                "div[class*='ProductCard']")[:10]:
            name_el = card.find(attrs={"automation-id": re.compile("name|description|title", re.I)})
            if not name_el:
                name_el = card.find(class_=re.compile("description|product-name|title"))
            price_el = card.find(attrs={"automation-id": re.compile("price", re.I)})
            if not price_el:
                price_el = card.find(class_=re.compile("price"))
            link_el = card.find("a")
            title = name_el.get_text(strip=True) if name_el else ""
            price = clean_price(price_el.get_text() if price_el else "")
            href  = abs_url(link_el.get("href","") if link_el else "", base)
            if title and price and href:
                results.append({"title": title, "price": price, "link": href})
    except Exception:
        pass
    return results


# ── Anaconda (card-link pattern) ──────────────────────────────────────────
def _anaconda(html, base, **_):
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for card in soup.find_all("a", class_="card-link")[:12]:
            href = abs_url(card.get("href",""), base)
            title_el = card.find(class_=re.compile("card-title|card-headline"))
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                text = card.get_text(" ", strip=True)
                m = re.match(r'^(.+?)\s*(?:FULL PRICE|SALE|WAS|\$)', text)
                title = m.group(1).strip() if m else text[:60]
            m = re.search(r'\$\s*([\d,]+(?:\.\d+)?)', card.get_text(" "))
            price = float(m.group(1).replace(",","")) if m else None
            if title and price and href:
                results.append({"title": title, "price": price, "link": href})
    except Exception as e:
        print(f"[PARSER] anaconda: {e}")
    return results


# ── BCF (product-tile with data-gtm JSON) ────────────────────────────────
def _bcf(html, base, **_):
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for tile in soup.find_all("div", class_="product-tile")[:12]:
            # Try data-gtm JSON
            try:
                gtm = json.loads(unquote(tile.get("data-gtm","{}")))
                items = gtm.get("ecommerce",{}).get("items",[])
                if items:
                    name  = items[0].get("item_name","")
                    price = items[0].get("price")
                    a = tile.find("a", class_=re.compile("thumb-link|name-link"))
                    href = abs_url(a.get("href","") if a else "", base)
                    if name and price and href:
                        results.append({"title": name, "price": float(price), "link": href})
                    continue
            except Exception:
                pass
            # CSS fallback
            name_el  = tile.find(class_=re.compile("product-name"))
            price_el = tile.find(class_=re.compile("product-sales-price|member-price"))
            a        = tile.find("a", class_=re.compile("thumb-link|name-link"))
            title = name_el.get_text(strip=True) if name_el else ""
            price = clean_price(price_el.get_text() if price_el else "")
            href  = abs_url(a.get("href","") if a else "", base)
            if title and price and href:
                results.append({"title": title, "price": price, "link": href})
    except Exception as e:
        print(f"[PARSER] bcf: {e}")
    return results


# ── Noelle Leeming (data-ga-product JSON) ────────────────────────────────
def _noelleeming(html, base, **_):
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for tile in soup.find_all(attrs={"data-ga-product": True})[:12]:
            try:
                ga    = json.loads(tile.get("data-ga-product","{}"))
                name  = ga.get("item_name","")
                price = ga.get("price")
                a     = tile.find("a")
                href  = abs_url(a.get("href","") if a else "", base)
                if name and price and href:
                    results.append({"title": name, "price": float(price), "link": href})
            except Exception:
                continue
    except Exception as e:
        print(f"[PARSER] noelleeming: {e}")
    return results


# ── PB Tech (JS-rendered — returns empty gracefully) ─────────────────────
def _pbtech(html, base, **_):
    """PB Tech search results need JS that Scrape.do doesn't fully execute."""
    return []


# ── Skip (Auckland Airport — content site not retail) ────────────────────
def _skip(html, **_):
    return []


# ── Magento standard (Digi Direct, Camera Pro, Photo Gear, etc.) ──────────
def _magento(html, base, **_):
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for card in soup.select("li.item.product, li[class*='product-item']")[:12]:
            name_a = (card.select_one("a.product-item-link") or
                      card.select_one("strong.product-item-name a") or
                      card.select_one("h2 a"))
            price_el = (card.select_one("span[data-price-type='finalPrice'] span.price") or
                        card.select_one("span.price"))
            if not name_a:
                continue
            title = name_a.get_text(strip=True)
            href  = abs_url(name_a.get("href",""), base)
            price = clean_price(price_el.get_text() if price_el else "")
            if title and price and href:
                results.append({"title": title, "price": price, "link": href})
    except Exception as e:
        print(f"[PARSER] magento ({base}): {e}")
    return results


# ── Rubber Monkey (card-container anchor) ────────────────────────────────
def _rubbermonkey(html, base, **_):
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for card in soup.find_all("a", class_=re.compile("card-container"))[:12]:
            href = abs_url(card.get("href",""), base)
            name_el = card.find(class_=re.compile("product-details|card-title|name"))
            title = name_el.get_text(strip=True) if name_el else ""
            if not title:
                text = card.get_text(" ", strip=True)
                m = re.match(r'^(.{10,80?}?)\s*\$', text)
                title = m.group(1).strip() if m else text[:60]
            price_el = card.find(class_=re.compile("customerPrice|price-with-cents|card-rotator-card-price"))
            m = re.search(r'\$([\d,]+(?:\.\d+)?)', (price_el or card).get_text(" "))
            price = float(m.group(1).replace(",","")) if m else None
            if title and price and href:
                results.append({"title": title, "price": price, "link": href})
    except Exception as e:
        print(f"[PARSER] rubbermonkey: {e}")
    return results



# ── CS-Cart (Harvey Norman NZ) ────────────────────────────────────────────
def _cscart(html, base, **_):
    """
    Harvey Norman NZ uses CS-Cart. Product data is embedded as JSON in
    hidden inputs (select_item_json) inside product forms.
    Links are protocol-relative //www.harveynorman.co.nz/...html
    """
    import json as _json
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        # Each product has a form named "product_form_XXXXX"
        forms = soup.find_all("form", attrs={"name": re.compile(r"^product_form_")})
        for form in forms[:12]:
            # Extract product data from the select_item_json hidden input
            inp = form.find("input", attrs={"name": re.compile(r"select_item_json")})
            if not inp:
                continue
            try:
                data  = _json.loads(inp.get("value", "{}"))
                items = data.get("ecommerce", {}).get("items", [])
                if not items:
                    continue
                item  = items[0]
                name  = item.get("item_name", "")
                price = item.get("price", 0)
                if not name or not price:
                    continue
            except Exception:
                continue

            # Find the product link — a.product-title inside the same tile
            tile = form.parent
            link_el = tile.find("a", class_=re.compile("product-title")) if tile else None
            href = link_el.get("href", "") if link_el else ""
            # Protocol-relative URLs like //www.harveynorman.co.nz/...
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = base + href
            elif not href.startswith("http"):
                continue

            results.append({"title": name, "price": float(price), "link": href})
    except Exception as e:
        print(f"[PARSER] cscart: {e}")
    return results


# ── Officeworks via Algolia JSON API ─────────────────────────────────────
def _algolia(html, base, **_):
    """
    Officeworks uses Algolia for search. The search_url calls Algolia
    directly, so html is JSON text (possibly with extra wrapper content).
    """
    results = []
    try:
        import json as _json

        # Find the JSON object — Scrape.do may prepend/append content
        text = html.strip()
        for marker in ['{"hits"', '{"results"', '{']:
            pos = text.find(marker)
            if pos != -1:
                raw = text[pos:]
                break
        else:
            return results

        # Parse robustly — if full parse fails, trim to last closing brace
        data = None
        for attempt in (raw, raw[:raw.rfind('}') + 1]):
            try:
                data = _json.loads(attempt)
                break
            except _json.JSONDecodeError:
                continue
        if data is None:
            return results

        # Single-index GET → {hits:[...]}  |  Batch POST → {results:[{hits:[...]}]}
        if "hits" in data:
            hits = data["hits"]
        elif "results" in data and data["results"]:
            hits = data["results"][0].get("hits", [])
        else:
            return results

        for hit in hits[:12]:
            name        = hit.get("name", "")
            price_cents = hit.get("price", 0)
            seo         = hit.get("seoPath", "") or ""
            sku         = hit.get("sku", "")
            if not name or not price_cents:
                continue
            price = price_cents / 100
            if seo:
                link = base + (seo if seo.startswith("/") else "/" + seo)
            else:
                slug = name.lower().replace(" ", "-").replace("/", "-")
                link = f"{base}/shop/officeworks/p/{slug}-{sku.lower()}"
            results.append({"title": name, "price": price, "link": link})
    except Exception as e:
        print(f"[PARSER] algolia (officeworks): {e}")
    return results



# ── Auckland Airport Mall (duty-free retail) ──────────────────────────────
def _auckland_mall(html, base, **_):
    """
    Auckland Airport duty-free mall.
    Products are rendered as <a class="productTile productGridItem"> inside
    a <div class="productGrid">. Each tile has:
      - title attribute  → product name
      - href attribute   → product URL (relative)
      - first $X.XX text → sale/current price
    """
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        grid = soup.select_one(".productGrid")
        if not grid:
            return results
        tiles = grid.select("a.productTile")
        for tile in tiles[:24]:
            title = tile.get("title", "").strip()
            href  = tile.get("href", "").strip()
            if not title or not href:
                continue
            link = base + href if href.startswith("/") else href
            # Collect all visible text strings and find first price
            price = None
            for text in tile.stripped_strings:
                m = re.match(r"^\$([0-9,]+(?:\.[0-9]+)?)$", text.strip())
                if m:
                    price = clean_price(m.group(1))
                    break
            if title and price and link:
                results.append({"title": title, "price": price, "link": link})
    except Exception as e:
        print(f"[PARSER] auckland_mall: {e}")
    return results


def _extract_json_generic(html, base):
    import re as _re
    results = []
    seen = set()
    pat = (r'"(?:name|title|productName)"\s*:\s*"([^"]{5,150})"'
           r'[^}]{0,400}?"(?:price|salePrice|currentPrice)"\s*:\s*"?(\d+\.?\d*)"?'
           r'[^}]{0,400}?"(?:url|href|slug|urlPath)"\s*:\s*"(/[^"]{3,100})"')
    for name, price_raw, url in _re.findall(pat, html[:2000000], _re.DOTALL):
        if name in seen:
            continue
        seen.add(name)
        p = clean_price(price_raw)
        if name and p and p > 0:
            results.append({"title": name, "price": p, "link": abs_url(url, base)})
    return results

# ── Klevu / Snize Search (PhotoGear — JS-rendered search results) ─────────
def _klevu(html, base, **_):
    """
    PhotoGear uses Searchanise (Snize) for search results.
    After JS render, products appear as <li class="snize-product"> elements with:
      - a.snize-view-link  → product URL
      - span.snize-title   → product name
      - first $X,XXX.XX text in card → price
    Falls back to Shopify JSON if Snize didn't render.
    """
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")

        # Method 1 — Snize rendered product cards
        cards = soup.select("li.snize-product")
        for card in cards[:12]:
            # Title
            title_el = card.select_one(".snize-title")
            title = title_el.get_text(strip=True) if title_el else ""

            # Link — wrapping <a> with class snize-view-link
            link_el = card.select_one("a.snize-view-link")
            href = link_el.get("href", "") if link_el else ""
            link = href if href.startswith("http") else base + href

            # Price — first $X,XXX.XX pattern in card text
            card_text = card.get_text(" ")
            import re as _re
            prices = _re.findall(r"\$([0-9,]+(?:\.[0-9]+)?)", card_text)
            price = None
            for p in prices:
                try:
                    price = float(p.replace(",", ""))
                    if price > 0:
                        break
                except Exception:
                    continue

            if title and price and link:
                results.append({"title": title, "price": price, "link": link})

        if results:
            return results

        # Method 2 — Klevu rendered cards (ku- prefix, alternative layout)
        for sel in ["li.klevuProduct", "li.ku-result-item", "[class*='klevuProduct']"]:
            cards = soup.select(sel)
            if cards:
                for card in cards[:12]:
                    name_el = (
                        card.select_one(".ku-title") or
                        card.select_one("[class*='ku-title']") or
                        card.select_one("h2") or card.select_one("h3")
                    )
                    title = name_el.get_text(strip=True) if name_el else ""
                    price_el = card.select_one(".ku-price") or card.select_one("[class*='price']")
                    price = clean_price(price_el.get_text() if price_el else "")
                    link_el = card.select_one("a")
                    href = link_el.get("href", "") if link_el else ""
                    link = abs_url(href, base)
                    if title and price and link:
                        results.append({"title": title, "price": price, "link": link})
                if results:
                    return results

        # Method 3 — Shopify JSON fallback (non-JS page)
        results = _shopify(html, base)

    except Exception as e:
        print(f"[PARSER] klevu: {e}")
    return results


# ── Photo Warehouse NZ ───────────────────────────────────────────────────
def _photowarehouse(html, base, **_):
    """
    Photo Warehouse NZ. Products are <a class="product-card"> elements.
    Title lives in data-pf-title attribute on an inner div.
    Price is the first $X,XXX.XX pattern in the card text.
    """
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for card in soup.select("a.product-card")[:24]:
            href = card.get("href", "")
            link = base + href if href.startswith("/") else href

            # Title from data-pf-title attribute
            pf = card.select_one("[data-pf-title]")
            title = pf.get("data-pf-title", "").strip() if pf else ""

            # Fallback: first meaningful text string
            if not title:
                for txt in card.stripped_strings:
                    if len(txt) > 10 and not txt.startswith("$"):
                        title = txt
                        break

            # Price — first $X,XXX.XX in card text
            prices = re.findall(r"\$([0-9,]+(?:\.[0-9]+)?)", card.get_text())
            price = None
            if prices:
                try:
                    price = float(prices[0].replace(",", ""))
                except Exception:
                    pass

            if title and price and link:
                results.append({"title": title, "price": price, "link": link})
    except Exception as e:
        print(f"[PARSER] photowarehouse: {e}")
    return results


# ── Boost Commerce / bc-sf-filter (Jacobs Digital) ───────────────────────
def _boostcommerce(html, base, **_):
    """
    Jacobs Digital uses Boost Commerce (bc-sf-filter) for search.
    Requires medium tier (JS rendering) so Boost PFS executes and injects cards.

    Rendered card structure (confirmed from live medium-tier HTML):

        <div class="boost-pfs-filter-products">
          <div class="row search-result" data-id="...">
            <div class="col-12 col-lg-5">
              <p class="product-title">
                <a href="/collections/all/products/{handle}">Product Name</a>
              </p>
            </div>
            <div class="col-12 col-lg-4">
              <li><span class="product-price">$5,334.00</span></li>
            </div>
          </div>
        </div>
    """
    results = []
    try:
        soup = BeautifulSoup(html, "lxml")

        # Each search result is div.row.search-result inside .boost-pfs-filter-products
        container = soup.select_one(".boost-pfs-filter-products")
        cards = (container or soup).select("div.row.search-result")

        for card in cards[:24]:
            # Title: p.product-title > a
            title_el = card.select_one("p.product-title a") or card.select_one("p.product-title")
            title = title_el.get_text(strip=True) if title_el else ""

            # Link: any a href pointing to a product
            link_el = card.select_one("a[href*='/products/']")
            href = link_el.get("href", "") if link_el else ""
            link = abs_url(href, base)

            # Price: span.product-price
            price_el = card.select_one("span.product-price")
            price = clean_price(price_el.get_text() if price_el else "")

            if title and price and link:
                results.append({"title": title, "price": price, "link": link})

    except Exception as e:
        print(f"[PARSER] boostcommerce (jacobsdigital): {e}")

    return results



_EXTRACTORS = {
    "boostcommerce": _boostcommerce,
    "klevu":          _klevu,
    "photowarehouse": _photowarehouse,
    "shopify":      _shopify,
    "goodguys":     _goodguys,
    "harveynorman": _harveynorman,
    "bunnings":     _bunnings,
    "bigw":         _bigw,
    "nextdata":     _nextdata,
    "costco":       _costco,
    "anaconda":     _anaconda,
    "bcf":          _bcf,
    "noelleeming":  _noelleeming,
    "pbtech":       _pbtech,
    "skip":         _skip,
    "magento":      _magento,
    "rubbermonkey": _rubbermonkey,
    "cscart":       _cscart,
    "algolia":      _algolia,
    "auckland_mall": _auckland_mall,
}


def parse_results(html: str | None, domain: str) -> list[dict]:
    if not html or domain not in SITE_PARSERS:
        return []
    rules = SITE_PARSERS[domain]
    extractor = _EXTRACTORS.get(rules["_type"])
    if not extractor:
        return []
    try:
        return extractor(html, **{k: v for k, v in rules.items() if k != "_type"})
    except Exception as e:
        print(f"[PARSER] {domain}: {e}")
        return []
