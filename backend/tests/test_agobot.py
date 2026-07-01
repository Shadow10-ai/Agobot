"""AgoBot Backend API Tests - Iteration 13"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

EMAIL = "gozmokchris@gmail.com"
PASSWORD = "f7e8251e"


@pytest.fixture(scope="module")
def auth_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.text}"
    data = r.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def authed(auth_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {auth_token}"})
    return s


# Health
def test_health():
    r = requests.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    print("Health OK")


# Auth
def test_login_success():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200
    data = r.json()
    token = data.get("access_token") or data.get("token")
    assert token is not None
    assert "user" in data
    print(f"Login OK, user={data['user'].get('email')}")


def test_login_wrong_password():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": "wrongpass"})
    assert r.status_code in [400, 401, 403]
    print("Wrong password returns error correctly")


# Dashboard
def test_dashboard(authed):
    r = authed.get(f"{BASE_URL}/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "bot_status" in data
    print(f"Dashboard OK, bot_mode={data['bot_status'].get('mode')}")


# ML Status
def test_ml_status(authed):
    r = authed.get(f"{BASE_URL}/api/ml/status")
    assert r.status_code == 200
    data = r.json()
    print(f"ML Status: {data}")
    assert "status" in data
    # Expect LEARNING mode with labeled_signals=86
    assert data.get("status") == "LEARNING", f"Expected LEARNING, got {data.get('status')}"
    labeled = data.get("labeled_signals", data.get("labeled_signals_count", 0))
    assert labeled == 86, f"Expected 86 labeled_signals, got {labeled}"
    training = data.get("training_samples", data.get("model_training_samples", 0))
    assert training == 0, f"Expected 0 training_samples, got {training}"
    print(f"ML status OK: LEARNING, labeled={labeled}, training_samples={training}")


# Performance
def test_performance(authed):
    r = authed.get(f"{BASE_URL}/api/performance")
    assert r.status_code == 200
    data = r.json()
    assert "wins" in data or "total_trades" in data
    print(f"Performance OK")


# Risk
def test_risk(authed):
    r = authed.get(f"{BASE_URL}/api/risk/circuit-breaker")
    assert r.status_code == 200
    data = r.json()
    print(f"Risk circuit-breaker OK: {list(data.keys())[:5]}")


# Market Intel
def test_market_intel(authed):
    r = authed.get(f"{BASE_URL}/api/orderflow")
    assert r.status_code == 200
    data = r.json()
    print(f"Market Intel/orderflow OK: {list(data.keys()) if isinstance(data, dict) else type(data)}")


# Trades
def test_trades(authed):
    r = authed.get(f"{BASE_URL}/api/trades")
    assert r.status_code == 200
    data = r.json()
    print(f"Trades OK, count={len(data) if isinstance(data, list) else 'dict'}")


# Bot status
def test_bot_status(authed):
    r = authed.get(f"{BASE_URL}/api/bot/status")
    assert r.status_code == 200
    data = r.json()
    assert "mode" in data
    print(f"Bot status OK: mode={data.get('mode')}, running={data.get('running')}")
