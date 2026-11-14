# Kisan Direct AI — Deployment Guide

Public demo deployment for Team TerraCore, GeNarrative Clash 2026.
Status: **prepared, not deployed.** Nothing in this guide has been run
against a live platform yet. Do not treat the steps below as verified
until someone has run them and filled in the "Launch log" at the end.

## 1. Architecture (primary)

```
                         HTTPS (Fly proxy, Let's Encrypt)
  Judge / visitor ──────────► https://kisan-direct-ai.fly.dev
                                     │
                        ┌────────────▼────────────┐
                        │  Fly.io Machine (1x)  │
                        │  shared-cpu-1x, 512MB │
                        │                         │
                        │  FastAPI (uvicorn)    │
                        │   ├─ /api/*           │
                        │   ├─ /api/health      │
                        │   └─ /  (serves the   │
                        │       whole website,  │
                        │       same origin:    │
                        │       / homepage,     │
                        │       /auth,          │
                        │       /marketplace,   │
                        │       /dashboard)     │
                        │                         │
                        │  SQLite ──► /data/    │
                        │  kisan_direct.db      │
                        └────────────┬────────────┘
                                     │ Fly Volume
                              kisan_data (1 GB)
```

One app, one machine, one volume. This is deliberate:

- **Single origin.** The backend serves the whole website (`KISAN_SERVE_FRONTEND=1`,
  on by default in dev and production), so there is no separate frontend
  host, no CORS problem in the demo, and no second service to keep awake.
  Routes: `/` homepage, `/auth` login/register (`/login` redirects here),
  `/marketplace` marketplace, `/dashboard` farmer dashboard. `/api/*`
  always takes priority over the pages, and unknown `/api/*` paths 404
  instead of returning HTML. The frontend calls `location.origin`
  in production, or `window.KISAN_API_URL` if you set it in a `<script>`
  tag before `app.js` (only needed for a separately hosted frontend).
  The standalone auth page maps a 10-digit phone number to a login id
  `9876543210@phone.kisan.direct` (the old `@kisan.local` mapping was
  rejected by the backend's email validation — `.local` is a reserved
  special-use name).
- **SQLite stays.** The app was built on SQLite and all tests run against
  it. Migrating to Postgres for a hackathon demo would be a new,
  untested database layer. SQLite on a Fly volume is the honest choice
  for a single-instance demo, with the limits below.
- **Single instance only.** A Fly volume is attached to one machine.
  Do not scale to 2 machines: the second machine would get an empty
  database and the two would diverge. `fly.toml` sets
  `min_machines_running = 1` and `auto_stop_machines = "off"`.

### Why Fly.io (and what it costs)

