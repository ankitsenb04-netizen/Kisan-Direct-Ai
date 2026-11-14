"""Live-browser tests for Kisan Direct AI — complete homepage-to-order journey.

The backend serves the whole website from ONE origin (see main.py):
  /            standalone homepage
  /auth        login/register page (/login redirects here)
  /marketplace marketplace
  /dashboard   farmer dashboard
Test data only. Requires the backend running on 127.0.0.1:8000 with a
FRESH database (delete mvp/backend/kisan_direct.db first, or the
register steps will hit "Email already registered"):
  KISAN_SERVE_FRONTEND=1 python3 -m uvicorn mvp.backend.main:app --host 127.0.0.1 --port 8000
Run from the repo root:
  PLAYWRIGHT_CHROME_PATH=<path to Chrome for Testing> python3 browser-tests/test_browser.py
Screenshots and results.json are written next to this file.
"""
import json, os, sys, traceback
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("KISAN_FRONTEND_URL", "http://127.0.0.1:8000")
CHROME = os.environ.get("PLAYWRIGHT_CHROME_PATH")  # set to a Chrome for Testing binary if Playwright's own Chromium is not installed
OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

results = []  # (name, status, detail)
console_errors = []

def check(name, ok, detail=""):
    results.append((name, "PASS" if ok else "FAIL", detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"]) if CHROME else p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("console", lambda m: console_errors.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: console_errors.append(f"[pageerror] {e}"))
        dialog_log = []
        page.on("dialog", lambda d: (dialog_log.append(f"{d.type}: {d.message}"), d.accept("10") if d.type == "prompt" else d.accept()))

        # ---- 1. Homepage / ----
        try:
            r = page.goto(BASE + "/", wait_until="networkidle", timeout=15000)
            check("homepage / loads 200", r.status == 200, f"status={r.status}")
            check("homepage title/brand", "Kisan Direct" in page.title(), page.title())
            check("homepage hero", "Sell Smarter" in page.inner_text("body"))
            check("homepage CSS loads", page.evaluate("fetch('/homepage.css').then(r=>r.status)") == 200)
            page.screenshot(path=str(OUT / "01-homepage-desktop.png"))
        except Exception as e:
            check("homepage / loads", False, str(e)); traceback.print_exc()

        # ---- 2. Homepage nav -> /marketplace ----
        try:
            page.get_by_role("link", name="Marketplace").first.click()
            page.wait_for_url("**/marketplace", timeout=10000)
            check("homepage nav Marketplace -> /marketplace", "/marketplace" in page.url, page.url)
            check("marketplace title", "AI Farmer Marketplace" in page.title(), page.title())
            page.wait_for_selector(".product", timeout=10000)
            txt = page.inner_text("#products")
            check("seeded listings visible", "Tomato" in txt and "Potato" in txt, txt[:200].replace("\n", " | "))
        except Exception as e:
            check("homepage nav Marketplace", False, str(e))

        # ---- 3. Price + demand prediction on /marketplace ----
        try:
            page.click("text=Predict crop price")
            page.wait_for_function("document.getElementById('priceResult').innerText.includes('₹')", timeout=10000)
            check("price prediction works", "Estimated price" in page.inner_text("#priceResult"), page.inner_text("#priceResult").replace("\n", " "))
            page.click("text=Predict demand")
            page.wait_for_function("document.getElementById('demandResult').innerText.includes('Demand level')", timeout=10000)
            check("demand prediction works", "Demand level" in page.inner_text("#demandResult"), page.inner_text("#demandResult").replace("\n", " "))
        except Exception as e:
            check("AI predictions work", False, str(e))
        page.screenshot(path=str(OUT / "02-marketplace-ai.png"))

        # ---- 4. Marketplace auth modal still opens ----
        try:
            page.click("text=Login / Register")
            page.wait_for_selector("#authModal:not(.hidden)", timeout=5000)
            check("marketplace auth modal opens", True)
            page.click(".modal .close")
        except Exception as e:
            check("marketplace auth modal opens", False, str(e))

        # ---- 5. /login redirects to /auth; register a farmer there ----
        try:
            page.goto(BASE + "/login", wait_until="networkidle", timeout=15000)
            page.wait_for_url("**/auth", timeout=10000)
            check("/login redirects to /auth", page.url.endswith("/auth"), page.url)
            check("auth page loads", "Kisan Portal" in page.inner_text("body"))
            page.get_by_role("button", name="New Registration").click()
            page.fill("#regName", "Test Farmer")
            page.fill("#regPhone", "9876543210")
            page.fill("#regPassword", "testpass123")
            page.select_option("#regRole", "farmer")
            page.locator("#registerForm button[type=submit]").click()
            page.wait_for_url("**/dashboard", timeout=10000)
            check("register farmer on /auth redirects to /dashboard", "/dashboard" in page.url, page.url)
        except Exception as e:
            check("register farmer on /auth", False, str(e) + " | err=" + (page.inner_text("#authError") if page.locator("#authError").count() else ""))
        page.screenshot(path=str(OUT / "03-auth.png"))

        # ---- 6. Farmer dashboard with live data (0 listings yet) ----
        try:
            page.wait_for_function("document.getElementById('priceIntel').innerText.includes('Tomato')", timeout=10000)
            body = page.inner_text("body")
            check("dashboard greeting", "Good Morning, Test Farmer" in body)
            check("dashboard My Produce", "My Produce" in body)
            check("dashboard Market Price Intelligence", "Market Price Intelligence" in body and "₹" in page.inner_text("#priceIntel"))
            check("dashboard AI Selling Advisor", "AI Selling Advisor" in body and "Demand is" in page.inner_text("#advisor"))
            check("dashboard Top Buyer Matches (labelled sample)", "Top Buyer Matches" in body and "Sample buyers" in body)
            check("dashboard Active Deliveries section", "Active Deliveries" in body)
        except Exception as e:
            check("farmer dashboard loads with live data", False, str(e))
        page.screenshot(path=str(OUT / "04-dashboard.png"))

        # ---- 7. Dashboard nav -> /marketplace; farmer creates a listing ----
        try:
            page.get_by_role("link", name="Marketplace").first.click()
            page.wait_for_url("**/marketplace", timeout=10000)
            check("dashboard nav Marketplace -> /marketplace", "/marketplace" in page.url, page.url)
            page.select_option("#sellCrop", "Onion")
            page.fill("#sellQty", "50")
            page.fill("#sellPrice", "30")
            page.select_option("#sellLocation", "Howrah")
            page.fill("#sellDesc", "Browser test onions")
            page.click("text=Publish listing")
            page.wait_for_selector("text=Listing published successfully!", timeout=10000)
            check("farmer creates listing", True)
            page.wait_for_function("document.getElementById('products').innerText.includes('Browser test onions')", timeout=10000)
            check("new listing appears in marketplace", True)
        except Exception as e:
            check("farmer creates listing", False, str(e) + " | sellmsg=" + page.inner_text("#sellMessage"))
        page.screenshot(path=str(OUT / "05-new-listing.png"))

        # ---- 8. Dashboard again: 1 listing, My Produce shows it ----
        try:
            page.goto(BASE + "/dashboard", wait_until="networkidle", timeout=15000)
            page.wait_for_function("document.getElementById('priceIntel').innerText.includes('Tomato')", timeout=10000)
            check("dashboard stat listings = 1", page.inner_text("#statListings").strip() == "1", "listings=" + page.inner_text("#statListings"))
            check("dashboard My Produce shows new listing", "Onion" in page.inner_text("#myProduce"))
        except Exception as e:
            check("dashboard shows new listing", False, str(e))

        # ---- 9. Logout, register a customer on /auth -> /marketplace ----
        try:
            page.goto(BASE + "/marketplace", wait_until="networkidle", timeout=15000)
            page.click("text=Logout")
            page.wait_for_selector("text=Login / Register", timeout=5000)
            check("logout works", True)
            page.goto(BASE + "/auth", wait_until="networkidle", timeout=15000)
            page.get_by_role("button", name="New Registration").click()
            page.fill("#regName", "Test Buyer")
            page.fill("#regPhone", "9876543211")
            page.fill("#regPassword", "testpass123")
            page.select_option("#regRole", "customer")
            page.locator("#registerForm button[type=submit]").click()
            page.wait_for_url("**/marketplace", timeout=10000)
            check("register customer on /auth redirects to /marketplace", "/marketplace" in page.url, page.url)
            check("customer logged in on marketplace", "Hi, Test Buyer" in page.inner_text("body"))
            check("buy button visible for customer", page.locator("button", has_text="Buy").count() > 0, f"buy buttons={page.locator('button', has_text='Buy').count()}")
            page.locator("button", has_text="Buy").first.click()
            page.wait_for_function("document.getElementById('ordersList').innerText.includes('Order #')", timeout=10000)
            check("customer places order via Buy button", True, "dialogs: " + "; ".join(dialog_log))
            check("My Orders shows the order", "Order #" in page.inner_text("#ordersList"), page.inner_text("#ordersList").replace("\n", " "))
        except Exception as e:
            check("customer places order via Buy button", False, str(e) + " | dialogs=" + "; ".join(dialog_log))
        page.screenshot(path=str(OUT / "06-customer-order.png"))

        # ---- 10. Customer visiting /dashboard gets a clear message ----
        try:
            page.goto(BASE + "/dashboard", wait_until="networkidle", timeout=15000)
            body = page.inner_text("body")
            check("customer on /dashboard sees farmer-only message", "logged in as a customer" in body and "farmer accounts" in body)
        except Exception as e:
            check("customer on /dashboard message", False, str(e))

        # ---- 11. Wrong password rejected on /auth ----
        try:
            page.goto(BASE + "/auth", wait_until="networkidle", timeout=15000)
            page.fill("#loginId", "9876543211")
            page.fill("#loginPassword", "wrongpass")
            page.locator("#loginForm button[type=submit]").click()
            page.wait_for_function("document.getElementById('authError').innerText.length > 0", timeout=5000)
            check("wrong password rejected on /auth", "Incorrect" in page.inner_text("#authError"), page.inner_text("#authError"))
        except Exception as e:
            check("wrong password rejected on /auth", False, str(e))
        page.screenshot(path=str(OUT / "07-login-error.png"))

        # ---- 12. Unauthenticated /dashboard shows a login prompt ----
        try:
            anon = browser.new_page(viewport={"width": 1280, "height": 800})
            anon.goto(BASE + "/dashboard", wait_until="networkidle", timeout=15000)
            body = anon.inner_text("body")
            check("unauthenticated /dashboard shows login prompt", "Please log in" in body and "log in" in body)
            anon.get_by_role("link", name="log in").first.click()
            anon.wait_for_url("**/auth", timeout=10000)
            check("dashboard login prompt links to /auth", "/auth" in anon.url, anon.url)
            anon.close()
        except Exception as e:
            check("unauthenticated /dashboard login prompt", False, str(e))

        # ---- 13. Mobile 390x844 ----
        try:
            mob = browser.new_page(viewport={"width": 390, "height": 844})
            mob.on("pageerror", lambda e: console_errors.append(f"[mobile pageerror] {e}"))
            mob.goto(BASE + "/", wait_until="networkidle", timeout=15000)
            overflow = mob.evaluate("document.documentElement.scrollWidth > 390")
            check("mobile homepage loads, no horizontal overflow", not overflow, f"scrollWidth={mob.evaluate('document.documentElement.scrollWidth')}")
            mob.screenshot(path=str(OUT / "08-homepage-mobile.png"))
            mob.goto(BASE + "/auth", wait_until="networkidle", timeout=15000)
            overflow = mob.evaluate("document.documentElement.scrollWidth > 390")
            check("mobile /auth loads, no horizontal overflow", not overflow, f"scrollWidth={mob.evaluate('document.documentElement.scrollWidth')}")
            mob.screenshot(path=str(OUT / "10-auth-mobile.png"))
            mob.goto(BASE + "/marketplace", wait_until="networkidle", timeout=15000)
            mob.wait_for_selector(".product", timeout=10000)
            overflow = mob.evaluate("document.documentElement.scrollWidth > 390")
            check("mobile /marketplace loads, no horizontal overflow", not overflow, f"scrollWidth={mob.evaluate('document.documentElement.scrollWidth')}")
            mob.screenshot(path=str(OUT / "11-marketplace-mobile.png"))
            mob.goto(BASE + "/dashboard", wait_until="networkidle", timeout=15000)
            mob.wait_for_function("document.getElementById('priceIntel').innerText.includes('Tomato')", timeout=10000)
            overflow = mob.evaluate("document.documentElement.scrollWidth > 390")
            check("mobile /dashboard loads, no horizontal overflow", not overflow, f"scrollWidth={mob.evaluate('document.documentElement.scrollWidth')}")
            mob.screenshot(path=str(OUT / "09-dashboard-mobile.png"))
            mob.close()
        except Exception as e:
            check("mobile responsive", False, str(e))

        browser.close()

    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"\nTOTAL: {passed} passed, {failed} failed, {len(results)} checks")
    print("CONSOLE ERRORS:", json.dumps(console_errors, indent=2) if console_errors else "none")
    (OUT / "results.json").write_text(json.dumps({"results": results, "console_errors": console_errors, "passed": passed, "failed": failed}, indent=2))
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
