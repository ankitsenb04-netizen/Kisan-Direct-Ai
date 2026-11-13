"""Integration tests for Kisan Direct AI (Phase 2, Team TerraCore).
Runs against a FRESH COPY of the integrated mvp/backend/main.py in a tmp dir.
Test-only fake data; no real credentials.
Run from repo root:  pytest tests/test_integration.py -v
Note: the original 6 audit tests in test_mvp_api.py assert the OLD behaviour
(SHA-256, no token, no /api/orders). They are superseded by this suite, which
asserts the new JWT/bcrypt/order behaviour. See INTEGRATION-REPORT.md.
"""
import hashlib
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_BACKEND = Path(__file__).resolve().parent.parent / "mvp" / "backend" / "main.py"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("backend-int")
    shutil.copy(REPO_BACKEND, tmp / "main.py")
    sys.path.insert(0, str(tmp))
    import main  # noqa: E402
    assert Path(tmp / "kisan_direct.db").exists()
    with TestClient(main.app) as c:
        yield c, tmp
    sys.path.remove(str(tmp))


def _email(tag):
    return f"int-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _register(client, name, role):
    email = _email(role)
    r = client.post("/api/register", json={"name": name, "email": email,
                                           "password": "testpass123", "role": role})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(client, user):
    return {"Authorization": f"Bearer {user['access_token']}"}


def test_home_health_and_openapi(client):
    c, _ = client
    assert c.get("/").status_code == 200
    assert c.get("/api/health").json() == {"status": "ok"}
    paths = sorted(c.get("/openapi.json").json()["paths"].keys())
    assert "/api/orders" in paths and "/api/buyers" in paths and "/api/me" in paths


def test_seed_demo_data(client):
    c, tmp = client
    # Seeded on first import: Ramesh + 3 products exist before any test user registers
    r = c.get("/api/products")
    assert r.status_code == 200
    crops = {p["crop"] for p in r.json()}
    assert {"Tomato", "Potato", "Onion"} <= crops
    # Demo login works with the seeded credentials
    r = c.post("/api/login", json={"email": "ramesh@example.com", "password": "demo1234"})
    assert r.status_code == 200 and r.json()["name"] == "Ramesh"
    assert r.json()["access_token"]


def test_bcrypt_not_sha256_and_login_returns_jwt(client):
    c, tmp = client
    user = _register(c, "Hash Farmer", "farmer")
    assert "access_token" in user and user["token_type"] == "bearer"
    con = sqlite3.connect(tmp / "kisan_direct.db")
    stored = con.execute("SELECT password_hash FROM users WHERE email=?",
                         (user["email"],)).fetchone()[0]
    con.close()
    assert stored.startswith("$2b$"), "password must be bcrypt, not SHA-256"
    assert stored != hashlib.sha256(b"testpass123").hexdigest()
    # /api/me works with the token
    r = c.get("/api/me", headers=_auth(c, user))
    assert r.status_code == 200 and r.json()["email"] == user["email"]
    # no token -> 401
    assert c.get("/api/me").status_code == 401


def test_old_sha256_row_migrates_on_login(client):
    c, tmp = client
    email = _email("legacy")
    old = hashlib.sha256(b"testpass123").hexdigest()
    con = sqlite3.connect(tmp / "kisan_direct.db")
    con.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)",
                ("Legacy", email, old, "farmer"))
    con.commit(); con.close()
    r = c.post("/api/login", json={"email": email, "password": "testpass123"})
    assert r.status_code == 200, r.text
    con = sqlite3.connect(tmp / "kisan_direct.db")
    stored = con.execute("SELECT password_hash FROM users WHERE email=?", (email,)).fetchone()[0]
    con.close()
    assert stored.startswith("$2b$"), "legacy SHA-256 row should be re-hashed with bcrypt"


def test_product_requires_token_and_farmer_role(client):
    c, _ = client
    farmer = _register(c, "Token Farmer", "farmer")
    buyer = _register(c, "Token Buyer", "customer")
    body = {"crop": "Potato", "quantity": 50, "price": 18, "location": "Howrah"}
    # no token -> 401 (impersonation via client-supplied farmer_id is closed)
    assert c.post("/api/products", json=body).status_code == 401
    # customer token -> 403
    assert c.post("/api/products", json=body, headers=_auth(c, buyer)).status_code == 403
    # farmer token, no farmer_id in body -> 200, derived from token
    r = c.post("/api/products", json=body, headers=_auth(c, farmer))
    assert r.status_code == 200, r.text


def test_order_flow_end_to_end(client):
    c, _ = client
    farmer = _register(c, "Order Farmer", "farmer")
    buyer = _register(c, "Order Buyer", "customer")
    r = c.post("/api/products",
               json={"crop": "Tomato", "quantity": 100, "price": 24, "location": "Kolkata"},
               headers=_auth(c, farmer))
    pid = r.json()["id"]
    # farmer cannot order their own listing -> 403
    assert c.post("/api/orders", json={"product_id": pid, "quantity": 10},
                  headers=_auth(c, farmer)).status_code == 403
    # unauthenticated -> 401
    assert c.post("/api/orders", json={"product_id": pid, "quantity": 10}).status_code == 401
    # too much quantity -> 400
    assert c.post("/api/orders", json={"product_id": pid, "quantity": 9999},
                  headers=_auth(c, buyer)).status_code == 400
    # valid order -> 200, quantity decrements
    r = c.post("/api/orders", json={"product_id": pid, "quantity": 10},
               headers=_auth(c, buyer))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Placed"
    # buyer sees their order, farmer sees the order for their listing
    assert len(c.get("/api/orders", headers=_auth(c, buyer)).json()) == 1
    assert len(c.get("/api/orders", headers=_auth(c, farmer)).json()) == 1
    products = c.get("/api/products").json()
    mine = [p for p in products if p["id"] == pid][0]
    assert mine["quantity"] == 90


def test_buyers_endpoint_is_labelled_demo(client):
    c, _ = client
    r = c.get("/api/buyers")
    assert r.status_code == 200
    assert "demo" in r.json()["note"].lower()
    assert len(r.json()["buyers"]) >= 1


def test_predict_still_works(client):
    c, _ = client
    body = {"crop": "Tomato", "season": "Winter", "location": "Kolkata",
            "month": 11, "rainfall_mm": 100, "temperature_c": 26}
    r = c.post("/api/predict/price", json=body)
    assert r.status_code == 200 and r.json()["estimated_price_per_kg"] > 0
    r = c.post("/api/predict/demand", json=body)
    assert r.status_code == 200 and r.json()["label"] in ("High", "Medium", "Low")
