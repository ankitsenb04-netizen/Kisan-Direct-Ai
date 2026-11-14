# Kisan Direct AI — Hackathon Source Code

Kisan Direct AI is a hackathon concept for connecting farmers and customers, with a demonstration marketplace and AI-assisted crop price and demand estimates.

Team TerraCore, GeNarrative Clash 2026.

## Integration status (branch `deployment-prep`)

The homepage, authentication page, and marketplace MVP are now integrated into one app, served from **one origin** by the backend — the same routes locally and in production:

- `/` — the original standalone homepage, with working nav to the marketplace, dashboard, and login/register.
- `/auth` — the working login/register page (phone or email, EN/HI toggle, farmer/customer account type). `/login` redirects here. After login/register, farmers go to `/dashboard` and customers go to `/marketplace`.
- `/marketplace` — the marketplace. Farmers get a Dashboard link and can list produce, customers get a Buy button and a My Orders section.
- `/dashboard` — the farmer dashboard. It shows My Produce, Market Price Intelligence, an AI Selling Advisor, Top Buyer Matches (labelled "Sample buyers (demo data)", there is no matching algorithm yet), and Active Deliveries. Visitors who are not logged in see a login prompt with a link to `/auth`; logged-in customers see a clear "farmer accounts only" message instead of a crash.
- One session: register and log in once, with a JWT token (`kdToken`) stored in the browser. No passwords are stored in localStorage. The marketplace auth modal, the standalone auth page, and the dashboard all use the same token and the same `/api/login` and `/api/register` endpoints.
- Ordering works: `POST /api/orders` and `GET /api/orders` are backed by the orders table, and ordering decrements the listing quantity.
- Security: bcrypt password hashing (legacy unsalted SHA-256 rows are re-hashed on login), JWT auth with `farmer_id` derived server-side from the token, CORS restricted to the real frontend origin(s) via `KISAN_CORS_ORIGINS` (required in production, no `*`, no localhost), rate limiting on login/register (20/min per IP) and on predictions, and foreign keys enforced. In production (`KISAN_ENV=production`) the app refuses to start without a real 32+ character `KISAN_SECRET_KEY`, `/docs` is off by default, and demo seeding is off unless explicitly enabled. See `.env.example` for `KISAN_SECRET_KEY`.
- Seed demo data on first run with an empty database (opt-in in production, on by default in dev): farmer Ramesh (`ramesh@example.com` / `demo1234`), demo buyer (`buyer@example.com` / `demo1234`), and 3 listings (Tomato, Potato, Onion).

## Repository layout

- **`mvp/`** — Runnable marketplace MVP: vanilla HTML/CSS/JS frontend, FastAPI backend, SQLite, and scikit-learn demonstration models. See [`mvp/README.md`](mvp/README.md) for setup.
- **`mvp/backend/`** — FastAPI backend, plus `Dockerfile` for containerised runs.
- **`standalone-pages/homepage/`** — Marketing homepage (`homepage.html` and `homepage.css`), now branded "Kisan Direct" and linked to the real marketplace and auth pages.
- **`standalone-pages/auth/`** — Login/registration page (`auth.html`), now wired to the backend.
- **`tests/`** — Pytest API tests (`test_integration.py`, 9 passed, including the journey routes) and production smoke tests (`test_production.py`, 9 passed), plus the Playwright live-browser suite (`browser-tests/test_browser.py`, 38 passed, 0 failed, desktop 1280x800 and mobile 390x844, full homepage-to-order journey). Browser results and screenshots are in `browser-tests/`.
- **`docker-compose.yml`** — Backend + frontend compose setup (prepared, not yet run end-to-end).

## Run locally

The backend serves the whole website from one origin, so one server
is enough (same as production). From the repository root:

```bash
cd mvp/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000/ in your browser:

- Homepage: http://127.0.0.1:8000/
- Login/register: http://127.0.0.1:8000/auth
- Marketplace: http://127.0.0.1:8000/marketplace
- Farmer dashboard: http://127.0.0.1:8000/dashboard (log in as a farmer first)
- API docs (dev only): http://127.0.0.1:8000/docs

Delete `mvp/backend/kisan_direct.db` for a fresh database (demo seed
data is created on first run in dev).

## Tests

```bash
python3 -m pytest tests/test_integration.py tests/test_production.py -v
```

`test_integration.py` (9 tests) covers the API and the journey routes
in dev mode. `test_production.py` (9 tests) runs the app in a
subprocess per scenario and checks the production fail-fast behaviour:
no secret / placeholder secret / no CORS / wildcard CORS all refuse
to start, docs off by default, demo seeding off by default, CORS
allows only a listed origin, security headers, same-origin website
serving, and predict rate limiting. The Playwright browser suite
(`browser-tests/test_browser.py`, 38 checks) needs the backend
running on 127.0.0.1:8000 with a fresh database; see its header.

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md). Primary architecture: one Fly.io
app (shared-cpu-1x, 512 MB, Mumbai region), backend serving the API
and the frontend from the same origin, SQLite on a 1 GB persistent
volume. Roughly $4-5/month before Fly's under-$5 waiver; no free tier
for new accounts, $1 trial credit for 7 days. **Not deployed yet.**
Set a real `KISAN_SECRET_KEY` as a platform secret before any
non-localhost use; the app refuses to start in production without one.

## Notes for hackathon reviewers

- MVP price and demand models use **synthetic demonstration data**, not live mandi/APMC data. Predictions are not financial or agricultural advice.
- Marketing impact figures in the standalone homepage are **unverified placeholder claims**, not measured results.
- Not implemented: pre-harvest listing, real AI buyer matching, logistics, negotiation, and FPO support. Do not claim them.
- Local dev uses plain HTTP and a dev-only default secret if `KISAN_SECRET_KEY` is not set. In production the app refuses to start without a real secret, `/docs` is off by default, and predictions are rate-limited. Set a real secret and use HTTPS before any non-localhost use; see [DEPLOYMENT.md](DEPLOYMENT.md).
