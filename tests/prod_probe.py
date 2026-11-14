"""Helper run by tests/test_production.py in a subprocess.

Each scenario gets a fresh process (and a fresh DB via KISAN_DB_PATH) so
module-level config in mvp/backend/main.py is evaluated with that
scenario's environment. Prints one JSON object to stdout and exits 0
on success, 2 if the app refused to start (RuntimeError at import).

Run directly for debugging, e.g.:
  KISAN_ENV=production KISAN_SECRET_KEY=<32+ chars> \\
  KISAN_CORS_ORIGINS=https://example.com KISAN_DB_PATH=/tmp/p.db \\
  KISAN_PROBE_MODE=prod python3 tests/prod_probe.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mvp" / "backend"))

try:
    import main
except RuntimeError as exc:
    print(json.dumps({"started": False, "error": str(exc)}))
    sys.exit(2)

from fastapi.testclient import TestClient

mode = os.environ.get("KISAN_PROBE_MODE", "prod")

if mode == "import":
    print(json.dumps({
        "started": True,
        "docs_enabled": main.ENABLE_DOCS,
        "seed": main.SEED_DEMO_DATA,
        "serve_frontend": main.SERVE_FRONTEND,
        "cors": main.FRONTEND_ORIGINS,
    }))
    sys.exit(0)

results = {"started": True}
with TestClient(main.app, raise_server_exceptions=False) as c:
    results["health"] = c.get("/api/health").status_code
    results["docs"] = c.get("/docs").status_code
    results["openapi"] = c.get("/openapi.json").status_code
    root = c.get("/")
    results["root_status"] = root.status_code
    results["root_is_html"] = "text/html" in root.headers.get("content-type", "")
    results["root_contains_kisan"] = "Kisan Direct" in root.text
    # Complete user journey routes (same origin).
    results["routes"] = {}
    for path, needle in [
        ("/", "Sell Smarter"),
        ("/auth", "Kisan Portal"),
        ("/marketplace", "AI Farmer Marketplace"),
        ("/dashboard", "Farmer Dashboard"),
        ("/homepage.css", "navbar"),
        ("/style.css", "topbar"),
        ("/app.js", "loadProducts"),
    ]:
        r = c.get(path)
        results["routes"][path] = {
            "status": r.status_code,
            "contains": needle in r.text,
        }
    login = c.get("/login", follow_redirects=False)
    results["login_redirect"] = {
        "status": login.status_code,
        "location": login.headers.get("location"),
    }
    results["legacy_marketplace_redirect"] = c.get(
        "/index.html", follow_redirects=False).headers.get("location")
    results["legacy_dashboard_redirect"] = c.get(
        "/farmer-dashboard.html", follow_redirects=False).headers.get("location")
    results["api_unknown_status"] = c.get("/api/nope").status_code
    results["api_unknown_is_html"] = "text/html" in c.get(
        "/api/nope").headers.get("content-type", "")
    results["products"] = c.get("/api/products").json()
    results["demo_login_status"] = c.post(
        "/api/login",
        json={"email": "ramesh@example.com", "password": "demo1234"},
    ).status_code
    good_origin = os.environ.get("KISAN_PROBE_GOOD_ORIGIN", "")
    evil = c.options("/api/health", headers={
        "Origin": "https://evil.example.com",
        "Access-Control-Request-Method": "GET",
    })
    results["cors_evil"] = evil.headers.get("access-control-allow-origin")
    good = c.options("/api/health", headers={
        "Origin": good_origin, "Access-Control-Request-Method": "GET",
    })
    results["cors_good"] = good.headers.get("access-control-allow-origin")
    headers = c.get("/api/health").headers
    results["hsts"] = headers.get("strict-transport-security")
    results["x_frame"] = headers.get("x-frame-options")
    results["x_content_type"] = headers.get("x-content-type-options")
    if mode == "predict":
        body = {"crop": "Tomato", "season": "Winter", "location": "Kolkata",
                "month": 11, "rainfall_mm": 100, "temperature_c": 26}
        results["predict_statuses"] = [
            c.post("/api/predict/price", json=body).status_code for _ in range(4)
        ]

print(json.dumps(results))
