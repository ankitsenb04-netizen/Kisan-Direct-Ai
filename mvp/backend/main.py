from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pathlib import Path
import sqlite3, hashlib, secrets, random
import numpy as np
from sklearn.ensemble import RandomForestRegressor

DB = Path(__file__).with_name("kisan_direct.db")
app = FastAPI(title="Kisan Direct AI API", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

CROPS = {
    "Tomato": 24, "Potato": 18, "Onion": 28, "Wheat": 25,
    "Rice": 32, "Cauliflower": 22, "Cabbage": 16, "Brinjal": 20,
    "Chilli": 48, "Mango": 65, "Banana": 30
}
SEASONS = ["Summer", "Monsoon", "Winter"]
LOCATIONS = ["Kolkata", "Howrah", "Hooghly", "Nadia", "Burdwan"]

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
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
          status TEXT DEFAULT 'Placed'
        );
        """)
init_db()

# Train demonstrator models on generated data. Replace with real, verified data for production.
rng = np.random.default_rng(42)
crop_names = list(CROPS)
crop_to_id = {c:i for i,c in enumerate(crop_names)}
season_to_id = {s:i for i,s in enumerate(SEASONS)}
loc_to_id = {s:i for i,s in enumerate(LOCATIONS)}
X, y_price, y_demand = [], [], []
for _ in range(5000):
    crop = rng.choice(crop_names)
    season = rng.choice(SEASONS)
    location = rng.choice(LOCATIONS)
    month = int(rng.integers(1,13))
    rainfall = float(rng.uniform(0,300))
    temperature = float(rng.uniform(12,42))
    base = CROPS[crop]
    seasonal = 1 + (0.12 if season == "Winter" else -0.05 if season == "Summer" else 0.02)
    weather = 1 + (rainfall-120)/3000 - abs(temperature-27)/500
    price = max(5, base * seasonal * weather * rng.normal(1,0.13))
    demand = max(10, 100 + base*1.8 + (18 if month in [10,11,12] else 0)
                 + (10 if location == "Kolkata" else 0) + rng.normal(0,18))
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
    email: str
    password: str = Field(min_length=6)
    role: str

class LoginIn(BaseModel):
    email: str
    password: str

class ProductIn(BaseModel):
    farmer_id: int
    crop: str
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    location: str
    description: str = ""

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

@app.get("/")
def home():
    return {"message":"Kisan Direct AI API is running", "docs":"/docs"}

@app.post("/api/register")
def register(data: RegisterIn):
    if data.role not in ("farmer","customer"):
        raise HTTPException(400,"Role must be farmer or customer.")
    hashed = hashlib.sha256(data.password.encode()).hexdigest()
    try:
        with db() as con:
            cur = con.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)",
                              (data.name, data.email.lower(), hashed, data.role))
            return {"id":cur.lastrowid,"name":data.name,"email":data.email.lower(),"role":data.role}
    except sqlite3.IntegrityError:
        raise HTTPException(409,"Email already registered.")

@app.post("/api/login")
def login(data: LoginIn):
    hashed = hashlib.sha256(data.password.encode()).hexdigest()
    with db() as con:
        row = con.execute("SELECT id,name,email,role FROM users WHERE email=? AND password_hash=?",
                          (data.email.lower(),hashed)).fetchone()
    if not row:
        raise HTTPException(401,"Incorrect email or password.")
    return dict(row)

@app.get("/api/products")
def products():
    with db() as con:
        rows = con.execute("""SELECT p.*,u.name AS farmer_name FROM products p
                              JOIN users u ON p.farmer_id=u.id ORDER BY p.id DESC""").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/products")
def add_product(data: ProductIn):
    if data.crop not in CROPS or data.location not in LOCATIONS:
        raise HTTPException(400,"Choose a supported crop and location.")
    with db() as con:
        user = con.execute("SELECT id,role FROM users WHERE id=?", (data.farmer_id,)).fetchone()
        if not user or user["role"] != "farmer":
            raise HTTPException(403,"A farmer account is required.")
        cur = con.execute("""INSERT INTO products(farmer_id,crop,quantity,price,location,description)
                             VALUES(?,?,?,?,?,?)""",
                          (data.farmer_id,data.crop,data.quantity,data.price,data.location,data.description))
        return {"id":cur.lastrowid,"message":"Product listed successfully."}

@app.post("/api/predict/price")
def predict_price(data: PredictIn):
    x = features(data)
    estimate = float(price_model.predict(x)[0])
    # Ensemble spread used as a simple indicative range, not a calibrated confidence interval.
    tree_preds = np.array([tree.predict(x)[0] for tree in price_model.estimators_])
    spread = float(np.std(tree_preds))
    return {"crop":data.crop,"location":data.location,"estimated_price_per_kg":round(estimate,2),
            "indicative_low":round(max(1,estimate-spread),2),
            "indicative_high":round(estimate+spread,2),
            "unit":"INR/kg","note":"Demo-model estimate trained on synthetic data; not a live mandi quote."}

@app.post("/api/predict/demand")
def predict_demand(data: PredictIn):
    x = features(data)
    estimate = float(demand_model.predict(x)[0])
    return {"crop":data.crop,"location":data.location,"estimated_demand_index":round(estimate,1),
            "label":"High" if estimate >= 170 else "Medium" if estimate >= 135 else "Low",
            "note":"Demo demand index (not tonnes or confirmed orders); trained on synthetic data."}
