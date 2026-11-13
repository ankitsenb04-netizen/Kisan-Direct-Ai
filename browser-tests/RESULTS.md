# Live-Browser Test Results — Kisan Direct AI (integrated app)

**Date:** 2026-11-13 IST
**App under test:** `~/workspace/kisan-direct-ai-audit/integrated/` (branch `integration`, commit `587e0ee` at test time; fixes committed as `4ec07bc`)
**Servers:** backend http://127.0.0.1:8000 (uvicorn, fresh seeded DB), frontend http://127.0.0.1:5500 (python http.server)
**Browser:** real Chrome for Testing 158.0.8127.18, driven by Playwright (Python) in `~/workspace/kisan-direct-ai-audit/venv-browser/`
**Test script:** `browser-tests/test_browser.py` (reproducible; test data only — Test Farmer / testfarmer@example.com, Test Buyer / testbuyer@example.com, password testpass123)

## How the browser was installed (honest install log)

- `pip install playwright` succeeded.
- `playwright install chromium` **failed twice**: Chrome for Testing zip download stopped at ~90% with "Download failed: server closed connection" (cdn.playwright.dev). Same failure on retry.
- Workaround that worked: `curl -L -C -` downloaded the same 197.8 MB zip to 100% (the Playwright downloader, not the network, was failing). First unzip attempt failed because `/tmp` is a 512 MB tmpfs and filled up; the zip was moved to the workspace disk (147 GB free) and unzipped there.
- `apt` has no chromium/firefox candidate in this VM's repos, so apt was not a route.
- Chrome binary: `browser-tests/chrome/chrome-linux64/chrome` — `--version` reports Google Chrome for Testing 158.0.8127.18, no missing shared libraries.

## Results — 26 passed, 0 failed (run twice: before and after fixes)

| # | Check | Result |
|---|---|---|
| 1 | Homepage loads 200 | PASS |
| 2 | Homepage title/brand "Kisan Direct" | PASS |
| 3 | Homepage nav links (Marketplace, AI Predictions, Sell Produce) | PASS |
| 4 | Seeded listings visible (Tomato, Potato, Onion) | PASS |
| 5 | Price prediction works (₹27.33/kg, range 25.22–29.45) | PASS |
| 6 | Demand prediction works (Medium, index 166.9) | PASS |
| 7 | Auth modal opens | PASS |
| 8 | Register farmer + auto-login ("Hi, Test Farmer") | PASS |
| 9 | Dashboard link visible for farmer | PASS |
| 10 | Farmer creates listing (Onion, 50 kg, ₹30/kg, Howrah) | PASS |
| 11 | New listing appears in marketplace | PASS |
| 12 | Dashboard greeting ("Good Morning, Test Farmer!") | PASS |
| 13 | Dashboard My Produce | PASS |
| 14 | Dashboard Market Price Intelligence (₹27.33/kg) | PASS |
| 15 | Dashboard AI Selling Advisor (Demand is Medium…) | PASS |
| 16 | Dashboard Top Buyer Matches, labelled "Sample buyers" | PASS |
| 17 | Dashboard Active Deliveries section | PASS |
| 18 | Dashboard stat listings > 0 (1) | PASS |
| 19 | Logout works | PASS |
| 20 | Register customer + auto-login ("Hi, Test Buyer") | PASS |
| 21 | Buy button visible for customer (4 buttons) | PASS |
| 22 | Customer places order via Buy button (Order #1, prompt + alert dialogs) | PASS |
| 23 | My Orders shows the order (Order #1, Onion, 10 kg, ₹30/kg, Placed) | PASS |
| 24 | Wrong password rejected in UI ("Incorrect email or password.") | PASS |
| 25 | Mobile 390×844 homepage loads, no horizontal overflow (scrollWidth 390) | PASS |
| 26 | Mobile 390×844 dashboard loads | PASS |

**Pytest (regression, after fixes):** `tests/test_integration.py` — **8 passed, 0 failed** (11.96 s; 1 non-fatal StarletteDeprecationWarning about httpx).

## Console errors

- First run: 2 errors — `404 /favicon.ico` and `401 POST /api/login`.
  - The 401 is the intentional wrong-password test (check 24); it is expected, not a bug.
  - The 404 was a real cosmetic bug: no favicon. Fixed (below).
- Second run (after fixes): only the intentional 401 remains. **No 404, no page errors, no other console errors.**

## Screenshots (real, from the runs)

All in `browser-tests/`:
- `01-homepage-desktop.png` — homepage, 1280×800 (visually verified: hero, nav, trust badges render correctly)
- `02-homepage-ai-desktop.png` — AI prediction panels with results
- `03-logged-in-farmer.png` — logged-in farmer state
- `04-new-listing.png` — new Onion listing published
- `05-dashboard-desktop.png` — farmer dashboard (visually verified: greeting, stats, price intelligence, advisor, My Produce)
- `06-customer-order.png` — My Orders with Order #1
- `07-login-error.png` — wrong-password message
- `08-homepage-mobile.png` — homepage at 390×844 (visually verified: nav wraps to a second line, no overflow, hero stacks)
- `09-dashboard-mobile.png` — dashboard at 390×844

## Bugs found and fixed (verified, committed)

1. **Missing favicon → 404 console error on every page load.** Fixed by adding an inline SVG 🌱 favicon link to `mvp/frontend/index.html` and `mvp/frontend/farmer-dashboard.html`. Re-run confirms the 404 is gone.
2. **Dashboard subtext stale when logged in.** The dashboard always said "Sign in as a farmer to see your listings", even after login (greeting correctly said "Good Morning, Test Farmer!"). Fixed: when a user is logged in, the subtext now reads "Your farm at a glance. Here are your listings, prices and orders."

Both fixes committed locally to branch `integration` as `4ec07bc` (2 files, 3 insertions, 3 deletions) in `~/workspace/kisan-direct-ai-audit/repo/`. **Not pushed, not merged, not deployed** — per instructions. Browser suite re-run after the fixes: 26/26 passed. Pytest re-run: 8/8 passed.

## What remains untested / open

- **Emergent demo:** not browser-tested in this run (task scope was the integrated local app; the demo is a remote preview URL and was not modified). A live-browser pass on the demo is still needed for the comparison.
- **Standalone homepage/auth pages:** not exercised in the browser in this run (auth modal on the marketplace was tested; the standalone `standalone-pages/` files were verified only by link checks in the audit). The standalone auth page now calls the backend, but its browser flow was not driven here.
- **Docker:** prepared in the integration work, not built/run end-to-end (stated in INTEGRATION-REPORT.md).
- **Real buyer matching, pre-harvest, logistics, negotiation, FPO, multilingual beyond auth:** still not implemented; unchanged from the integration report. Do not claim them.
- Test DB now contains the browser-test users/listings/order from the second run (test data only). The running backend was restarted once with a fresh seeded DB to reset test users between runs.

## Addendum — 2026-11-13, final re-run against the repo tree

- The suite was re-run against the code in this repo (branch `integration`, after the favicon/dashboard fixes and the README update): **26 passed, 0 failed**, same counts as above. Only console error is the intentional 401 from the wrong-password test.
- `test_browser.py` in this repo is portable: it uses Playwright's default Chromium unless `PLAYWRIGHT_CHROME_PATH` is set, and writes screenshots/results next to itself.
- Correction to the "What remains untested" section above: the Emergent demo WAS browser-tested separately on 2026-11-13. It is a frontend-only prototype with no login/register, no backend, and sample data only; its AI price advisor gives a sample result, not a live ML prediction.
