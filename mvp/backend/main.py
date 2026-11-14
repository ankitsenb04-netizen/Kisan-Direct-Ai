"""Kisan Direct AI API — integrated build (Team TerraCore, GeNarrative Clash 2026).

Based on the audited MVP (commit 40bfc6f). Changes in this integration build:
- bcrypt password hashing (replaces unsalted SHA-256; old SHA-256 rows are
  re-hashed with bcrypt on next successful login).
- JWT Bearer sessions; POST /api/products and /api/orders now derive the
  user from the verified token instead of a client-supplied farmer_id.
- New order flow: POST /api/orders, GET /api/orders (backed by the existing
  orders table, previously dead code).
- CORS restricted to the real frontend origin(s) via env (default localhost:5500).
- Simple in-memory rate limiting on login/register.
- Seed demo data on first run (demo farmer Ramesh + sample listings/buyers,
  clearly labelled demo data) and GET /api/buyers (sample buyers only —
  real AI buyer matching is NOT implemented yet).
- EmailStr validation, upper bounds, FK enforcement, global error handler.
- ML models unchanged: RandomForest price/demand on synthetic data.

Production hardening (see DEPLOYMENT.md):
- KISAN_ENV=production requires a real KISAN_SECRET_KEY (>= 32 chars, not a
  placeholder); otherwise the app refuses to start. Dev keeps the old
  dev-only default, with a loud warning.
- In production, KISAN_CORS_ORIGINS is required, and wildcards and
  localhost origins are rejected. /docs and /openapi.json are off by
  default in production (KISAN_ENABLE_DOCS=1 to turn them back on).
- Demo seed data is opt-in: KISAN_SEED_DEMO_DATA=1. It defaults ON in
  dev and OFF in production, so the demo accounts are never created in
  production unless someone explicitly enables seeding.
- Predict endpoints are rate-limited (KISAN_PREDICT_RATE_LIMIT, default
  60/min per IP). Basic security headers are set on every response.
- KISAN_SERVE_FRONTEND=1 makes the backend serve the whole website from
  the same origin (no separate frontend host, no CORS needed for the
  demo). It defaults ON in both production and dev, so local and
  production behave identically: just run the backend and open
  http://127.0.0.1:8000/. Routes: / = standalone homepage,
  /auth (and /login -> /auth) = login/register page,
  /marketplace = marketplace, /dashboard = farmer dashboard.
  /api/* always takes priority over the static pages.
"""
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pathlib import Path
from pydantic import BaseModel, EmailStr, Field
from sklearn.ensemble import RandomForestRegressor
import sqlite3

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kisan-direct")

KISAN_ENV = os.environ.get("KISAN_ENV", "development").lower()
IS_PRODUCTION = KISAN_ENV == "production"

# Database path. In production this points at the persistent volume
# (fly.toml sets KISAN_DB_PATH=/data/kisan_direct.db). Locally it is the
# SQLite file next to this module.
DB = Path(
    os.environ.get("KISAN_DB_PATH") or str(Path(__file__).with_name("kisan_direct.db"))
)

# --- Secret key: fail fast in production, dev-only default locally. ---
PLACEHOLDER_SECRETS = {
    "", "change-me-to-a-long-random-secret", "dev-only-change-me-in-production",
    "replace-me", "replace-with-a-long-random-secret",
    "replace-with-a-long-random-secret-at-least-32-chars",
}
_secret = os.environ.get("KISAN_SECRET_KEY", "")
if IS_PRODUCTION:
    if (
        not _secret
        or _secret in PLACEHOLDER_SECRETS
        or "change-me" in _secret
        or "replace-with" in _secret
        or len(_secret) < 32
    ):
        raise RuntimeError(
            "KISAN_ENV=production requires KISAN_SECRET_KEY: set a real secret "
            "of at least 32 characters (generate one with: "
            "python3 -c \"import secrets; print(secrets.token_urlsafe(32))\" ). "
            "Refusing to start rather than running with a known/dev secret."
        )
    SECRET_KEY = _secret
