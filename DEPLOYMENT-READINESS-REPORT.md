# Kisan Direct AI — Deployment Readiness Report

Date: 2026-11-13
Repo: https://github.com/ankitsenb04-netizen/Kisan-Direct-Ai
Branch: `deployment-prep`, commit `7a1300f` (off merged main `9440534`)
Status: **prepared, NOT deployed, NOT pushed, NOT merged.**
Full deployment guide (in the branch): `DEPLOYMENT.md`.

## 1. Main vs local diff (step 1)

Local `integration` branch was at `8a7377c`. After `git fetch origin`,
merged main `9440534` (merge of PR #1, head `1c8ef3b`) was compared
file by file against `8a7377c`:

- **Code: identical.** `git diff origin/main 8a7377c -- mvp/backend/main.py
  mvp/frontend/ README.md tests/` is empty.
- **Only difference: `PUSH-FROM-LAPTOP.md`** — present in main (the
  user committed the ZIP-only instructions file when pushing from his
  laptop), absent locally. It is deleted on `deployment-prep` because
  it is not part of the project.
- The local `main` branch pointer was stale at `40bfc6f`; all
  comparisons above use `origin/main` (`9440534`). Main is the source
  of truth, and `deployment-prep` was created off it.

## 2. Verification against merged main (before hardening)

- pytest `tests/test_integration.py`: **8 passed, 0 failed.**
- Playwright `browser-tests/test_browser.py` (Chrome for Testing
  158.0.8127.18, desktop 1280x800 + mobile 390x844): **26 passed,
  0 failed.** Only console error is the intentional 401 from the
  wrong-password test.
- No bugs were found in the merged main code itself. The bugs below
  were found by the *production* checks, not by the functional tests.

## 3. Bugs found and fixed on deployment-prep

All found while hardening for production, all verified by the new
production smoke tests and by re-running the full suites.

1. **Rate-limit bucket shared across endpoints.** `rate_limit()` was
   keyed by IP only, so a login attempt ate the predict budget (the
   predict test saw `[200, 200, 429, 429]` instead of
   `[200, 200, 200, 429]`). Fixed: key is now IP + path.
2. **Static frontend mount shadowed by the JSON home route.**
   `GET /` returned JSON even with `KISAN_SERVE_FRONTEND=1`, because
   the `@app.get("/")` route was registered before the mount.
   Fixed: the JSON home route is only registered when frontend
   serving is off; with it on, `GET /` serves `index.html`.
   Verified live: same-origin backend on port 8001 returned
   `200 text/html` containing "Kisan Direct" for `GET /`, and
   `/api/health` returned `{"status":"ok"}`.
3. **`.env.example` placeholder secret would have passed the
   production check.** The example value
   `replace-with-a-long-random-secret-at-least-32-chars` is 49 chars
   and was not in the placeholder list. Fixed: the exact string is
   now rejected, and any secret containing `change-me` or
   `replace-with` is rejected. Covered by a new smoke test.
4. **Empty `KISAN_DB_PATH` broke the DB path.** `os.environ.get(
   "KISAN_DB_PATH", default)` returns `""` when the variable is set
   but empty (as in `.env.example`), and `Path("")` is `.`.
   Fixed: empty values now fall back to the default path.
5. **Frontend API URL hardcoded to localhost in 3 places**
   (`mvp/frontend/app.js`, `mvp/frontend/farmer-dashboard.html`,
   `standalone-pages/auth/auth.html`). A public deployment would
   have made every API call fail. Fixed: `window.KISAN_API_URL`
   override, same origin (`location.origin`) in production,
   `http://127.0.0.1:8000` in local dev. Local browser tests still
   pass unchanged.

## 4. Verification after hardening (final numbers)

| Suite | Result |
| --- | --- |
| pytest `tests/test_integration.py` | 8 passed, 0 failed |
| pytest `tests/test_production.py` (new) | 9 passed, 0 failed |
| **pytest total** | **17 passed, 0 failed** |
| Playwright `browser-tests/test_browser.py` (fresh DB, hardened code) | **26 passed, 0 failed** (desktop + mobile; registration, login, farmer dashboard, marketplace, listings, ordering, AI predictions, mobile responsiveness) |
| Same-origin serving (manual curl check) | `GET /` 200 HTML, `/api/health` `{"status":"ok"}` |

Only console error in the browser run is the intentional 401 from
the wrong-password test. Local test servers were stopped afterwards.
Backend memory measured at startup: about **207 MB RSS**
(scikit-learn + two RandomForest models). First startup takes about
15 seconds (model training); Fly health-check grace is 60s.

## 5. Architecture recommendation

**Primary: one Fly.io app** — FastAPI backend serving the API and the
marketplace frontend from the same origin, SQLite on a 1 GB
persistent volume, Mumbai (`bom`) region, `shared-cpu-1x` 512 MB,
always on, HTTPS automatic. Full details, launch steps, env vars,
verification, and rollback in `DEPLOYMENT.md`.

Costs (Fly.io's own pricing page, https://fly.io/docs/about/pricing/,
read 2026-11-13; re-check at launch):

- 512 MB shared-cpu-1x: $3.69/month at `iad` rates; `bom` is higher,
  expect roughly $4-5/month total with the 1 GB volume ($0.15/month).
- Shared IPv4 + IPv6: $0. First 10 single-hostname SSL certs: $0.
  Outbound data in India: $0.12/GB (a demo uses megabytes).
- **No free tier for new organisations.** $1 credit trial, 7 days,
  no card to start; a card is required afterwards.
- **Bills under $5 are waived** for a personal organisation (Fly.io's
  own page). A tiny demo bill is normally waived, but this is not
  guaranteed — check the first invoice.
- 512 MB, not 256 MB ($2.19/month), because the backend already uses
  ~207 MB RSS at startup; 256 MB risks an out-of-memory kill.

**Fallback: Render free** — verified against Render's own free-tier
docs (https://render.com/docs/free, read 2026-11-13). Not recommended
for the judged demo: free web services spin down after 15 idle
minutes (~1 minute to wake), the filesystem is ephemeral so a SQLite
file is **lost on every redeploy/restart/spin-down**, free services
cannot attach a persistent disk, and free Postgres expires 30 days
after creation. Paid Render would be $7/month (web service) +
$2.50/month (10 GB disk) or $6/month (smallest paid Postgres), and
would still need a Postgres migration that has not been done.

**DB decision: SQLite stays.** No migration was done. It is the
tested database, and it is correct for a single-instance demo on a
volume. Limits: one machine only (a volume cannot be shared), no
managed backups beyond Fly snapshots, no failover.

## 6. Files changed / added on deployment-prep (commit 7a1300f)

- `mvp/backend/main.py` — production fail-fast config, docs off by
  default, opt-in seeding, predict rate limiting, security headers,
  same-origin frontend serving, `KISAN_DB_PATH`, per-path rate limits.
- `mvp/frontend/app.js`, `mvp/frontend/farmer-dashboard.html`,
  `standalone-pages/auth/auth.html` — API URL now configurable.
- `mvp/backend/Dockerfile` — pinned `python:3.12.13-slim`, non-root
  user, no `.env` in the image, healthcheck, `$PORT` support,
  repo-root build context.
- `.dockerignore` (new) — secrets, DBs, venvs, tests, git never enter
  the image.
- `docker-compose.yml` — production single-service compose (named
  volume `kisan-data`).
- `docker-compose.override.yml` (new) — local dev override.
- `fly.toml` (new) — app, `bom`, 512 MB, 1 GB volume, health check,
  `force_https`.
- `.env.example` — every variable documented, no real secret.
- `DEPLOYMENT.md` (new) — architecture, verified pricing, launch
  steps, env vars, HTTPS/custom domain, verification, rollback,
  not-production-ready list.
- `tests/test_production.py` + `tests/prod_probe.py` (new) — 9
  production smoke tests.
- `README.md` — deployment pointer and test instructions.
- `PUSH-FROM-LAPTOP.md` — deleted (instructions file, not project).
- `browser-tests/RESULTS.md` — addendum with the re-run numbers.

## 7. Environment variables (production)

| Variable | Value to set |
| --- | --- |
| `KISAN_ENV` | `production` |
| `KISAN_SECRET_KEY` | Generated secret, 32+ chars, via `fly secrets set` (never in a file) |
| `KISAN_CORS_ORIGINS` | `https://kisan-direct-ai.fly.dev` (replace with the real app URL) |
| `KISAN_SEED_DEMO_DATA` | `0` (leave off unless demo accounts are wanted) |
| `KISAN_ENABLE_DOCS` | `0` |
| `KISAN_SERVE_FRONTEND` | `1` |
| `KISAN_DB_PATH` | `/data/kisan_direct.db` (set in fly.toml) |

Demo accounts, if seeding is enabled: `ramesh@example.com` /
`demo1234` (farmer), `buyer@example.com` / `demo1234` (customer).
They are published sample accounts, not real accounts.

## 8. Remaining blockers and risks

- **Not deployed.** No Fly.io account, app, volume, or secret exists
  yet. The launch steps in `DEPLOYMENT.md` §3 have not been run.
- **Docker build not verified.** No Docker is installed in this
  environment, so the image has never been built. The first
  `fly deploy` uses Fly's remote builder; a build failure there is
  the most likely first-launch problem. The Dockerfile is written
  carefully (pinned base, non-root, healthcheck) but unproven.
- **Prices are `iad`-based estimates for `bom`.** Fly's table is for
  Ashburn/Secaucus; Mumbai costs more. Expect roughly $4-5/month,
  verify on the first invoice, and confirm the under-$5 waiver
  applies to the account used.
- **Single-instance SQLite.** No scaling, no failover, no managed
  backups beyond Fly snapshots. Back up `/data/kisan_direct.db`
  before risky deploys.
- **Startup time ~15s** (model training on every start). Fly's
  health-check grace (60s) covers it, but the first request after a
  deploy is slow.
- **Still not production-ready** (see DEPLOYMENT.md §7): synthetic ML
  data, no real buyer matching/logistics/payments, no email
  verification or password reset, no moderation/admin, no
  monitoring/alerting. This is a hackathon demo, not a product.
- **Standalone homepage/auth pages are not served** by the backend;
  only the marketplace frontend is. They remain in the repo as
  design demos.
- The `integration` branch on GitHub still exists after the merge;
  deleting it is optional and was not done here.

---

# Addendum — Complete user journey (2026-11-13, branch deployment-prep)

## What changed

The production server previously served only the marketplace at `/`;
the standalone homepage and auth pages were not served. The backend
now serves the whole website from one origin, locally and in
production (`KISAN_SERVE_FRONTEND=1` is now the default in both):

| Route | Page |
| --- | --- |
| `/` | Original standalone homepage (`standalone-pages/homepage/`) |
| `/auth` | Working login/register page (`standalone-pages/auth/`); `/login` redirects here (canonical URL is `/auth`) |
| `/marketplace` | Marketplace (`mvp/frontend/index.html`) |
| `/dashboard` | Farmer dashboard (`mvp/frontend/farmer-dashboard.html`) |

`/api/*` always takes priority; unknown `/api/*` paths 404 as JSON
and never leak the homepage HTML. Legacy `/index.html` and
`/farmer-dashboard.html` redirect to `/marketplace` and `/dashboard`.
All pages use absolute asset paths (`/style.css`, `/app.js`,
`/homepage.css`), so nothing breaks at a sub-path. After login/register
on `/auth`, farmers go to `/dashboard` and customers to `/marketplace`.
Unauthenticated `/dashboard` shows a login prompt linking to `/auth`;
a logged-in customer sees a clear farmer-only message, not a crash.
JWT auth, order flow, ML predictions, production hardening, and
SQLite persistence are unchanged.

## Test counts

| Suite | Before (merged main) | After hardening | After journey fix |
| --- | --- | --- | --- |
| pytest `tests/test_integration.py` | 8 passed | 8 passed | 9 passed (new journey-routes test) |
| pytest `tests/test_production.py` | — | 9 passed | 9 passed (route assertions added) |
| **pytest total** | **8** | **17** | **18 passed, 0 failed** |
| Playwright `browser-tests/test_browser.py` | 26 passed | 26 passed | **38 passed, 0 failed** (full homepage-to-order journey, desktop + mobile) |

Playwright first run of the new journey suite: 21/27, then fixed and
re-run green at 38/38. Only console errors on the green run: 5x
`net::ERR_TUNNEL_CONNECTION_FAILED` (this VM's browser cannot reach
external Unsplash/Font Awesome resources through its network proxy;
no app resource failed) plus the intentional 401 from the
wrong-password test.

## Bugs found and fixed in the journey work

1. **Auth page phone login broken (real bug, never browser-tested
   before).** `auth.html` mapped a phone number to
   `9876543210@kisan.local`, but the backend's EmailStr validation
   rejects `.local` as a reserved special-use name, so every phone
   registration returned 422. Fixed to
   `9876543210@phone.kisan.direct` (verified by curl before the fix
   was applied). Login id only, not a real mailbox.
2. **Homepage and auth pages had no favicon** (404 console error).
   Fixed with inline SVG favicons.
3. **Dashboard had no handling for visitors/customers.** Fixed with
   a login-prompt banner (link to `/auth`) for visitors and a
   farmer-only banner for logged-in customers.
4. **Dockerfile did not copy `standalone-pages/`.** Fixed with
   `COPY standalone-pages/ ./standalone-pages/`.

## Docker verification

**Docker build is NOT verified.** There is no Docker or Podman binary
in this environment, and `apt` has no `docker.io` package
(`apt-cache policy docker.io` is empty; a dry-run install reports
"Unable to locate package docker.io"). Installing Docker from its own
repository was not attempted: it would need an external apt source,
a daemon, and is out of scope for this task. Substitute check done
instead: the exact file layout the Dockerfile produces (`main.py` +
`frontend/` + `standalone-pages/` in one directory) was copied to a
clean directory and run with production env vars (real test secret,
`KISAN_CORS_ORIGINS=https://example.com`, fresh DB): `/`, `/auth`,
`/marketplace`, `/dashboard`, `/api/health` all returned 200 and
`/docs` returned 404. That proves the app finds its pages in the
container layout; it is not a Docker build. The first `fly deploy`
(remote builder) remains the first real Docker build.

## Files changed in the journey commit (on top of 7a1300f)

`mvp/backend/main.py` (routing + `_site_dir` resolution),
`mvp/backend/Dockerfile`, `standalone-pages/homepage/homepage.html`,
`standalone-pages/auth/auth.html`, `mvp/frontend/index.html`,
`mvp/frontend/farmer-dashboard.html`, `tests/test_integration.py`,
`tests/test_production.py`, `tests/prod_probe.py`,
`browser-tests/test_browser.py`, `browser-tests/RESULTS.md`,
`browser-tests/results.json`, new screenshots
`01-homepage-desktop.png`–`11-marketplace-mobile.png`,
`DEPLOYMENT.md`, `README.md`, `.env.example`,
`docker-compose.override.yml`.

## Remaining blockers (unchanged, plus one)

- Not deployed, not pushed, not merged. No Fly.io account/app/volume/
  secret exists yet.
- Docker build not verified (see above); first `fly deploy` is the
  most likely first-launch failure point.
- Homepage external images (Unsplash) and Font Awesome load from
  third-party CDNs; if those CDNs are unreachable the page still
  works but loses its hero imagery/icons. The homepage impact figures
  (50K+ farmers, etc.) remain unverified placeholder claims.
- Single-instance SQLite, synthetic ML data, no real buyer matching/
  logistics/payments, no email verification/password reset.
