"""Phase 2 QA tests for Kisan Direct AI MVP (Team TerraCore, GeNarrative Clash 2026).

Runs against a FRESH COPY of mvp/backend/main.py in a tmp dir, so the
repo and the curl-test DB under run/backend-copy are untouched.
Test-only fake data; no real credentials.
Run:  ../venv-test/bin/pytest tests/test_mvp_api.py -v
"""
import shutil
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_BACKEND = Path(__file__).resolve().parent.parent.parent / "mvp" / "backend" / "main.py"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("backend")
    shutil.copy(REPO_BACKEND, tmp / "main.py")
    sys.path.insert(0, str(tmp))
    import main  # noqa: E402  (imported from the temp copy; its DB lives in tmp)

    assert Path(tmp / "kisan_direct.db").exists(), "init_db() should create the SQLite DB on import"
    with TestClient(main.app) as c:
        yield c
    sys.path.remove(str(tmp))


def _email(tag):
    return f"qa-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def test_home_and_openapi(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["message"] == "Kisan Direct AI API is running"
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = sorted(r.json()["paths"].keys())
    assert paths == ["/", "/api/login", "/api/predict/demand",
                     "/api/predict/price", "/api/products", "/api/register"]


def test_register_login_farmer(client):
    email = _email("farmer")
    r = client.post("/api/register", json={"name": "QA Farmer", "email": email,
                                           "password": "testpass123", "role": "farmer"})
    assert r.status_code == 200, r.text
    farmer_id = r.json()["id"]
    # duplicate email -> 409
    r = client.post("/api/register", json={"name": "QA Farmer", "email": email,
                                           "password": "testpass123", "role": "farmer"})
    assert r.status_code == 409
    assert r.json()["detail"] == "Email already registered."
    # login OK
    r = client.post("/api/login", json={"email": email, "password": "testpass123"})
    assert r.status_code == 200
    assert r.json()["id"] == farmer_id
    # wrong password -> 401
    r = client.post("/api/login", json={"email": email, "password": "wrongpass"})
    assert r.status_code == 401


def test_register_bad_role_and_short_password(client):
    r = client.post("/api/register", json={"name": "Bad", "email": _email("role"),
                                           "password": "testpass123", "role": "admin"})
    assert r.status_code == 400
    r = client.post("/api/register", json={"name": "Short", "email": _email("short"),
                                           "password": "123", "role": "farmer"})
    assert r.status_code == 422


def test_listing_flow(client):
    farmer_email = _email("seller")
    farmer = client.post("/api/register", json={"name": "QA Seller", "email": farmer_email,
                                                "password": "testpass123", "role": "farmer"}).json()
    buyer = client.post("/api/register", json={"name": "QA Buyer", "email": _email("buyer"),
                                               "password": "testpass123", "role": "customer"}).json()
    # farmer can list
    r = client.post("/api/products", json={"farmer_id": farmer["id"], "crop": "Potato",
                                           "quantity": 50, "price": 18,
                                           "location": "Howrah", "description": "QA listing"})
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Product listed successfully."
    # customer cannot list -> 403
    r = client.post("/api/products", json={"farmer_id": buyer["id"], "crop": "Potato",
                                           "quantity": 50, "price": 18, "location": "Howrah"})
    assert r.status_code == 403
    # unsupported crop -> 400
    r = client.post("/api/products", json={"farmer_id": farmer["id"], "crop": "Dragonfruit",
                                           "quantity": 10, "price": 99, "location": "Kolkata"})
    assert r.status_code == 400
    # listing appears in GET /api/products
    r = client.get("/api/products")
    assert r.status_code == 200
    mine = [p for p in r.json() if p["description"] == "QA listing"]
    assert len(mine) == 1
    assert mine[0]["crop"] == "Potato" and mine[0]["farmer_name"] == "QA Seller"


def test_predict_price_and_demand(client):
    body = {"crop": "Tomato", "season": "Winter", "location": "Kolkata",
            "month": 11, "rainfall_mm": 100, "temperature_c": 26}
    r = client.post("/api/predict/price", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["unit"] == "INR/kg"
    assert d["indicative_low"] <= d["estimated_price_per_kg"] <= d["indicative_high"]
    assert d["estimated_price_per_kg"] > 0
    r = client.post("/api/predict/demand", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["label"] in ("High", "Medium", "Low")
    assert d["estimated_demand_index"] > 0
    # unsupported crop -> 400
    r = client.post("/api/predict/price", json={**body, "crop": "Dragonfruit"})
    assert r.status_code == 400


def test_no_order_endpoint(client):
    # orders table exists in the DB, but no buyer/order route is implemented
    r = client.post("/api/orders", json={"product_id": 1, "customer_id": 1, "quantity": 10})
    assert r.status_code == 404
    r = client.get("/api/orders")
    assert r.status_code == 404
