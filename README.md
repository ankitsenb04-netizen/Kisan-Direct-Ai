# Kisan Direct AI — Hackathon Source Code

Kisan Direct AI is a hackathon concept for connecting farmers and customers, with a demonstration marketplace and AI-assisted crop price and demand estimates.

## Repository layout

- **`mvp/`** — Original runnable marketplace MVP: vanilla HTML/CSS/JS frontend, FastAPI backend, SQLite, and scikit-learn demonstration models. See [`mvp/README.md`](mvp/README.md) for setup.
- **`standalone-pages/homepage/`** — Separately designed marketing homepage (`homepage.html` and `homepage.css`).
- **`standalone-pages/auth/`** — Separately designed login/registration page (`auth.html`, with inline CSS/JS).

**Integration status:** These are separate source-code deliverables. The standalone homepage and authentication page have **not** been integrated into the MVP or with each other. Some navigation links in the standalone pages point to filenames outside their own folders and will not resolve in this layout. The homepage's action buttons are design-only. The standalone authentication demo stores credentials in browser localStorage; **do not use real passwords**. The MVP has its own separate login/register implementation.

## Run the MVP locally

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

Open http://127.0.0.1:5500 in your browser.

## View the standalone designs

Open `standalone-pages/homepage/homepage.html` or `standalone-pages/auth/auth.html` in a browser. These are **independent demos**, not part of the running MVP. The homepage uses externally hosted imagery and Font Awesome icons, so an internet connection may be needed for its full appearance.

## Notes for hackathon reviewers

- MVP price and demand models use **synthetic demonstration data**, not live mandi/APMC data. Predictions are not financial or agricultural advice.
- Marketing impact figures in the standalone homepage are **unverified placeholder claims**, not measured results.
- The standalone authentication page uses insecure client-side credential storage; it is a UI prototype only.
- Authentication/security and production deployment need further work before real-world use.

This repository preserves the provided source-code versions separately, without attempting to integrate or refactor them.
