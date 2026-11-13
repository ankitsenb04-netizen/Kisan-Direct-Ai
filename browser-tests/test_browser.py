"""Live-browser tests for Kisan Direct AI (integrated app).
Test data only. Requires the backend on 127.0.0.1:8000 and the frontend on
127.0.0.1:5500 (see root README), plus Playwright (`pip install playwright`
and `playwright install chromium`, or set PLAYWRIGHT_CHROME_PATH to a
Chrome for Testing binary). Run from the repo root:
  python3 browser-tests/test_browser.py
Screenshots and results.json are written next to this file.
"""
import json, os, sys, traceback
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("KISAN_FRONTEND_URL", "http://127.0.0.1:5500")
API = os.environ.get("KISAN_API_URL", "http://127.0.0.1:8000")
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
        # ---- Desktop 1280x800 ----
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("console", lambda m: console_errors.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: console_errors.append(f"[pageerror] {e}"))
        dialog_log = []
        page.on("dialog", lambda d: (dialog_log.append(f"{d.type}: {d.message}"), d.accept("10") if d.type == "prompt" else d.accept()))

        # 1. Homepage loads
        try:
            r = page.goto(BASE + "/", wait_until="networkidle", timeout=15000)
            check("homepage loads 200", r.status == 200, f"status={r.status}")
            check("homepage title/brand", "Kisan" in page.title() or "Kisan" in page.inner_text("body")[:2000], page.title())
            check("homepage nav links present", all(t in page.inner_text("body") for t in ["Marketplace", "AI Predictions", "Sell Produce"]))
            page.screenshot(path=str(OUT / "01-homepage-desktop.png"))
        except Exception as e:
            check("homepage loads", False, str(e)); traceback.print_exc()

        # 2. Seeded products visible
        try:
            page.wait_for_selector(".product", timeout=10000)
            txt = page.inner_text("#products")
            check("seeded listings visible", "Tomato" in txt and "Potato" in txt, txt[:200].replace("\n", " | "))
        except Exception as e:
            check("seeded listings visible", False, str(e))

        # 3. Price prediction
        try:
            page.click("text=Predict crop price")
            page.wait_for_function("document.getElementById('priceResult').innerText.includes('₹')", timeout=10000)
            check("price prediction works", "Estimated price" in page.inner_text("#priceResult"), page.inner_text("#priceResult").replace("\n", " "))
        except Exception as e:
            check("price prediction works", False, str(e))
        # 4. Demand prediction
        try:
            page.click("text=Predict demand")
            page.wait_for_function("document.getElementById('demandResult').innerText.includes('Demand level')", timeout=10000)
            check("demand prediction works", "Demand level" in page.inner_text("#demandResult"), page.inner_text("#demandResult").replace("\n", " "))
        except Exception as e:
            check("demand prediction works", False, str(e))
        page.screenshot(path=str(OUT / "02-homepage-ai-desktop.png"))

        # 5. Register a test farmer via modal
        try:
            page.click("text=Login / Register")
            page.wait_for_selector("#authModal:not(.hidden)", timeout=5000)
            check("auth modal opens", True)
            page.click("#registerTab")
            page.fill("#authName", "Test Farmer")
            page.fill("#authEmail", "testfarmer@example.com")
            page.fill("#authPassword", "testpass123")
            page.select_option("#authRole", "farmer")
            page.click("#authSubmit")
            page.wait_for_selector("text=Hi, Test Farmer", timeout=10000)
            check("register farmer + auto-login", True, "Hi, Test Farmer shown")
            check("dashboard link visible for farmer", page.is_visible("#dashLink"))
        except Exception as e:
            check("register farmer + auto-login", False, str(e) + " | msg=" + page.inner_text("#authMessage"))
        page.screenshot(path=str(OUT / "03-logged-in-farmer.png"))

        # 6. Create a listing
        try:
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
        page.screenshot(path=str(OUT / "04-new-listing.png"))

        # 7. Farmer dashboard
        try:
            page.goto(BASE + "/farmer-dashboard.html", wait_until="networkidle", timeout=15000)
            page.wait_for_function("document.getElementById('priceIntel').innerText.includes('Tomato')", timeout=10000)
            body = page.inner_text("body")
            check("dashboard greeting", "Good Morning, Test Farmer" in body)
            check("dashboard My Produce", "My Produce" in body and "Onion" in body)
            check("dashboard Market Price Intelligence", "Market Price Intelligence" in body and "₹" in page.inner_text("#priceIntel"))
            check("dashboard AI Selling Advisor", "AI Selling Advisor" in body and "Demand is" in page.inner_text("#advisor"))
            check("dashboard Top Buyer Matches (labelled sample)", "Top Buyer Matches" in body and "Sample buyers" in body)
            check("dashboard Active Deliveries section", "Active Deliveries" in body)
            check("dashboard stat listings > 0", page.inner_text("#statListings").strip() != "0", "listings=" + page.inner_text("#statListings"))
        except Exception as e:
            check("farmer dashboard loads with live data", False, str(e))
        page.screenshot(path=str(OUT / "05-dashboard-desktop.png"))

        # 8. Logout, register customer, place order via Buy button
        try:
            page.goto(BASE + "/", wait_until="networkidle", timeout=15000)
            page.click("text=Logout")
            page.wait_for_selector("text=Login / Register", timeout=5000)
            check("logout works", True)
            page.click("text=Login / Register")
            page.click("#registerTab")
            page.fill("#authName", "Test Buyer")
            page.fill("#authEmail", "testbuyer@example.com")
            page.fill("#authPassword", "testpass123")
            page.select_option("#authRole", "customer")
            page.click("#authSubmit")
            page.wait_for_selector("text=Hi, Test Buyer", timeout=10000)
            check("register customer + auto-login", True)
            check("buy button visible for customer", page.locator("button", has_text="Buy").count() > 0, f"buy buttons={page.locator('button', has_text='Buy').count()}")
            page.locator("button", has_text="Buy").first.click()
            page.wait_for_function("document.getElementById('ordersList').innerText.includes('Order #')", timeout=10000)
            check("customer places order via Buy button", True, "dialogs: " + "; ".join(dialog_log))
            check("My Orders shows the order", "Order #" in page.inner_text("#ordersList"), page.inner_text("#ordersList").replace("\n", " "))
        except Exception as e:
            check("customer places order via Buy button", False, str(e) + " | dialogs=" + "; ".join(dialog_log))
        page.screenshot(path=str(OUT / "06-customer-order.png"))

        # 9. Wrong-password login rejected
        try:
            page.click("text=Logout")
            page.click("text=Login / Register")
            page.fill("#authEmail", "testbuyer@example.com")
            page.fill("#authPassword", "wrongpass")
            page.click("#authSubmit")
            page.wait_for_function("document.getElementById('authMessage').innerText.length > 0", timeout=5000)
            check("wrong password rejected in UI", "Invalid" in page.inner_text("#authMessage") or "incorrect" in page.inner_text("#authMessage").lower(), page.inner_text("#authMessage"))
        except Exception as e:
            check("wrong password rejected in UI", False, str(e))
        page.screenshot(path=str(OUT / "07-login-error.png"))

        # 10. Mobile 390x844
        try:
            mob = browser.new_page(viewport={"width": 390, "height": 844})
            mob.on("pageerror", lambda e: console_errors.append(f"[mobile pageerror] {e}"))
            mob.goto(BASE + "/", wait_until="networkidle", timeout=15000)
            mob.wait_for_selector(".product", timeout=10000)
            overflow = mob.evaluate("document.documentElement.scrollWidth > 390")
            check("mobile homepage loads, no horizontal overflow", not overflow, f"scrollWidth={mob.evaluate('document.documentElement.scrollWidth')}")
            mob.screenshot(path=str(OUT / "08-homepage-mobile.png"))
            mob.goto(BASE + "/farmer-dashboard.html", wait_until="networkidle", timeout=15000)
            mob.wait_for_function("document.getElementById('priceIntel').innerText.includes('Tomato')", timeout=10000)
            check("mobile dashboard loads", True)
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