else:
    SECRET_KEY = _secret or "dev-only-change-me-in-production"
    if not _secret:
        log.warning(
            "KISAN_SECRET_KEY is not set; using the dev-only default secret. "
            "Never use this outside localhost."
        )

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("KISAN_JWT_MINUTES", "720"))

# --- CORS: required and strict in production, localhost default in dev. ---
_cors_raw = os.environ.get("KISAN_CORS_ORIGINS", "")
if IS_PRODUCTION:
    if not _cors_raw:
        raise RuntimeError(
            "KISAN_ENV=production requires KISAN_CORS_ORIGINS: set it to the "
            "public frontend origin(s), comma-separated, e.g. "
            "https://kisan-direct-ai.fly.dev. Refusing to start."
        )
    FRONTEND_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    if "*" in FRONTEND_ORIGINS or any(
        "localhost" in o or "127.0.0.1" in o for o in FRONTEND_ORIGINS
    ):
        raise RuntimeError(
            "KISAN_CORS_ORIGINS in production must not contain '*' or "
            "localhost/127.0.0.1 origins. Refusing to start."
        )
else:
    FRONTEND_ORIGINS = (
        [o.strip() for o in _cors_raw.split(",") if o.strip()]
        or ["http://127.0.0.1:5500", "http://localhost:5500"]
    )

PREDICT_RATE_LIMIT = int(os.environ.get("KISAN_PREDICT_RATE_LIMIT", "60"))
SEED_DEMO_DATA = os.environ.get(
    "KISAN_SEED_DEMO_DATA", "0" if IS_PRODUCTION else "1"
) == "1"
ENABLE_DOCS = os.environ.get(
    "KISAN_ENABLE_DOCS", "0" if IS_PRODUCTION else "1"
) == "1"
SERVE_FRONTEND = os.environ.get("KISAN_SERVE_FRONTEND", "1") == "1"

app = FastAPI(
    title="Kisan Direct AI API", version="1.1",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)
app.add_middleware(
    CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_credentials=True,
    allow_methods=["GET", "POST"], allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response

CROPS = {
    "Tomato": 24, "Potato": 18, "Onion": 28, "Wheat": 25,
    "Rice": 32, "Cauliflower": 22, "Cabbage": 16, "Brinjal": 20,
    "Chilli": 48, "Mango": 65, "Banana": 30,
}
SEASONS = ["Summer", "Monsoon", "Winter"]
LOCATIONS = ["Kolkata", "Howrah", "Hooghly", "Nadia", "Burdwan"]

# Sample buyers — DEMO ONLY. There is no matching algorithm behind this list.
SAMPLE_BUYERS = [
    {"name": "Kolkata Fresh Mart", "location": "Kolkata", "crop": "Tomato",
     "offer_price_per_kg": 30, "quantity_kg": 200, "note": "Sample buyer (demo data)"},
    {"name": "Howrah Wholesale Traders", "location": "Howrah", "crop": "Potato",
     "offer_price_per_kg": 20, "quantity_kg": 500, "note": "Sample buyer (demo data)"},
    {"name": "Nadia Veg Supply Co.", "location": "Nadia", "crop": "Onion",
     "offer_price_per_kg": 32, "quantity_kg": 300, "note": "Sample buyer (demo data)"},
]


def db():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('farmer','customer'))
        );
        CREATE TABLE IF NOT EXISTS products(
          id INTEGER PRIMARY KEY AUTOINCREMENT, farmer_id INTEGER NOT NULL,
          crop TEXT NOT NULL, quantity REAL NOT NULL, price REAL NOT NULL,
          location TEXT NOT NULL, description TEXT DEFAULT '',
          FOREIGN KEY(farmer_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL,
          customer_id INTEGER NOT NULL, quantity REAL NOT NULL,
          status TEXT DEFAULT 'Placed',
          FOREIGN KEY(product_id) REFERENCES products(id),
          FOREIGN KEY(customer_id) REFERENCES users(id)
        );
        """)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Return (ok, needs_rehash). Old unsalted SHA-256 rows are recognised
    (64 hex chars) and verified the old way, then flagged for re-hashing."""
    if stored.startswith("$2b$") or stored.startswith("$2a$"):
        return bcrypt.checkpw(password.encode(), stored.encode()), False
    if len(stored) == 64 and all(c in "0123456789abcdef" for c in stored.lower()):
        import hashlib
        ok = hashlib.sha256(password.encode()).hexdigest() == stored.lower()
        return ok, ok  # needs rehash with bcrypt
    return False, False


def make_token(user: dict) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user["id"]), "name": user["name"],
                       "email": user["email"], "role": user["role"],
                       "exp": exp}, SECRET_KEY, algorithm=JWT_ALGORITHM)


bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if not creds:
        raise HTTPException(401, "Login required. Send a Bearer token.")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid session token.")
    with db() as con:
        row = con.execute("SELECT id,name,email,role FROM users WHERE id=?",
                          (int(payload["sub"]),)).fetchone()
    if not row:
        raise HTTPException(401, "Account no longer exists.")
    return dict(row)


# --- simple in-memory rate limiting for login/register (per IP, 20/min) ---
_rate: dict[str, list[float]] = defaultdict(list)


def rate_limit(request: Request, limit: int = 20, window: int = 60):
    # Keyed by IP *and* path, so a login attempt does not eat the
    # predict budget (and vice versa).
    host = request.client.host if request.client else "unknown"
    key = f"{host}:{request.url.path}"
    now = time.time()
    hits = [t for t in _rate[key] if now - t < window]
    if len(hits) >= limit:
        raise HTTPException(429, "Too many attempts. Try again in a minute.")
    hits.append(now)
    _rate[key] = hits


init_db()


def seed_demo_data():
    """Seed demo data once, only when the users table is empty.

    DEMO ONLY. The demo accounts (ramesh@example.com / demo1234 and
    buyer@example.com / demo1234) are sample accounts for a hackathon demo,
    not real accounts. Seeding is opt-in via KISAN_SEED_DEMO_DATA and is
    OFF by default in production.
    """
    with db() as con:
        if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return
        cur = con.execute(
            "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)",
            ("Ramesh", "ramesh@example.com", hash_password("demo1234"), "farmer"))
        farmer_id = cur.lastrowid
        cur = con.execute(
            "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)",
            ("Demo Buyer", "buyer@example.com", hash_password("demo1234"), "customer"))
        for crop, qty, price, loc, desc in [
            ("Tomato", 100, 24, "Kolkata", "Freshly harvested tomatoes"),
            ("Potato", 200, 18, "Howrah", "Farm fresh potatoes"),
            ("Onion", 150, 28, "Nadia", "Red onions, graded"),
        ]:
            con.execute(
                "INSERT INTO products(farmer_id,crop,quantity,price,location,description)"
                " VALUES(?,?,?,?,?,?)", (farmer_id, crop, qty, price, loc, desc))
        log.info(
            "Seeded DEMO data: farmer Ramesh (ramesh@example.com / demo1234). "
            "Demo accounts only, not real accounts."
        )


if SEED_DEMO_DATA:
    seed_demo_data()
else:
    log.info(
        "Demo seed data is OFF (KISAN_SEED_DEMO_DATA is not 1). "
        "No demo accounts are created."
    )

