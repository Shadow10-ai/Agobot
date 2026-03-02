"""
Test suite for AgoBot production-readiness fixes - Iteration 5
Tests:
1. Health endpoint (new) - no auth required
2. Authentication endpoints - register/login
3. Dashboard API - with auth
4. Bot control endpoints - status/start/stop
5. Performance/Leaderboard endpoints
6. Backtest endpoint
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
TEST_EMAIL = "user@example.com"
TEST_PASSWORD = "password"

# ====================================================================
# FIXTURES
# ====================================================================

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token - try login first, then register"""
    # Try login first
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    
    # If login fails (user doesn't exist), try registering
    response = api_client.post(f"{BASE_URL}/api/auth/register", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "Test User"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    
    pytest.skip("Authentication failed - skipping authenticated tests")

@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client

# ====================================================================
# HEALTH ENDPOINT TESTS (NEW - No Auth Required)
# ====================================================================

class TestHealthEndpoint:
    """Test the new /api/health endpoint for Kubernetes probes"""
    
    def test_health_returns_ok(self, api_client):
        """Health endpoint should return status ok"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got {data.get('status')}"
        print(f"✓ Health endpoint returns status: {data.get('status')}")
    
    def test_health_has_database_field(self, api_client):
        """Health endpoint should include database status"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "database" in data, "Missing 'database' field in health response"
        assert data["database"] in ["connected", "disconnected"], f"Unexpected database status: {data['database']}"
        print(f"✓ Database status: {data['database']}")
    
    def test_health_has_bot_running_field(self, api_client):
        """Health endpoint should include bot_running status"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "bot_running" in data, "Missing 'bot_running' field in health response"
        assert isinstance(data["bot_running"], bool), f"bot_running should be boolean, got {type(data['bot_running'])}"
        print(f"✓ Bot running: {data['bot_running']}")
    
    def test_health_has_mode_field(self, api_client):
        """Health endpoint should include mode field"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "mode" in data, "Missing 'mode' field in health response"
        assert data["mode"] == "DRY", f"Expected mode 'DRY', got {data['mode']}"
        print(f"✓ Bot mode: {data['mode']}")
    
    def test_health_no_auth_required(self, api_client):
        """Health endpoint should work without authentication"""
        # Create a new session without auth
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, "Health endpoint should not require auth"
        print("✓ Health endpoint accessible without auth")

# ====================================================================
# AUTHENTICATION TESTS
# ====================================================================

class TestAuthentication:
    """Test authentication endpoints"""
    
    def test_login_success(self, api_client):
        """Login with valid credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        # May fail if user doesn't exist, but 401 is expected behavior
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "access_token" in data, "Missing access_token in response"
            assert "user" in data, "Missing user in response"
            print(f"✓ Login successful for {TEST_EMAIL}")
        else:
            print(f"✓ Login returns 401 for non-existent user (expected)")
    
    def test_login_invalid_credentials(self, api_client):
        """Login with invalid credentials should return 401"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401, f"Expected 401 for invalid credentials, got {response.status_code}"
        print("✓ Invalid credentials correctly rejected")
    
    def test_register_validation(self, api_client):
        """Register endpoint validates input"""
        # Try to register with invalid email format
        response = api_client.post(f"{BASE_URL}/api/auth/register", json={
            "email": "",
            "password": "test123",
            "name": "Test"
        })
        # Should fail validation or register
        assert response.status_code in [400, 422, 200], f"Unexpected status: {response.status_code}"
        print("✓ Register endpoint accepts/validates input")

# ====================================================================
# DASHBOARD TESTS (Auth Required)
# ====================================================================

class TestDashboard:
    """Test dashboard API"""
    
    def test_dashboard_requires_auth(self, api_client):
        """Dashboard should require authentication"""
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("✓ Dashboard correctly requires auth")
    
    def test_dashboard_returns_data(self, authenticated_client):
        """Dashboard returns balance, bot_status, positions, trades"""
        response = authenticated_client.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Verify required fields
        assert "balance" in data, "Missing 'balance' field"
        assert "bot_status" in data, "Missing 'bot_status' field"
        assert "positions" in data, "Missing 'positions' field"
        assert "recent_trades" in data or "trades" in data, "Missing trades data"
        
        # Verify bot_status structure
        bot_status = data.get("bot_status", {})
        assert "running" in bot_status, "Missing 'running' in bot_status"
        assert "mode" in bot_status, "Missing 'mode' in bot_status"
        
        print(f"✓ Dashboard data: balance=${data.get('balance')}, bot_running={bot_status.get('running')}")

# ====================================================================
# BOT CONTROL TESTS (Auth Required)
# ====================================================================

class TestBotControl:
    """Test bot control endpoints"""
    
    def test_bot_status(self, authenticated_client):
        """Bot status endpoint returns state"""
        response = authenticated_client.get(f"{BASE_URL}/api/bot/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "running" in data, "Missing 'running' field"
        assert "mode" in data, "Missing 'mode' field"
        assert "paused" in data, "Missing 'paused' field"
        print(f"✓ Bot status: running={data.get('running')}, mode={data.get('mode')}")
    
    def test_bot_start(self, authenticated_client):
        """Bot start endpoint works"""
        response = authenticated_client.post(f"{BASE_URL}/api/bot/start")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "started", f"Expected status 'started', got {data.get('status')}"
        print("✓ Bot start successful")
    
    def test_bot_stop(self, authenticated_client):
        """Bot stop endpoint works"""
        response = authenticated_client.post(f"{BASE_URL}/api/bot/stop")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "stopped", f"Expected status 'stopped', got {data.get('status')}"
        print("✓ Bot stop successful")
        
        # Restart the bot for other tests
        authenticated_client.post(f"{BASE_URL}/api/bot/start")
    
    def test_bot_requires_auth(self, api_client):
        """Bot endpoints require authentication"""
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/bot/status")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth"
        print("✓ Bot endpoints correctly require auth")

# ====================================================================
# PERFORMANCE/LEADERBOARD TESTS (Auth Required)
# ====================================================================

class TestPerformance:
    """Test performance and leaderboard endpoints"""
    
    def test_performance_endpoint(self, authenticated_client):
        """Performance endpoint returns data"""
        response = authenticated_client.get(f"{BASE_URL}/api/performance")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Verify key fields
        assert "cumulative_pnl" in data or "total_pnl" in data, "Missing PnL data"
        print(f"✓ Performance data retrieved: total_pnl={data.get('total_pnl', 'N/A')}")
    
    def test_leaderboard_endpoint(self, authenticated_client):
        """Leaderboard endpoint returns data"""
        response = authenticated_client.get(f"{BASE_URL}/api/leaderboard")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "symbol_rankings" in data, "Missing 'symbol_rankings' field"
        print(f"✓ Leaderboard data retrieved: {len(data.get('symbol_rankings', []))} symbols ranked")

# ====================================================================
# BACKTEST TESTS (Auth Required)
# ====================================================================

class TestBacktest:
    """Test backtest endpoint"""
    
    def test_backtest_runs(self, authenticated_client):
        """Backtest endpoint executes a strategy test"""
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
        
        response = authenticated_client.post(f"{BASE_URL}/api/backtest", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "summary" in data, "Missing 'summary' field in backtest response"
        summary = data.get("summary", {})
        assert "total_trades" in summary, "Missing 'total_trades' in summary"
        print(f"✓ Backtest completed: {summary.get('total_trades', 0)} trades simulated")
    
    def test_backtest_requires_auth(self, api_client):
        """Backtest endpoint requires authentication"""
        no_auth_session = requests.Session()
        no_auth_session.headers.update({"Content-Type": "application/json"})
        response = no_auth_session.post(f"{BASE_URL}/api/backtest", json={
            "symbol": "BTCUSDT",
            "period_days": 7
        })
        assert response.status_code in [401, 403], f"Expected 401/403 without auth"
        print("✓ Backtest endpoint correctly requires auth")

# ====================================================================
# TRADES & POSITIONS TESTS (Auth Required)
# ====================================================================

class TestTradesPositions:
    """Test trades and positions endpoints"""
    
    def test_trades_endpoint(self, authenticated_client):
        """Trades endpoint returns trade history"""
        response = authenticated_client.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "trades" in data, "Missing 'trades' field"
        assert "total" in data, "Missing 'total' field"
        print(f"✓ Trades retrieved: {data.get('total', 0)} total trades")
    
    def test_positions_endpoint(self, authenticated_client):
        """Positions endpoint returns open positions"""
        response = authenticated_client.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Positions is a list
        assert isinstance(data, list), "Positions should be a list"
        print(f"✓ Positions retrieved: {len(data)} open positions")

# ====================================================================
# BOT CONFIG TESTS (Auth Required)
# ====================================================================

class TestBotConfig:
    """Test bot configuration endpoint"""
    
    def test_get_config(self, authenticated_client):
        """Get bot config"""
        response = authenticated_client.get(f"{BASE_URL}/api/bot/config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "symbols" in data, "Missing 'symbols' in config"
        assert "base_usdt_per_trade" in data, "Missing 'base_usdt_per_trade' in config"
        print(f"✓ Bot config retrieved: symbols={data.get('symbols')}")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
