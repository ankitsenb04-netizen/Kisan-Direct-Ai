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

DB = Path(__file__).with_name("kisan_direct.db")
SECRET_KEY = os.environ.get("KISAN_SECRET_KEY", "dev-only-change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("KISAN_JWT_MINUTES", "720"))
FRONTEND_ORIGINS = [
    o.strip() for o in os.environ.get(
        "KISAN_CORS_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500"
    ).split(",") if o.strip()
]

app = FastAPI(title="Kisan Direct AI API", version="1.1")
app.add_middleware(
    CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_credentials=True,
    allow_methods=["GET", "POST"], allow_headers=["*"],
)

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
    key = request.client.host if request.client else "unknown"
    now = time.time()
    hits = [t for t in _rate[key] if now - t < window]
    if len(hits) >= limit:
        raise HTTPException(429, "Too many attempts. Try again in a minute.")
    hits.append(now)
    _rate[key] = hits


init_db()


def seed_demo_data():
    """Seed demo data once, only when the users table is empty. Test-only."""
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
        log.info("Seeded demo data: farmer Ramesh (ramesh@example.com / demo1234)")


seed_demo_data()

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


@app.get("/")
def home():
    return {"message": "Kisan Direct AI API is running", "docs": "/docs"}


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
def predict_price(data: PredictIn):
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
def predict_demand(data: PredictIn):
    x = features(data)
    estimate = float(demand_model.predict(x)[0])
    return {"crop": data.crop, "location": data.location,
            "estimated_demand_index": round(estimate, 1),
            "label": "High" if estimate >= 170 else "Medium" if estimate >= 135 else "Low",
            "note": "Demo demand index (not tonnes or confirmed orders); trained on synthetic data."}