# Train demonstrator models on generated data. Replace with real, verified data for production.
rng = np.random.default_rng(42)
crop_names = list(CROPS)
crop_to_id = {c: i for i, c in enumerate(crop_names)}
season_to_id = {s: i for i, s in enumerate(SEASONS)}
loc_to_id = {s: i for i, s in enumerate(LOCATIONS)}
X, y_price, y_demand = [], [], []
for _ in range(5000):
    crop = rng.choice(crop_names)
    season = rng.choice(SEASONS)
    location = rng.choice(LOCATIONS)
    month = int(rng.integers(1, 13))
    rainfall = float(rng.uniform(0, 300))
    temperature = float(rng.uniform(12, 42))
    base = CROPS[crop]
    seasonal = 1 + (0.12 if season == "Winter" else -0.05 if season == "Summer" else 0.02)
    weather = 1 + (rainfall - 120) / 3000 - abs(temperature - 27) / 500
    price = max(5, base * seasonal * weather * rng.normal(1, 0.13))
    demand = max(10, 100 + base * 1.8 + (18 if month in [10, 11, 12] else 0)
                 + (10 if location == "Kolkata" else 0) + rng.normal(0, 18))
    X.append([crop_to_id[crop], season_to_id[season], loc_to_id[location],
              month, rainfall, temperature])
    y_price.append(price)
    y_demand.append(demand)
price_model = RandomForestRegressor(n_estimators=100, random_state=42, min_samples_leaf=3)
demand_model = RandomForestRegressor(n_estimators=100, random_state=43, min_samples_leaf=3)
price_model.fit(X, y_price)
demand_model.fit(X, y_demand)


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProductIn(BaseModel):
    crop: str
    quantity: float = Field(gt=0, le=100000)
    price: float = Field(gt=0, le=10000)
    location: str
    description: str = Field(default="", max_length=500)


class OrderIn(BaseModel):
    product_id: int
    quantity: float = Field(gt=0, le=100000)


class PredictIn(BaseModel):
    crop: str
    season: str = "Winter"
    location: str = "Kolkata"
    month: int = Field(default=11, ge=1, le=12)
    rainfall_mm: float = Field(default=100, ge=0, le=1000)
    temperature_c: float = Field(default=26, ge=-5, le=60)


def features(data):
    if data.crop not in crop_to_id:
        raise HTTPException(400, "Crop not supported yet.")
    if data.season not in season_to_id or data.location not in loc_to_id:
        raise HTTPException(400, "Choose a listed season and location.")
    return [[crop_to_id[data.crop], season_to_id[data.season], loc_to_id[data.location],
             data.month, data.rainfall_mm, data.temperature_c]]


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})


@app.get("/api")
def api_root():
    return {"message": "Kisan Direct AI API is running"}


# GET / is only a JSON route when the website is NOT served from this
# app. When SERVE_FRONTEND is on, the routes at the end of this file
# serve the homepage at / instead.
if not SERVE_FRONTEND:
    @app.get("/")
    def home():
        return {"message": "Kisan Direct AI API is running"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/register")
def register(data: RegisterIn, request: Request):
    rate_limit(request)
    if data.role not in ("farmer", "customer"):
        raise HTTPException(400, "Role must be farmer or customer.")
    try:
        with db() as con:
            cur = con.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)",
                              (data.name, data.email.lower(), hash_password(data.password), data.role))
            user = {"id": cur.lastrowid, "name": data.name,
                    "email": data.email.lower(), "role": data.role}
            return {**user, "access_token": make_token(user), "token_type": "bearer"}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Email already registered.")


