import requests

def test_scrape(url: str, token: str, geo: str = "nz", render: bool = False, super_mode: bool = False):
    params = {
        "token": token,
        "url": url,
        "geoCode": geo,
    }
    if render:
        params["render"] = "true"
    if super_mode:
        params["super"] = "true"

    response = requests.get("https://api.scrape.do", params=params, timeout=60)
    print(f"Status : {response.status_code}")
    print(f"Preview: {response.text[:300]}")
    return response



response = test_scrape(
    url="https://www.bunnings.co.nz/_next/data/LXjxXu0q4iR9G1bhixXWX/search/products.json?page=1&q=Ryobi+drill&sort=BoostOrder&rest=products",
    token="071a463d431640e6ba41fc80f64e6ace03a76b5007f",
    geo="nz",
    render=False,
    super_mode=True,
)

print(response)