Prices below are from Fly.io's own resource pricing page
(https://fly.io/docs/about/pricing/), read 2026-11-13. Re-check them
at launch time; Fly changes prices.

| Item | Cost |
| --- | --- |
| shared-cpu-1x, 512 MB, always on, `bom` (Mumbai) | about $3.69/month at `iad` rates; `bom` prices are higher than `iad`, so expect roughly $4–5/month — verify with `flyctl` / the dashboard at launch |
| 1 GB volume | $0.15/month |
| Shared IPv4 + IPv6 | $0 |
| First 10 single-hostname SSL certificates | $0 |
| Outbound data, India (APAC) | $0.12/GB (a demo uses megabytes) |
| **Expected total** | **roughly $4–5/month** |

Two things make this effectively free for a short demo, both from
Fly.io's own page:

1. **No free tier for new organisations.** New accounts get a $1
   credit trial for 7 days, no card needed to start. After the trial,
   a card is required to keep billable resources.
2. **Bills under $5 are waived.** Fly.io: "if your personal
   organization's monthly bill comes to less than $5, we waive it."
   A 512 MB machine + 1 GB volume in the cheapest region is under $5,
   so a personal-organisation demo bill is normally waived. This is
   not a promise: it applies to a *personal* organisation, and Fly
   can change it. Check the first invoice.

Why 512 MB and not the cheapest 256 MB ($2.19/month)? Measured
locally, the backend uses about **207 MB RSS just after startup**
(scikit-learn + two RandomForest models). 256 MB leaves almost no
headroom for request spikes and risks an out-of-memory kill during
judging. 512 MB is the safe minimum.

### Fallback: Render (free, but not suitable for a persistent demo)

Verified against Render's own free-tier docs (https://render.com/docs/free),
read 2026-11-13:

- Free web service: $0, 512 MB, but it **spins down after 15 minutes
  without traffic** and takes about a minute to wake. Bad for a live
  judging demo.
- **Ephemeral filesystem:** a SQLite file is **lost on every redeploy,
  restart, or spin-down** on a free service. Free services cannot
  attach a persistent disk. So a free Render deploy would lose every
  account, listing, and order after 15 idle minutes.
- Free Postgres: 1 GB, one per workspace, and it **expires 30 days
  after creation** (14-day grace period to upgrade, then it is deleted).
  It would also need a Postgres migration of the app, which has not
  been done or tested.
- Paid Render would be $7/month for the smallest always-on web
  service plus $0.25/GB/month for a disk (10 GB minimum, $2.50/month),
  or $6/month for the smallest paid Postgres.

Use Render only as a $0 *preview* (accepting that data vanishes),
never as the judged demo. Fly.io is the primary recommendation.

## 2. Environment variables

Set these as **platform secrets, never in a committed file**.
On Fly.io: `fly secrets set KEY=value` (see §3). In Docker Compose:
a local `.env` file (never committed).

| Variable | Required in production? | What it does |
| --- | --- | --- |
| `KISAN_ENV` | Yes, set to `production` | Turns on fail-fast checks, turns docs off, seed off, frontend serving on |
| `KISAN_SECRET_KEY` | Yes | JWT signing secret, at least 32 chars, not a placeholder. Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Without it, the app **refuses to start** |
| `KISAN_CORS_ORIGINS` | Yes | Public frontend origin(s), comma-separated, e.g. `https://kisan-direct-ai.fly.dev`. No `*`, no localhost in production; the app refuses to start otherwise |
| `KISAN_JWT_MINUTES` | No (default 720) | JWT session lifetime in minutes |
| `KISAN_SEED_DEMO_DATA` | No (default `0` in production) | `1` creates the demo accounts on first run with an empty DB. Leave `0` unless you deliberately want the public demo accounts |
| `KISAN_ENABLE_DOCS` | No (default `0` in production) | `1` re-enables `/docs`, `/redoc`, `/openapi.json`. Leave `0` |
| `KISAN_SERVE_FRONTEND` | No (default `1` everywhere) | `1` serves the whole website from the backend at `/`, `/auth`, `/marketplace`, `/dashboard` |
| `KISAN_DB_PATH` | No (set by `fly.toml` to `/data/kisan_direct.db`) | SQLite file path |
| `KISAN_PREDICT_RATE_LIMIT` | No (default 60) | Predict requests per minute per IP |

### Demo accounts — not real accounts

If seeding is enabled, these demo accounts are created on first run
with an empty database:

- Farmer: `ramesh@example.com` / `demo1234`
- Customer: `buyer@example.com` / `demo1234`

They are **sample accounts for a hackathon demo**, with the password
`demo1234` published in this repo's docs and tests. Never present
them as real accounts, never reuse the password anywhere else, and
leave `KISAN_SEED_DEMO_DATA=0` in production unless the team
deliberately wants judges to log in with them. With seeding off,
the public site starts with an empty marketplace and anyone can
register their own farmer/customer account.

## 3. Launch steps (Fly.io)

Do this from a machine with `flyctl` installed. Nothing here deploys
from this repo automatically.

```bash
# 0. Install flyctl (macOS/Linux) and log in
curl -L https://fly.io/install.sh | sh
fly auth login

# 1. From the repo root, on branch deployment-prep (after its PR merges)
fly launch --no-deploy
#    - App name: kisan-direct-ai (or your own name; update fly.toml
#      and KISAN_CORS_ORIGINS to match)
#    - Region: bom (Mumbai, closest to Indian judges/users)
#    - Do NOT add a Postgres database when asked (we use SQLite)
#    - Do NOT deploy yet

# 2. Create the persistent volume (1 GB is plenty for a demo)
fly volumes create kisan_data --size 1 --region bom

# 3. Set secrets (replace the URL with your real app URL)
fly secrets set KISAN_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
fly secrets set KISAN_CORS_ORIGINS="https://kisan-direct-ai.fly.dev"

# 4. Deploy
fly deploy

# 5. Check status and logs
fly status
fly logs
curl -s https://kisan-direct-ai.fly.dev/api/health
#    expected: {"status":"ok"}
```

### HTTPS and custom domain

- The `*.fly.dev` URL gets HTTPS automatically (Fly provisions a
  Let's Encrypt certificate; the first 10 single-hostname certs are
  free). `fly.toml` sets `force_https = true`, and the app sends
  `Strict-Transport-Security` in production.
- Custom domain (optional): buy/configure a domain, then
  `fly certs add yourdomain.com` and point a CNAME at
  `kisan-direct-ai.fly.dev`. Fly issues the certificate; check it
  with `fly certs show yourdomain.com`. If you use a custom domain,
  add it to `KISAN_CORS_ORIGINS` as well
  (e.g. `https://kisan-direct-ai.fly.dev,https://yourdomain.com`).

## 4. Verify the public demo end to end

Run these against the public URL (replace the host). Every step
must pass before the demo is shown to judges.

```bash
BASE=https://kisan-direct-ai.fly.dev

# 1. Health and docs
curl -s $BASE/api/health            # {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" $BASE/docs   # 404 (docs off)

# 2. Whole website loads from the same origin
curl -s $BASE/ | grep -o "Sell Smarter" | head -1
curl -s $BASE/auth | grep -o "Kisan Portal" | head -1
curl -s $BASE/marketplace | grep -o "AI Farmer Marketplace" | head -1
curl -s $BASE/dashboard | grep -o "Farmer Dashboard" | head -1
curl -s -o /dev/null -w "%{http_code}\n" $BASE/login   # 302 -> /auth
curl -s -o /dev/null -w "%{http_code}\n" $BASE/api/nope  # 404, not HTML

# 3. In a browser, the full journey: start at /, follow the nav to
#    /marketplace, go to /auth, register a farmer (redirects to
#    /dashboard), check the dashboard, go to /marketplace, create a
#    listing, log out, register a customer on /auth (redirects to
#    /marketplace), place an order, check My Orders, try a price
#    prediction (expect about ₹27.33/kg for Tomato/Winter/Kolkata)
#    and a demand prediction (expect Medium, index about 166.9).
#    Wrong password must be rejected on /auth. An unauthenticated
#    visit to /dashboard must show a login prompt, and a customer
#    visiting /dashboard must see a "farmer accounts only" message.

# 4. Mobile: open the same URL on a phone-width viewport (390px);
#    the homepage, auth, marketplace, and dashboard must all load
#    with no horizontal overflow.
```

If seeding was enabled, also log in as the demo farmer
`ramesh@example.com` / `demo1234` and confirm the 3 sample listings
(Tomato, Potato, Onion) are visible.

## 5. Rollback

- **Redeploy the previous release:** `fly releases` lists releases,
  then `fly deploy --image <previous-image>` or
  `fly releases rollback <version>` (check `fly releases --help` on
  the deploy machine; the exact flag varies by flyctl version).
- **Redeploy the previous commit:** check out the previous `main`
  commit locally and run `fly deploy` again.
- **Data rollback:** the SQLite file lives on the volume. Before a
  risky deploy, back it up with
  `fly ssh console -C "cp /data/kisan_direct.db /data/kisan_direct.db.bak"`.
  Fly also takes automatic daily volume snapshots (5 days retention);
  snapshot storage is $0.08/GB/month, first 10 GB free.
- **Kill switch:** `fly scale count 0` stops the machine (the volume
  and its data stay). `fly scale count 1` brings it back.

## 6. Local Docker run (optional, for testing the image)

```bash
# From the repo root. Needs a .env file with KISAN_SECRET_KEY set.
cp .env.example .env   # then edit .env and set a real secret
docker compose up --build
# Backend + frontend at http://127.0.0.1:8000 (same origin)
# Note: docker-compose.override.yml switches this to dev mode.
# For a production-like local run: docker compose -f docker-compose.yml up --build
```

Docker build has **not** been verified in this environment: there is
no Docker or Podman binary here, and `apt` has no `docker.io` package
to install (`apt-cache policy docker.io` is empty), so no image has
ever been built. The first `fly deploy` uses Fly's remote builder; if
the build fails, read the builder log before changing the Dockerfile.
What WAS checked instead: the exact file layout the Dockerfile
produces (`main.py` + `frontend/` + `standalone-pages/` in one
directory, as the image has it) was copied to a clean directory and
run with production env vars — all of `/`, `/auth`, `/marketplace`,
`/dashboard`, `/api/health` returned 200 and `/docs` returned 404.
That proves the app finds its pages in the container layout, but it
is not a Docker build.

## 7. What is still NOT production-ready

Say this plainly to judges; do not claim otherwise.

- **Synthetic ML data.** Price/demand models are RandomForests trained
  on 5,000 generated rows. They are demo estimates, not live mandi
  prices. No real market data, no payments, no logistics.
- **No real buyer matching.** `/api/buyers` returns a fixed sample
  list labelled demo data. There is no matching algorithm.
- **Single instance, SQLite.** One machine, one volume. No horizontal
  scaling, no managed backups beyond Fly snapshots, no failover.
  Concurrent-write load has not been tested; SQLite handles a demo,
  not a marketplace.
- **Auth is basic.** JWT + bcrypt, no email verification, no password
  reset, no account lockout beyond the 20/min login rate limit.
  Anyone can register unlimited accounts.
- **No admin, no moderation.** Listings and orders have no review
  flow; there is no way to remove a bad listing except from the DB.
- **Pre-harvest listing, negotiation, FPO support, and multilingual
  support beyond the auth page are not implemented.**
- **No monitoring/alerting.** Fly logs only. No uptime check is
  configured; add one (e.g. a free uptime monitor hitting
  `/api/health`) before judging day.

## 8. Files changed for deployment

- `mvp/backend/main.py` — production fail-fast config, docs off by
  default, opt-in seeding, predict rate limiting, security headers,
  same-origin website serving (`/` homepage, `/auth`, `/login` ->
  `/auth`, `/marketplace`, `/dashboard`, legacy file URLs redirect),
  `KISAN_DB_PATH`, per-path rate limits.
- `mvp/frontend/app.js`, `mvp/frontend/farmer-dashboard.html`,
  `standalone-pages/auth/auth.html`, `standalone-pages/homepage/homepage.html`
  — absolute asset/API paths, real journey links, auth page with a
  farmer/customer role selector and role-based redirects, dashboard
  login prompt for visitors and a farmer-only message for customers.
- `mvp/backend/Dockerfile` — pinned `python:3.12.13-slim`, non-root
  user, no `.env` in the image, healthcheck, `$PORT` support, now
  also copies `standalone-pages/` into the image.
- `.dockerignore` — secrets, DBs, venvs, tests, and git never enter
  the image.
- `docker-compose.yml` / `docker-compose.override.yml` — production
  single-service compose plus a dev override.
- `fly.toml` — app, region `bom`, 512 MB machine, 1 GB volume,
  health check, `force_https`.
- `.env.example` — every variable documented, no real secret.
- `tests/test_production.py` + `tests/prod_probe.py` — production
  smoke tests (see below).
- `PUSH-FROM-LAPTOP.md` — removed (it was deploy instructions for
  the last PR, not part of the project).

## 9. Launch log (fill in at launch time)

- [ ] `fly launch` done, app name: _______________
- [ ] Volume created: _______________
- [ ] Secrets set (secret value NOT recorded here): _______________
- [ ] First deploy: _______________ (date/time, flyctl version)
- [ ] `curl /api/health` → `{"status":"ok"}`: _______________
- [ ] Browser end-to-end check passed: _______________
- [ ] First invoice checked (expected under $5, waived if personal org): _______________
