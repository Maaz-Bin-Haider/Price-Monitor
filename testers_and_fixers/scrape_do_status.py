"""
scrape_do_status.py — Quickly diagnose whether the issue is Scrape.do or individual sites.
Run: python testers_and_fixers/scrape_do_status.py
"""
import requests
import time

TOKEN = "071a463d431640e6ba41fc80f64e6ace03a76b5007f"

print("=" * 60)
print("  SCRAPE.DO DIAGNOSTICS")
print("=" * 60)

# ── 1. Account status ──────────────────────────────────────────
print("\n[1] Account status...")
try:
    r = requests.get("https://api.scrape.do/info", params={"token": TOKEN}, timeout=15)
    if r.status_code == 200:
        info = r.json()
        active    = info.get("IsActive")
        remaining = info.get("RemainingMonthlyRequest")
        max_req   = info.get("MaxMonthlyRequest")
        concurrent = info.get("ConcurrentRequest")
        used      = max_req - remaining if max_req and remaining else "?"
        pct       = f"{used/max_req*100:.1f}%" if isinstance(used, int) and max_req else "?"

        print(f"   Active            : {'✓ YES' if active else '✗ NO — SUBSCRIPTION INACTIVE'}")
        print(f"   Monthly limit     : {max_req:,}")
        print(f"   Used this month   : {used:,}  ({pct})")
        print(f"   Remaining         : {remaining:,}")
        print(f"   Concurrent slots  : {concurrent}")

        if not active:
            print("\n   ⚠️  SUBSCRIPTION IS INACTIVE — this is why all sites are 502ing.")
            print("   Fix: log in to app.scrape.do and check your billing / plan status.")
        elif isinstance(remaining, int) and remaining < 100:
            print("\n   ⚠️  CREDITS NEARLY EXHAUSTED — requests will fail when remaining hits 0.")
    else:
        print(f"   Failed to get account info: HTTP {r.status_code} — {r.text[:100]}")
except Exception as e:
    print(f"   Error: {e}")

# ── 2. Simple fetch test (httpbin — always works if Scrape.do is up) ────────
print("\n[2] Basic connectivity test (httpbin.org — no anti-bot)...")
try:
    start = time.time()
    r = requests.get("https://api.scrape.do", params={
        "token": TOKEN,
        "url":   "https://httpbin.org/get",
        "geoCode": "us",
    }, timeout=30)
    elapsed = time.time() - start
    if r.status_code == 200 and "httpbin" in r.text:
        print(f"   ✓ Scrape.do API is responding normally ({elapsed:.1f}s)")
    elif r.status_code == 200:
        print(f"   ✓ HTTP 200 but unexpected body — API may be degraded ({elapsed:.1f}s)")
        print(f"   Body preview: {r.text[:100]}")
    else:
        print(f"   ✗ HTTP {r.status_code} — {r.text[:150]}")
except Exception as e:
    print(f"   ✗ Connection error: {e}")

# ── 3. Test a normally-easy site (rubber monkey, no anti-bot) ──────────────
print("\n[3] Test easy site: rubbermonkey.co.nz (light tier, no anti-bot)...")
try:
    start = time.time()
    r = requests.get("https://api.scrape.do", params={
        "token":   TOKEN,
        "url":     "https://www.rubbermonkey.co.nz/search?q=sony",
        "geoCode": "nz",
    }, timeout=30)
    elapsed = time.time() - start
    if r.status_code == 200:
        size = len(r.text)
        print(f"   ✓ HTTP 200 — {size:,} bytes in {elapsed:.1f}s")
    else:
        print(f"   ✗ HTTP {r.status_code} in {elapsed:.1f}s — {r.text[:100]}")
except Exception as e:
    print(f"   ✗ Error: {e}")

# ── 4. Test a medium-tier site (JB Hi-Fi AU) ──────────────────────────────
print("\n[4] Test medium-tier site: jbhifi.com.au...")
try:
    start = time.time()
    r = requests.get("https://api.scrape.do", params={
        "token":     TOKEN,
        "url":       "https://www.jbhifi.com.au/search?q=sony",
        "geoCode":   "au",
        "render":    "true",
        "waitUntil": "networkidle0",
    }, timeout=90)
    elapsed = time.time() - start
    if r.status_code == 200:
        size = len(r.text)
        print(f"   ✓ HTTP 200 — {size:,} bytes in {elapsed:.1f}s")
    else:
        print(f"   ✗ HTTP {r.status_code} in {elapsed:.1f}s — {r.text[:100]}")
except Exception as e:
    print(f"   ✗ Error: {e}")

# ── 5. Diagnosis summary ────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  WHAT TO DO NEXT")
print("=" * 60)
print("""
  If test [2] failed → Scrape.do API itself is down. Wait and retry.

  If test [1] shows IsActive=False → Your subscription lapsed.
  Log in to app.scrape.do to renew.

  If test [1] shows Remaining < 1000 → You're nearly out of credits.
  Upgrade plan or wait for monthly reset.

  If tests [2] and [3] pass but [4] fails → Medium/heavy tier proxy
  pool is degraded. This is a Scrape.do infrastructure issue.
  Email support@scrape.do with your token and affected URLs.

  If all tests pass → The 502s are temporary proxy IP rotation issues.
  Wait 1-2 hours and run bulk_site_check.py again.
""")