@app.post("/api/login")
def login(data: LoginIn, request: Request):
    rate_limit(request)
    with db() as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (data.email.lower(),)).fetchone()
    if not row:
        raise HTTPException(401, "Incorrect email or password.")
    ok, needs_rehash = verify_password(data.password, row["password_hash"])
    if not ok:
        raise HTTPException(401, "Incorrect email or password.")
    if needs_rehash:
        with db() as con:
            con.execute("UPDATE users SET password_hash=? WHERE id=?",
                        (hash_password(data.password), row["id"]))
    user = {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"]}
    return {**user, "access_token": make_token(user), "token_type": "bearer"}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


@app.get("/api/products")
def products():
    with db() as con:
        rows = con.execute("""SELECT p.*,u.name AS farmer_name FROM products p
                              JOIN users u ON p.farmer_id=u.id ORDER BY p.id DESC""").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/products")
def add_product(data: ProductIn, user: dict = Depends(current_user)):
    if user["role"] != "farmer":
        raise HTTPException(403, "A farmer account is required.")
    if data.crop not in CROPS or data.location not in LOCATIONS:
        raise HTTPException(400, "Choose a supported crop and location.")
    with db() as con:
        cur = con.execute("""INSERT INTO products(farmer_id,crop,quantity,price,location,description)
                             VALUES(?,?,?,?,?,?)""",
                          (user["id"], data.crop, data.quantity, data.price, data.location, data.description))
        return {"id": cur.lastrowid, "message": "Product listed successfully."}


@app.post("/api/orders")
def create_order(data: OrderIn, user: dict = Depends(current_user)):
    if user["role"] != "customer":
        raise HTTPException(403, "Only customer accounts can place orders.")
    with db() as con:
        product = con.execute("SELECT * FROM products WHERE id=?", (data.product_id,)).fetchone()
        if not product:
            raise HTTPException(404, "Product not found.")
        if data.quantity > product["quantity"]:
            raise HTTPException(400, "Not enough quantity available.")
        cur = con.execute("INSERT INTO orders(product_id,customer_id,quantity,status)"
                          " VALUES(?,?,?,'Placed')",
                          (data.product_id, user["id"], data.quantity))
        con.execute("UPDATE products SET quantity=quantity-? WHERE id=?",
                    (data.quantity, data.product_id))
        return {"id": cur.lastrowid, "product_id": data.product_id,
                "quantity": data.quantity, "status": "Placed",
                "message": "Order placed successfully."}


@app.get("/api/orders")
def list_orders(user: dict = Depends(current_user)):
    with db() as con:
        if user["role"] == "customer":
            rows = con.execute("""SELECT o.*,p.crop,p.price,p.location FROM orders o
                                  JOIN products p ON o.product_id=p.id
                                  WHERE o.customer_id=? ORDER BY o.id DESC""",
                               (user["id"],)).fetchall()
        else:
            rows = con.execute("""SELECT o.*,p.crop,p.price,p.location FROM orders o
                                  JOIN products p ON o.product_id=p.id
                                  WHERE p.farmer_id=? ORDER BY o.id DESC""",
                               (user["id"],)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/buyers")
def buyers():
    """Sample buyers only (demo data). Real AI buyer matching is NOT implemented."""
    return {"buyers": SAMPLE_BUYERS,
            "note": "Sample buyers (demo data). No matching algorithm runs behind this list yet."}


@app.post("/api/predict/price")
def predict_price(data: PredictIn, request: Request):
    rate_limit(request, limit=PREDICT_RATE_LIMIT, window=60)
    x = features(data)
    estimate = float(price_model.predict(x)[0])
    tree_preds = np.array([tree.predict(x)[0] for tree in price_model.estimators_])
    spread = float(np.std(tree_preds))
    return {"crop": data.crop, "location": data.location,
            "estimated_price_per_kg": round(estimate, 2),
            "indicative_low": round(max(1, estimate - spread), 2),
            "indicative_high": round(estimate + spread, 2),
            "unit": "INR/kg",
            "note": "Demo-model estimate trained on synthetic data; not a live mandi quote."}


@app.post("/api/predict/demand")
def predict_demand(data: PredictIn, request: Request):
    rate_limit(request, limit=PREDICT_RATE_LIMIT, window=60)
    x = features(data)
    estimate = float(demand_model.predict(x)[0])
    return {"crop": data.crop, "location": data.location,
            "estimated_demand_index": round(estimate, 1),
            "label": "High" if estimate >= 170 else "Medium" if estimate >= 135 else "Low",
            "note": "Demo demand index (not tonnes or confirmed orders); trained on synthetic data."}


# --- Serve the whole website from the same origin. ---
# One origin for the complete journey, local and production alike:
#   /             standalone homepage (standalone-pages/homepage/)
#   /auth         login/register page (standalone-pages/auth/); /login redirects here
#   /marketplace  marketplace (mvp/frontend/index.html)
#   /dashboard    farmer dashboard (mvp/frontend/farmer-dashboard.html)
# Registered last, so /api/*, /docs and /api/health keep working and take
# priority. Unknown /api/* paths still 404 (they fall through to the
# static mount, which has no matching file) instead of returning HTML.
# The pages use absolute asset paths (/style.css, /app.js, /homepage.css)
# so they work from any of these routes.
def _site_dir(*parts: str) -> Path:
    """Find a site directory by walking up from this file, then from cwd.

    main.py normally lives at mvp/backend/main.py, so the repo root is
    two levels up. The cwd fallback matters for the test suite, which
    imports a copy of this file from a temp dir while running pytest
    from the repo root.
    """
    here = Path(__file__).resolve()
    for base in [here.parent, *here.parents, Path.cwd()]:
        candidate = base.joinpath(*parts)
        if candidate.is_dir():
            return candidate
    # Docker layout: main.py is /app/main.py and the frontend is copied
    # to /app/frontend (a sibling, not /app/mvp/frontend).
    sibling = here.parent.joinpath(parts[-1])
    if sibling.is_dir():
        return sibling
    return here.parent.joinpath(*parts)


FRONTEND_DIR = _site_dir("mvp", "frontend")
HOMEPAGE_DIR = _site_dir("standalone-pages", "homepage")
AUTH_DIR = _site_dir("standalone-pages", "auth")
if SERVE_FRONTEND:
    from fastapi.responses import FileResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles

    def _page(directory: Path, filename: str):
        """Serve one HTML file, or 404 with a plain message if it is missing."""
        path = directory / filename
        if path.is_file():
            return FileResponse(path, media_type="text/html")
        log.warning("Site file missing: %s", path)
        return JSONResponse(status_code=404, content={"detail": "Page not found."})

    @app.get("/", include_in_schema=False)
    def homepage():
        return _page(HOMEPAGE_DIR, "homepage.html")

    @app.get("/homepage.css", include_in_schema=False)
    def homepage_css():
        return FileResponse(HOMEPAGE_DIR / "homepage.css", media_type="text/css")

    @app.get("/auth", include_in_schema=False)
    def auth_page():
        return _page(AUTH_DIR, "auth.html")

    @app.get("/login", include_in_schema=False)
    def login_page():
        # Canonical auth URL is /auth.
        return RedirectResponse("/auth", status_code=302)

    @app.get("/marketplace", include_in_schema=False)
    def marketplace_page():
        return _page(FRONTEND_DIR, "index.html")

    @app.get("/dashboard", include_in_schema=False)
    def dashboard_page():
        return _page(FRONTEND_DIR, "farmer-dashboard.html")

    # Legacy direct file URLs (used by the old Playwright suite and by
    # bookmarks). Keep them working as redirects, not as duplicates.
    @app.get("/index.html", include_in_schema=False)
    def legacy_marketplace():
        return RedirectResponse("/marketplace", status_code=302)

    @app.get("/farmer-dashboard.html", include_in_schema=False)
    def legacy_dashboard():
        return RedirectResponse("/dashboard", status_code=302)

    @app.get("/homepage.html", include_in_schema=False)
    def legacy_homepage():
        return RedirectResponse("/", status_code=302)

    @app.get("/marketplace/", include_in_schema=False)
    def marketplace_trailing_slash():
        return RedirectResponse("/marketplace", status_code=302)

    @app.get("/dashboard/", include_in_schema=False)
    def dashboard_trailing_slash():
        return RedirectResponse("/dashboard", status_code=302)

    @app.get("/auth/", include_in_schema=False)
    def auth_trailing_slash():
        return RedirectResponse("/auth", status_code=302)

    if FRONTEND_DIR.is_dir():
        # Serves /style.css, /app.js and any other marketplace asset.
        # Explicit routes above take priority; unknown paths 404.
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
        log.info("Serving website from %s (homepage %s, auth %s) at /",
                 FRONTEND_DIR, HOMEPAGE_DIR, AUTH_DIR)
    else:
        log.warning("KISAN_SERVE_FRONTEND=1 but frontend dir %s is missing.", FRONTEND_DIR)
