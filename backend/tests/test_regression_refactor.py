"""
AgoBot Regression Test Suite - Post-Refactor (Iteration 12)
Tests all endpoints after major server.py refactor (3518 -> 109 lines).
Covers: Auth, Dashboard, Bot, Trading, ML, Risk, Market Intel, Backtest, Misc
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

TEST_EMAIL = "regression_test@example.com"
TEST_PASSWORD = "testpass123"
TEST_NAME = "Regression Tester"


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Try login first, then register if needed."""
    resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if resp.status_code == 200:
        return resp.json().get("access_token")

    # Register new user
    resp = api_client.post(f"{BASE_URL}/api/auth/register", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": TEST_NAME
    })
    if resp.status_code == 200:
        return resp.json().get("access_token")

    pytest.skip(f"Auth failed: {resp.status_code} - {resp.text}")


@pytest.fixture(scope="module")
def auth_client(api_client, auth_token):
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


# =====================================================================
# HEALTH (no auth required)
# =====================================================================

class TestHealth:
    """GET /api/health — no auth required"""

    def test_health_returns_200(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "status" in data, "Missing 'status' field"
        assert data["status"] in ("healthy", "ok", "degraded"), f"Unexpected status: {data['status']}"
        print(f"✓ Health: {data}")

    def test_health_no_auth_needed(self):
        s = requests.Session()
        resp = s.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200, "Health endpoint should not require auth"
        print("✓ Health accessible without auth")

    def test_health_database_field(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/health")
        data = resp.json()
        assert "database" in data, "Missing 'database' field in health response"
        print(f"✓ Health database field: {data.get('database')}")


# =====================================================================
# AUTHENTICATION
# =====================================================================

class TestAuth:
    """Register and login flows"""

    def test_register_new_user(self, api_client):
        """Register should succeed or return 400 if already exists."""
        resp = api_client.post(f"{BASE_URL}/api/auth/register", json={
            "email": "reg_new_user_iter12@example.com",
            "password": "testpass123",
            "name": "New User"
        })
        assert resp.status_code in (200, 400), f"Unexpected: {resp.status_code} {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert "access_token" in data
            assert "user" in data
            assert data["user"]["email"] == "reg_new_user_iter12@example.com"
            print("✓ Register: new user created")
        else:
            print("✓ Register: user already exists (400 expected)")

    def test_login_success(self, auth_client):
        """auth_token fixture ensures user is registered before testing login."""
        resp = auth_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "access_token" in data
        assert "user" in data
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 0
        print(f"✓ Login success: {data['user']['email']}")

    def test_login_invalid_credentials(self, api_client):
        resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": "nonexistent_xyz@example.com",
            "password": "wrongpassword"
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Login rejects invalid credentials")

    def test_auth_me(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "email" in data
        assert data["email"] == TEST_EMAIL
        print(f"✓ /auth/me: {data['email']}")


# =====================================================================
# DASHBOARD
# =====================================================================

class TestDashboard:
    """GET /api/dashboard"""

    def test_dashboard_requires_auth(self, api_client):
        s = requests.Session()
        resp = s.get(f"{BASE_URL}/api/dashboard")
        assert resp.status_code in (401, 403), f"Should require auth, got {resp.status_code}"
        print("✓ Dashboard requires auth")

    def test_dashboard_returns_required_fields(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/dashboard")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Check required fields
        assert "balance" in data, "Missing 'balance'"
        assert "positions" in data, "Missing 'positions'"
        assert "recent_trades" in data, "Missing 'recent_trades'"
        assert "prices" in data, "Missing 'prices'"
        assert "bot_status" in data, "Missing 'bot_status'"

        # Check bot_status sub-fields
        bot_status = data["bot_status"]
        assert "running" in bot_status, "Missing bot_status.running"
        assert "paused" in bot_status, "Missing bot_status.paused"
        assert "mode" in bot_status, "Missing bot_status.mode"

        print(f"✓ Dashboard OK: balance={data['balance']}, mode={bot_status['mode']}")

    def test_dashboard_prices_dict(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/dashboard")
        data = resp.json()
        assert isinstance(data["prices"], dict), "prices should be a dict"
        print(f"✓ Dashboard prices: {list(data['prices'].keys())}")

    def test_dashboard_balance_numeric(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/dashboard")
        data = resp.json()
        assert isinstance(data["balance"], (int, float)), "balance should be numeric"
        assert data["balance"] >= 0, "balance should be non-negative"
        print(f"✓ Dashboard balance: {data['balance']}")


# =====================================================================
# BOT STATUS / START / STOP / CONFIG / MODE
# =====================================================================

class TestBotControl:
    """Bot control endpoints"""

    def test_bot_status_fields(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/bot/status")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "running" in data, "Missing 'running'"
        assert "paused" in data, "Missing 'paused'"
        assert "mode" in data, "Missing 'mode'"
        assert data["mode"] in ("DRY", "LIVE"), f"Unexpected mode: {data['mode']}"
        print(f"✓ Bot status: running={data['running']}, paused={data['paused']}, mode={data['mode']}")

    def test_bot_start(self, auth_client):
        resp = auth_client.post(f"{BASE_URL}/api/bot/start")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("status") == "started", f"Unexpected status: {data}"
        print("✓ Bot start: OK")

    def test_bot_stop(self, auth_client):
        resp = auth_client.post(f"{BASE_URL}/api/bot/stop")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("status") == "stopped", f"Unexpected status: {data}"
        print("✓ Bot stop: OK")
        # restart for subsequent tests
        auth_client.post(f"{BASE_URL}/api/bot/start")

    def test_get_bot_config(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/bot/config")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "symbols" in data, "Missing 'symbols' in config"
        assert isinstance(data["symbols"], list), "symbols should be a list"
        print(f"✓ Bot config: symbols={data['symbols']}")

    def test_put_bot_config(self, auth_client):
        """PUT /api/bot/config should update and return config"""
        resp = auth_client.put(f"{BASE_URL}/api/bot/config", json={
            "min_confidence_score": 0.65
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "symbols" in data, "Updated config should still have 'symbols'"
        print(f"✓ Bot config updated: min_confidence_score set")

    def test_get_bot_mode(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/bot/mode")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "mode" in data, "Missing 'mode'"
        assert data["mode"] in ("DRY", "LIVE"), f"Unexpected mode: {data['mode']}"
        assert "binance_connected" in data, "Missing 'binance_connected'"
        print(f"✓ Bot mode: {data['mode']}, binance_connected={data['binance_connected']}")

    def test_put_bot_mode_dry(self, auth_client):
        """Switch to DRY mode"""
        resp = auth_client.put(f"{BASE_URL}/api/bot/mode", json={"mode": "DRY"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("mode") == "DRY", f"Expected DRY, got {data.get('mode')}"
        print("✓ Bot mode toggled to DRY")

    def test_put_bot_mode_invalid(self, auth_client):
        """Invalid mode returns 400"""
        resp = auth_client.put(f"{BASE_URL}/api/bot/mode", json={"mode": "INVALID"})
        assert resp.status_code == 400, f"Expected 400 for invalid mode, got {resp.status_code}"
        print("✓ Invalid mode correctly returns 400")


# =====================================================================
# TRADING: TRADES & PERFORMANCE
# =====================================================================

class TestTrading:
    """Trades and performance endpoints"""

    def test_get_trades(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/trades")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "trades" in data, "Missing 'trades'"
        assert "total" in data, "Missing 'total'"
        assert isinstance(data["trades"], list), "trades should be list"
        assert isinstance(data["total"], int), "total should be int"
        print(f"✓ Trades: {data['total']} total")

    def test_get_performance(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/performance")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "cumulative_pnl" in data, "Missing 'cumulative_pnl'"
        assert "total_trades" in data, "Missing 'total_trades'"
        assert "win_rate" in data, "Missing 'win_rate'"
        print(f"✓ Performance: total_trades={data['total_trades']}, win_rate={data['win_rate']}")

    def test_get_leaderboard(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/leaderboard")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "symbol_rankings" in data, "Missing 'symbol_rankings'"
        assert "best_trades" in data, "Missing 'best_trades'"
        assert "worst_trades" in data, "Missing 'worst_trades'"
        assert "streaks" in data, "Missing 'streaks'"
        print(f"✓ Leaderboard: {len(data['symbol_rankings'])} symbols ranked")

    def test_get_prices(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/prices")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, dict), "Prices should be a dict"
        # Should have at least one symbol
        assert len(data) > 0, "Prices dict should not be empty"
        print(f"✓ Prices: {list(data.keys())}")


# =====================================================================
# ML ENDPOINTS
# =====================================================================

class TestML:
    """ML status, training, dataset"""

    def test_ml_status(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/ml/status")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "status" in data, "Missing 'status'"
        assert "accuracy" in data, "Missing 'accuracy'"
        assert "feature_importance" in data, "Missing 'feature_importance'"
        assert data["status"] in ("ACTIVE", "WAITING", "TRAINING", "UNTRAINED"), f"Unexpected ML status: {data['status']}"
        print(f"✓ ML status: {data['status']}, accuracy={data['accuracy']}")

    def test_ml_dataset(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/ml/dataset")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "samples" in data, "Missing 'samples'"
        assert "total" in data, "Missing 'total'"
        assert isinstance(data["samples"], list), "samples should be list"
        print(f"✓ ML dataset: {data['total']} total samples")

    def test_dataset_stats(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/dataset/stats")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "total_signals" in data, "Missing 'total_signals'"
        assert "outcomes" in data, "Missing 'outcomes'"
        print(f"✓ Dataset stats: total_signals={data['total_signals']}")


# =====================================================================
# RISK ENDPOINTS
# =====================================================================

class TestRisk:
    """Risk management: circuit breaker, sessions, Monte Carlo, regime"""

    def test_circuit_breaker(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/risk/circuit-breaker")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "tripped" in data, "Missing 'tripped'"
        assert "current_drawdown_pct" in data, "Missing 'current_drawdown_pct'"
        assert "peak_balance" in data, "Missing 'peak_balance'"
        assert "max_drawdown_limit" in data, "Missing 'max_drawdown_limit'"
        print(f"✓ Circuit breaker: tripped={data['tripped']}, drawdown={data['current_drawdown_pct']}")

    def test_risk_sessions(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/risk/sessions")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "session_ok" in data, "Missing 'session_ok'"
        assert "current_hour_utc" in data, "Missing 'current_hour_utc'"
        assert "all_sessions" in data, "Missing 'all_sessions'"
        print(f"✓ Risk sessions: session_ok={data['session_ok']}, hour={data['current_hour_utc']}")

    def test_risk_regime(self, auth_client):
        """GET /api/risk/regime (NOT /risk/market-regime)"""
        resp = auth_client.get(f"{BASE_URL}/api/risk/regime")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "regime" in data, "Missing 'regime'"
        assert "strength" in data, "Missing 'strength'"
        assert "symbol" in data, "Missing 'symbol'"
        assert "all_symbols" in data, "Missing 'all_symbols'"
        print(f"✓ Risk regime: {data['regime']} (symbol={data['symbol']})")

    def test_risk_regime_old_endpoint_not_exist(self, auth_client):
        """Old /risk/market-regime should NOT exist in refactored version"""
        resp = auth_client.get(f"{BASE_URL}/api/risk/market-regime")
        assert resp.status_code == 404, f"Old endpoint should be 404, got {resp.status_code}"
        print("✓ Old /risk/market-regime endpoint correctly returns 404")

    def test_monte_carlo(self, auth_client):
        resp = auth_client.post(
            f"{BASE_URL}/api/risk/monte-carlo",
            params={"n_simulations": 100, "n_trades": 20, "initial_balance": 10000}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Should return simulation results
        assert isinstance(data, dict), "Monte Carlo should return a dict"
        print(f"✓ Monte Carlo: keys={list(data.keys())[:5]}")


# =====================================================================
# MARKET INTEL (MOCKED/SIMULATED)
# =====================================================================

class TestMarketIntel:
    """Order flow, funding rates, whale activity — all SIMULATED"""

    def test_orderflow_summary(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/orderflow")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "symbols" in data, "Missing 'symbols'"
        assert isinstance(data["symbols"], list), "symbols should be a list"
        assert len(data["symbols"]) > 0, "Should have at least one symbol"
        first = data["symbols"][0]
        assert "symbol" in first
        assert "pressure" in first
        assert "imbalance_ratio" in first
        print(f"✓ Order flow: {len(data['symbols'])} symbols, first={first['symbol']}, pressure={first['pressure']}")

    def test_orderflow_symbol(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/orderflow/BTCUSDT")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "pressure" in data, "Missing 'pressure'"
        assert "imbalance_ratio" in data, "Missing 'imbalance_ratio'"
        print(f"✓ BTCUSDT order flow: pressure={data['pressure']}")

    def test_funding_rates(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/funding-rates")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "rates" in data, "Missing 'rates'"
        assert isinstance(data["rates"], dict), "rates should be a dict"
        assert "arb_opportunities" in data or "has_opportunities" in data, "Missing arb_opportunities field"
        print(f"✓ Funding rates: {len(data['rates'])} symbols, arb_opps={data.get('arb_opportunities', data.get('has_opportunities', 'N/A'))}")

    def test_whale_activity(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/whale-activity")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "whale_trades" in data, "Missing 'whale_trades'"
        assert "whale_signal" in data, "Missing 'whale_signal'"
        assert "total_whale_buys" in data, "Missing 'total_whale_buys'"
        assert "total_whale_sells" in data, "Missing 'total_whale_sells'"
        print(f"✓ Whale activity: signal={data['whale_signal']}, buys={data['total_whale_buys']}, sells={data['total_whale_sells']}")


# =====================================================================
# BACKTEST
# =====================================================================

class TestBacktest:
    """Backtest endpoint"""

    def test_backtest_runs(self, auth_client):
        payload = {
            "symbol": "BTCUSDT",
            "period_days": 7,
            "base_usdt_per_trade": 50.0,
            "risk_per_trade_percent": 0.5,
            "rsi_period": 14,
            "rsi_overbought": 70.0,
            "rsi_oversold": 30.0,
            "min_entry_probability": 0.45,
            "trailing_stop_activate_pips": 2.4,
            "trailing_stop_distance_pips": 1.2,
            "atr_sl_multiplier": 1.2,
            "atr_tp_multiplier": 2.4,
            "initial_balance": 10000.0
        }
        resp = auth_client.post(f"{BASE_URL}/api/backtest", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "summary" in data, "Missing 'summary'"
        assert "params" in data, "Missing 'params'"
        summary = data["summary"]
        assert "total_trades" in summary, "Missing 'total_trades' in summary"
        print(f"✓ Backtest: {summary.get('total_trades')} trades simulated")

    def test_backtest_invalid_symbol(self, auth_client):
        resp = auth_client.post(f"{BASE_URL}/api/backtest", json={
            "symbol": "INVALIDXYZ",
            "period_days": 7
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("✓ Backtest correctly rejects invalid symbol")

    def test_backtest_requires_auth(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        resp = s.post(f"{BASE_URL}/api/backtest", json={"symbol": "BTCUSDT", "period_days": 7})
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
        print("✓ Backtest requires auth")


# =====================================================================
# MISC
# =====================================================================

class TestMisc:
    """Prices, dataset stats"""

    def test_prices_endpoint(self, auth_client):
        resp = auth_client.get(f"{BASE_URL}/api/prices")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, dict), "Prices should be a dict"
        assert len(data) > 0, "Prices dict not empty"
        print(f"✓ Prices: {data}")

    def test_filters_endpoint(self, auth_client):
        """GET /api/bot/filters"""
        resp = auth_client.get(f"{BASE_URL}/api/bot/filters")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "filters" in data, "Missing 'filters'"
        assert "cooldown_state" in data, "Missing 'cooldown_state'"
        print(f"✓ Bot filters: {list(data['filters'].keys())[:3]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
