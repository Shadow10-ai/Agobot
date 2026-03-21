"""
Phase 4: Market Intelligence Features Tests
- Order Flow Analysis (/api/orderflow, /api/orderflow/{symbol})
- Funding Rate Arbitrage (/api/funding-rates)
- Whale Activity Tracking (/api/whale-activity)
- Regression: dashboard, ml/status, risk/circuit-breaker, bot/status, auth
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


@pytest.fixture(scope="module")
def auth_token():
    """Attempt login first; if user doesn't exist, register then login."""
    # Try login
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "test@example.com",
        "password": "password"
    })
    if resp.status_code == 200:
        return resp.json().get("access_token")

    # Register
    reg = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": "test@example.com",
        "password": "password",
        "name": "Test User"
    })
    if reg.status_code == 200:
        return reg.json().get("access_token")

    pytest.skip("Authentication failed - skipping all tests")


@pytest.fixture
def api_client(auth_token):
    """Authenticated requests session."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


# ===================================================================
# AUTH TESTS
# ===================================================================

class TestAuth:
    """Auth register/login tests."""

    def test_register_new_user(self):
        """Register a test user (may already exist - check 200 or 400)."""
        resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": "testregister_phase4@example.com",
            "password": "password123",
            "name": "Phase4 Test User"
        })
        assert resp.status_code in [200, 400], f"Unexpected status: {resp.status_code}, body: {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert "access_token" in data
            print(f"Registration succeeded: {data.get('user', {}).get('email')}")
        else:
            print("User already exists - expected 400")

    def test_login_valid_credentials(self):
        """Login with valid credentials returns token."""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@example.com",
            "password": "password"
        })
        # Could be 200 or 401 if user not registered yet; in CI environment, first register
        if resp.status_code == 401:
            # Register first
            reg = requests.post(f"{BASE_URL}/api/auth/register", json={
                "email": "test@example.com",
                "password": "password",
                "name": "Test User"
            })
            assert reg.status_code == 200, f"Registration failed: {reg.text}"
            resp = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": "test@example.com",
                "password": "password"
            })
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        assert "access_token" in data
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 10
        print(f"Login OK - token length: {len(data['access_token'])}")

    def test_login_invalid_credentials(self):
        """Login with wrong password returns 401."""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@example.com",
            "password": "wrongpassword123456"
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("Invalid credentials correctly rejected with 401")


# ===================================================================
# ORDER FLOW TESTS
# ===================================================================

class TestOrderFlow:
    """Order Flow Analysis endpoint tests."""

    def test_orderflow_all_symbols_status(self, api_client):
        """GET /api/orderflow returns 200."""
        resp = api_client.get(f"{BASE_URL}/api/orderflow")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("GET /api/orderflow returned 200")

    def test_orderflow_all_symbols_structure(self, api_client):
        """GET /api/orderflow returns symbols dict with expected fields."""
        resp = api_client.get(f"{BASE_URL}/api/orderflow")
        assert resp.status_code == 200
        data = resp.json()

        assert "symbols" in data, f"Missing 'symbols' key: {data.keys()}"
        symbols = data["symbols"]
        assert len(symbols) > 0, "symbols dict is empty"

        # Check first symbol for required fields
        first_symbol = list(symbols.keys())[0]
        sym_data = symbols[first_symbol]
        assert "pressure" in sym_data, f"Missing 'pressure' for {first_symbol}"
        assert "imbalance_ratio" in sym_data, f"Missing 'imbalance_ratio' for {first_symbol}"
        assert "bid_walls" in sym_data, f"Missing 'bid_walls' for {first_symbol}"
        assert "ask_walls" in sym_data, f"Missing 'ask_walls' for {first_symbol}"
        print(f"Order flow symbol data OK: {first_symbol} -> pressure={sym_data['pressure']}, imbalance={sym_data['imbalance_ratio']}")

    def test_orderflow_pressure_valid_values(self, api_client):
        """All symbols have valid pressure values."""
        resp = api_client.get(f"{BASE_URL}/api/orderflow")
        assert resp.status_code == 200
        data = resp.json()
        valid_pressures = {"STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"}
        for symbol, sym_data in data["symbols"].items():
            assert sym_data["pressure"] in valid_pressures, \
                f"Invalid pressure '{sym_data['pressure']}' for {symbol}"
        print(f"All {len(data['symbols'])} symbols have valid pressure values")

    def test_orderflow_symbol_btcusdt(self, api_client):
        """GET /api/orderflow/BTCUSDT returns detailed order book."""
        resp = api_client.get(f"{BASE_URL}/api/orderflow/BTCUSDT")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Required fields
        assert "symbol" in data and data["symbol"] == "BTCUSDT"
        assert "depth_levels" in data, "Missing 'depth_levels'"
        assert "total_bid_volume" in data, "Missing 'total_bid_volume'"
        assert "total_ask_volume" in data, "Missing 'total_ask_volume'"
        assert "bid_walls" in data, "Missing 'bid_walls'"
        assert "ask_walls" in data, "Missing 'ask_walls'"
        assert "imbalance_ratio" in data
        assert "pressure" in data

        # Depth levels should have 4 entries
        depth = data["depth_levels"]
        assert len(depth) == 4, f"Expected 4 depth levels, got {len(depth)}: {list(depth.keys())}"
        for level_key, level_data in depth.items():
            assert "bid_volume" in level_data
            assert "ask_volume" in level_data
            assert "bid_usdt" in level_data
            assert "ask_usdt" in level_data
        print(f"BTCUSDT order book OK: bid_vol={data['total_bid_volume']}, ask_vol={data['total_ask_volume']}, pressure={data['pressure']}")

    def test_orderflow_symbol_ethusdt(self, api_client):
        """GET /api/orderflow/ETHUSDT returns valid data."""
        resp = api_client.get(f"{BASE_URL}/api/orderflow/ETHUSDT")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["symbol"] == "ETHUSDT"
        assert data["total_bid_volume"] > 0
        assert data["total_ask_volume"] > 0
        print(f"ETHUSDT order book OK: bid={data['total_bid_volume']}, ask={data['total_ask_volume']}")

    def test_orderflow_invalid_symbol(self, api_client):
        """GET /api/orderflow/FAKEUSDT returns 400."""
        resp = api_client.get(f"{BASE_URL}/api/orderflow/FAKEUSDT")
        assert resp.status_code == 400, f"Expected 400 for invalid symbol, got {resp.status_code}"
        print("Invalid symbol correctly rejected with 400")

    def test_orderflow_unauthenticated(self):
        """GET /api/orderflow without token returns 401 or 403."""
        resp = requests.get(f"{BASE_URL}/api/orderflow")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"
        print(f"Unauthenticated request correctly rejected: {resp.status_code}")


# ===================================================================
# FUNDING RATES TESTS
# ===================================================================

class TestFundingRates:
    """Funding Rate Arbitrage endpoint tests."""

    def test_funding_rates_status(self, api_client):
        """GET /api/funding-rates returns 200."""
        resp = api_client.get(f"{BASE_URL}/api/funding-rates")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("GET /api/funding-rates returned 200")

    def test_funding_rates_structure(self, api_client):
        """GET /api/funding-rates returns rates, arbitrage_opportunities, has_opportunities."""
        resp = api_client.get(f"{BASE_URL}/api/funding-rates")
        assert resp.status_code == 200
        data = resp.json()

        assert "rates" in data, f"Missing 'rates' key: {data.keys()}"
        assert "arbitrage_opportunities" in data, f"Missing 'arbitrage_opportunities': {data.keys()}"
        assert "has_opportunities" in data, f"Missing 'has_opportunities': {data.keys()}"
        assert isinstance(data["has_opportunities"], bool)
        print(f"Funding rates structure OK: {len(data['rates'])} symbols, has_opportunities={data['has_opportunities']}")

    def test_funding_rates_per_symbol_fields(self, api_client):
        """Each symbol in rates has current_rate, sentiment, arb_opportunity, annualized_yield."""
        resp = api_client.get(f"{BASE_URL}/api/funding-rates")
        assert resp.status_code == 200
        data = resp.json()
        rates = data["rates"]
        assert len(rates) > 0, "rates dict is empty"

        for symbol, sym_data in rates.items():
            assert "current_rate" in sym_data, f"Missing 'current_rate' for {symbol}"
            assert "sentiment" in sym_data, f"Missing 'sentiment' for {symbol}"
            assert "arb_opportunity" in sym_data, f"Missing 'arb_opportunity' for {symbol}"
            assert "annualized_yield" in sym_data, f"Missing 'annualized_yield' for {symbol}"
            assert isinstance(sym_data["arb_opportunity"], bool)
        print(f"All {len(rates)} funding rate symbols have required fields")

    def test_funding_rates_sentiment_values(self, api_client):
        """Sentiment values are valid."""
        resp = api_client.get(f"{BASE_URL}/api/funding-rates")
        assert resp.status_code == 200
        data = resp.json()
        valid_sentiments = {"EXTREMELY_BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "EXTREMELY_BEARISH"}
        for symbol, sym_data in data["rates"].items():
            assert sym_data["sentiment"] in valid_sentiments, \
                f"Invalid sentiment '{sym_data['sentiment']}' for {symbol}"
        print(f"All sentiment values are valid")

    def test_funding_rates_unauthenticated(self):
        """GET /api/funding-rates without token returns 401 or 403."""
        resp = requests.get(f"{BASE_URL}/api/funding-rates")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print(f"Unauthenticated request correctly rejected: {resp.status_code}")


# ===================================================================
# WHALE ACTIVITY TESTS
# ===================================================================

class TestWhaleActivity:
    """Whale Activity Tracking endpoint tests."""

    def test_whale_activity_status(self, api_client):
        """GET /api/whale-activity returns 200."""
        resp = api_client.get(f"{BASE_URL}/api/whale-activity")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("GET /api/whale-activity returned 200")

    def test_whale_activity_structure(self, api_client):
        """GET /api/whale-activity returns all required top-level fields."""
        resp = api_client.get(f"{BASE_URL}/api/whale-activity")
        assert resp.status_code == 200
        data = resp.json()

        required_fields = ["whale_trades", "total_whale_buys", "total_whale_sells",
                           "net_flow", "whale_signal", "symbol_breakdown"]
        for field in required_fields:
            assert field in data, f"Missing required field: '{field}'"
        print(f"Whale activity structure OK: signal={data['whale_signal']}, "
              f"buys=${data['total_whale_buys']}, sells=${data['total_whale_sells']}, net=${data['net_flow']}")

    def test_whale_activity_signal_values(self, api_client):
        """whale_signal must be ACCUMULATION, DISTRIBUTION, or NEUTRAL."""
        resp = api_client.get(f"{BASE_URL}/api/whale-activity")
        assert resp.status_code == 200
        data = resp.json()
        valid_signals = {"ACCUMULATION", "DISTRIBUTION", "NEUTRAL"}
        assert data["whale_signal"] in valid_signals, \
            f"Invalid whale_signal: '{data['whale_signal']}'"
        print(f"whale_signal valid: {data['whale_signal']}")

    def test_whale_activity_trades_list(self, api_client):
        """whale_trades is a list with expected trade fields."""
        resp = api_client.get(f"{BASE_URL}/api/whale-activity")
        assert resp.status_code == 200
        data = resp.json()
        trades = data["whale_trades"]
        assert isinstance(trades, list), f"whale_trades should be list, got {type(trades)}"

        if trades:
            trade = trades[0]
            assert "symbol" in trade, "Missing 'symbol' in trade"
            assert "usdt_value" in trade, "Missing 'usdt_value' in trade"
            assert "side" in trade, "Missing 'side' in trade"
            assert "time" in trade, "Missing 'time' in trade"
            assert trade["side"] in ["BUY", "SELL"], f"Invalid side: {trade['side']}"
        print(f"whale_trades list OK: {len(trades)} trades, first={trades[0] if trades else 'empty'}")

    def test_whale_activity_symbol_breakdown(self, api_client):
        """symbol_breakdown has per-symbol buy/sell volumes and signal."""
        resp = api_client.get(f"{BASE_URL}/api/whale-activity")
        assert resp.status_code == 200
        data = resp.json()
        breakdown = data["symbol_breakdown"]
        assert isinstance(breakdown, dict)

        valid_signals = {"ACCUMULATION", "DISTRIBUTION", "NEUTRAL"}
        for sym, sym_data in breakdown.items():
            assert "buy_volume" in sym_data, f"Missing buy_volume for {sym}"
            assert "sell_volume" in sym_data, f"Missing sell_volume for {sym}"
            assert "signal" in sym_data, f"Missing signal for {sym}"
            assert sym_data["signal"] in valid_signals, f"Invalid signal for {sym}: {sym_data['signal']}"
        print(f"symbol_breakdown OK: {len(breakdown)} symbols")

    def test_whale_activity_unauthenticated(self):
        """GET /api/whale-activity without token returns 401 or 403."""
        resp = requests.get(f"{BASE_URL}/api/whale-activity")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print(f"Unauthenticated request correctly rejected: {resp.status_code}")


# ===================================================================
# REGRESSION TESTS
# ===================================================================

class TestRegression:
    """Regression tests for existing endpoints."""

    def test_health_check(self):
        """GET /api/health returns 200 (no auth required)."""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"
        print(f"Health OK: db={data.get('database')}, bot={data.get('bot_running')}")

    def test_dashboard_status(self, api_client):
        """GET /api/dashboard returns 200 with valid data."""
        resp = api_client.get(f"{BASE_URL}/api/dashboard")
        assert resp.status_code == 200, f"Dashboard returned {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, dict)
        print(f"Dashboard OK: keys={list(data.keys())[:6]}")

    def test_ml_status(self, api_client):
        """GET /api/ml/status returns 200 with model metrics."""
        resp = api_client.get(f"{BASE_URL}/api/ml/status")
        assert resp.status_code == 200, f"ML status returned {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, dict)
        print(f"ML status OK: keys={list(data.keys())[:6]}")

    def test_risk_circuit_breaker(self, api_client):
        """GET /api/risk/circuit-breaker returns drawdown data."""
        resp = api_client.get(f"{BASE_URL}/api/risk/circuit-breaker")
        assert resp.status_code == 200, f"Circuit breaker returned {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "tripped" in data, f"Missing 'tripped': {data.keys()}"
        assert "current_drawdown" in data, f"Missing 'current_drawdown': {data.keys()}"
        assert isinstance(data["tripped"], bool)
        print(f"Circuit breaker OK: tripped={data['tripped']}, drawdown={data['current_drawdown']}")

    def test_bot_status(self, api_client):
        """GET /api/bot/status returns bot state."""
        resp = api_client.get(f"{BASE_URL}/api/bot/status")
        assert resp.status_code == 200, f"Bot status returned {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, dict)
        print(f"Bot status OK: running={data.get('running')}, mode={data.get('mode')}")
