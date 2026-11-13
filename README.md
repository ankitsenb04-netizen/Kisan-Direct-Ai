# Kisan Direct AI — Hackathon Source Code

Kisan Direct AI is a hackathon concept for connecting farmers and customers, with a demonstration marketplace and AI-assisted crop price and demand estimates.

Team TerraCore, GeNarrative Clash 2026.

## Integration status (branch `integration`)

The homepage, authentication page, and marketplace MVP are now integrated into one app:

- One session: register and log in once, with a JWT token (`kdToken`) stored in the browser. No passwords are stored in localStorage.
- The standalone auth page (`standalone-pages/auth/auth.html`) now calls the real backend (`POST /api/register`, `POST /api/login`), keeping its EN/HI toggle.
- The marketplace frontend (`mvp/frontend/`) is token-based: farmers get a Dashboard link and can list produce, customers get a Buy button and a My Orders section.
- Ordering works: `POST /api/orders` and `GET /api/orders` are backed by the orders table, and ordering decrements the listing quantity.
- A farmer dashboard (`mvp/frontend/farmer-dashboard.html`) shows My Produce, Market Price Intelligence, an AI Selling Advisor, Top Buyer Matches (labelled "Sample buyers (demo data)", there is no matching algorithm yet), and Active Deliveries.
- Security: bcrypt password hashing (legacy unsalted SHA-256 rows are re-hashed on login), JWT auth with `farmer_id` derived server-side from the token, CORS restricted to `http://127.0.0.1:5500` and `http://localhost:5500` by default, rate limiting on login/register (20/min per IP), and foreign keys enforced. See `.env.example` for `KISAN_SECRET_KEY`.
- Seed demo data on first run with an empty database: farmer Ramesh (`ramesh@example.com` / `demo1234`), demo buyer (`buyer@example.com` / `demo1234`), and 3 listings (Tomato, Potato, Onion).

## Repository layout

- **`mvp/`** — Runnable marketplace MVP: vanilla HTML/CSS/JS frontend, FastAPI backend, SQLite, and scikit-learn demonstration models. See [`mvp/README.md`](mvp/README.md) for setup.
- **`mvp/backend/`** — FastAPI backend, plus `Dockerfile` for containerised runs.
- **`standalone-pages/homepage/`** — Marketing homepage (`homepage.html` and `homepage.css`), now branded "Kisan Direct" and linked to the real marketplace and auth pages.
- **`standalone-pages/auth/`** — Login/registration page (`auth.html`), now wired to the backend.
- **`tests/`** — Pytest API tests (`test_integration.py`, 8 passed) and the Playwright live-browser suite (`browser-tests/test_browser.py`, 26 passed, 0 failed, desktop 1280x800 and mobile 390x844). Browser results and screenshots are in `browser-tests/`.
- **`docker-compose.yml`** — Backend + frontend compose setup (prepared, not yet run end-to-end).

## Run locally

From the repository root, open two terminals.

**Terminal 1 — backend:**

```bash
cd mvp/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend: http://127.0.0.1:8000 — API docs: http://127.0.0.1:8000/docs

**Terminal 2 — frontend:**

```bash
cd mvp/frontend
python3 -m http.server 5500
```

Open http://127.0.0.1:5500 in your browser. Farmer dashboard: http://127.0.0.1:5500/farmer-dashboard.html (log in as a farmer first).

## Tests

```bash
python3 -m pytest tests/test_integration.py -v
```

## Notes for hackathon reviewers

- MVP price and demand models use **synthetic demonstration data**, not live mandi/APMC data. Predictions are not financial or agricultural advice.
- Marketing impact figures in the standalone homepage are **unverified placeholder claims**, not measured results.
- Not implemented: pre-harvest listing, real AI buyer matching, logistics, negotiation, and FPO support. Do not claim them.
- Localhost only: plain HTTP, a dev default secret if `KISAN_SECRET_KEY` is not set, public `/docs`, and no rate limiting on the prediction endpoints. Set a real secret and use HTTPS before any non-localhost use.
