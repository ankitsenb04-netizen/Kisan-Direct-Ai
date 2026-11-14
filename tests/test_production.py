"""Production smoke tests for Kisan Direct AI.

Each test runs tests/prod_probe.py in a subprocess with a controlled
environment and a fresh throwaway DB, so the module-level production
checks in mvp/backend/main.py are exercised for real:
- production refuses to start without a real secret, without CORS, or
  with a wildcard/localhost CORS origin;
- /docs and /openapi.json are off by default in production;
- demo seed data is off by default in production (no demo accounts);
- CORS allows only a listed origin, security headers are set, and the
  frontend is served from the same origin;
- predict endpoints are rate-limited.

Run from the repo root:  pytest tests/test_production.py -v
"""
import json
import os
import subprocess
import sys
from pathlib import Path

PROBE = Path(__file__).resolve().parent / "prod_probe.py"
GOOD_ORIGIN = "https://kisan-direct-ai.fly.dev"
SECRET = "prod-test-secret-that-is-long-enough-123456"


def _clean_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("KISAN_")}
    env.pop("KISAN_PROBE_MODE", None)
    env.pop("KISAN_PROBE_GOOD_ORIGIN", None)
    return env


def run_probe(tmp_path, mode="prod", **overrides):
    env = _clean_env()
    env["KISAN_DB_PATH"] = str(tmp_path / "prod.db")
    env["KISAN_PROBE_MODE"] = mode
    env["KISAN_PROBE_GOOD_ORIGIN"] = GOOD_ORIGIN
    env.update(overrides)
    proc = subprocess.run(
        [sys.executable, str(PROBE)], env=env, capture_output=True,
        text=True, timeout=180,
    )
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise AssertionError(
            f"probe produced no JSON (rc={proc.returncode}): "
            f"stdout={proc.stdout!r} stderr={proc.stderr[-2000:]!r}"
        )
    return proc.returncode, data


def prod_env(**extra):
    env = {
        "KISAN_ENV": "production",
        "KISAN_SECRET_KEY": SECRET,
        "KISAN_CORS_ORIGINS": GOOD_ORIGIN,
    }
    env.update(extra)
    return env


def test_production_refuses_without_secret(tmp_path):
    rc, data = run_probe(tmp_path, mode="import", KISAN_ENV="production")
    assert rc == 2 and not data["started"]
    assert "KISAN_SECRET_KEY" in data["error"]


def test_production_refuses_placeholder_secret(tmp_path):
    rc, data = run_probe(
        tmp_path, mode="import", KISAN_ENV="production",
        KISAN_SECRET_KEY="change-me-to-a-long-random-secret",
    )
    assert rc == 2 and "KISAN_SECRET_KEY" in data["error"]


def test_production_refuses_example_placeholder_secret(tmp_path):
    rc, data = run_probe(
        tmp_path, mode="import", KISAN_ENV="production",
        KISAN_SECRET_KEY="replace-with-a-long-random-secret-at-least-32-chars",
    )
    assert rc == 2 and "KISAN_SECRET_KEY" in data["error"]


def test_production_refuses_without_cors(tmp_path):
    rc, data = run_probe(
        tmp_path, mode="import", KISAN_ENV="production",
        KISAN_SECRET_KEY=SECRET,
    )
    assert rc == 2 and "KISAN_CORS_ORIGINS" in data["error"]


def test_production_refuses_wildcard_cors(tmp_path):
    rc, data = run_probe(
        tmp_path, mode="import", KISAN_ENV="production",
        KISAN_SECRET_KEY=SECRET, KISAN_CORS_ORIGINS="*",
    )
    assert rc == 2 and "KISAN_CORS_ORIGINS" in data["error"]


def test_production_defaults_secure(tmp_path):
    rc, data = run_probe(tmp_path, **prod_env())
    assert rc == 0, data
    assert data["health"] == 200
    assert data["docs"] == 404
    assert data["openapi"] == 404
    assert data["products"] == []
    assert data["demo_login_status"] == 401
    assert data["cors_evil"] is None
    assert data["cors_good"] == GOOD_ORIGIN
    assert data["hsts"] is not None and "max-age=31536000" in data["hsts"]
    assert data["x_frame"] == "DENY"
    assert data["x_content_type"] == "nosniff"
    assert data["root_status"] == 200
    assert data["root_is_html"] and data["root_contains_kisan"]
    # Complete journey routes, all same origin.
    for path in ("/", "/auth", "/marketplace", "/dashboard",
                 "/homepage.css", "/style.css", "/app.js"):
        assert data["routes"][path]["status"] == 200, path
        assert data["routes"][path]["contains"], path
    assert data["login_redirect"]["status"] in (301, 302, 307, 308)
    assert data["login_redirect"]["location"] == "/auth"
    assert data["legacy_marketplace_redirect"] == "/marketplace"
    assert data["legacy_dashboard_redirect"] == "/dashboard"
    assert data["api_unknown_status"] == 404
    assert not data["api_unknown_is_html"]


def test_production_docs_can_be_enabled(tmp_path):
    rc, data = run_probe(tmp_path, **prod_env(KISAN_ENABLE_DOCS="1"))
    assert rc == 0, data
    assert data["docs"] == 200


def test_production_seeding_is_opt_in(tmp_path):
    rc, data = run_probe(tmp_path, **prod_env(KISAN_SEED_DEMO_DATA="1"))
    assert rc == 0, data
    crops = {p["crop"] for p in data["products"]}
    assert {"Tomato", "Potato", "Onion"} <= crops
    assert data["demo_login_status"] == 200


def test_production_predict_rate_limited(tmp_path):
    rc, data = run_probe(
        tmp_path, mode="predict",
        **prod_env(KISAN_PREDICT_RATE_LIMIT="3"),
    )
    assert rc == 0, data
    assert data["predict_statuses"] == [200, 200, 200, 429]
