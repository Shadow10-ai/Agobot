"""
Test suite for DRY/LIVE mode toggle feature - Iteration 6
Tests the new mode toggle endpoints and related functionality.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "user@example.com"
TEST_PASSWORD = "password"


class TestModeToggleEndpoints:
    """Tests for DRY/LIVE mode toggle API endpoints"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip("Authentication failed - skipping tests")
        self.token = response.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def test_get_bot_mode_returns_expected_fields(self):
        """GET /api/bot/mode returns mode, binance_connected, binance_keys_configured"""
        response = requests.get(
            f"{BASE_URL}/api/bot/mode",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify all expected fields are present
        assert "mode" in data, "Response should contain 'mode' field"
        assert "binance_connected" in data, "Response should contain 'binance_connected' field"
        assert "binance_keys_configured" in data, "Response should contain 'binance_keys_configured' field"
        
        # Verify mode is valid
        assert data["mode"] in ["DRY", "LIVE"], f"Mode should be DRY or LIVE, got {data['mode']}"
        
        # Verify boolean types
        assert isinstance(data["binance_connected"], bool)
        assert isinstance(data["binance_keys_configured"], bool)

    def test_put_bot_mode_dry_success(self):
        """PUT /api/bot/mode with mode='DRY' should succeed"""
        response = requests.put(
            f"{BASE_URL}/api/bot/mode",
            json={"mode": "DRY"},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["mode"] == "DRY"
        assert "binance_connected" in data
        assert "message" in data
        assert "simulated" in data["message"].lower()

    def test_put_bot_mode_live_fails_without_binance(self):
        """PUT /api/bot/mode with mode='LIVE' returns error when Binance unavailable"""
        response = requests.put(
            f"{BASE_URL}/api/bot/mode",
            json={"mode": "LIVE"},
            headers=self.headers
        )
        # Should return 400 because Binance client is not connected
        assert response.status_code == 400
        data = response.json()
        
        assert "detail" in data
        assert "binance" in data["detail"].lower() or "live" in data["detail"].lower()

    def test_put_bot_mode_invalid_returns_400(self):
        """PUT /api/bot/mode with invalid mode returns 400"""
        response = requests.put(
            f"{BASE_URL}/api/bot/mode",
            json={"mode": "INVALID"},
            headers=self.headers
        )
        assert response.status_code == 400
        data = response.json()
        
        assert "detail" in data
        assert "dry" in data["detail"].lower() or "live" in data["detail"].lower()

    def test_get_bot_mode_requires_auth(self):
        """GET /api/bot/mode without auth returns 401/403"""
        response = requests.get(f"{BASE_URL}/api/bot/mode")
        assert response.status_code in [401, 403]

    def test_put_bot_mode_requires_auth(self):
        """PUT /api/bot/mode without auth returns 401/403"""
        response = requests.put(
            f"{BASE_URL}/api/bot/mode",
            json={"mode": "DRY"}
        )
        assert response.status_code in [401, 403]


class TestHealthEndpoint:
    """Tests for health endpoint - still works after mode toggle changes"""

    def test_health_endpoint_no_auth(self):
        """GET /api/health works without auth"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "ok"
        assert "database" in data
        assert "bot_running" in data
        assert "mode" in data


class TestAuthEndpoint:
    """Tests for auth endpoint - still works after changes"""

    def test_login_success(self):
        """POST /api/auth/login still works"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == TEST_EMAIL


class TestDashboardWithMode:
    """Tests for dashboard endpoint including mode in bot_status"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip("Authentication failed")
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_dashboard_bot_status_includes_mode(self):
        """GET /api/dashboard returns bot_status with correct mode"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "bot_status" in data
        bot_status = data["bot_status"]
        
        assert "mode" in bot_status
        assert bot_status["mode"] in ["DRY", "LIVE"]
        assert "running" in bot_status
        assert "paused" in bot_status


class TestOtherEndpoints:
    """Tests that other critical endpoints still work"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip("Authentication failed")
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_bot_config_endpoint(self):
        """GET /api/bot/config still works"""
        response = requests.get(
            f"{BASE_URL}/api/bot/config",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Config should have trading parameters
        assert "symbols" in data
        assert "base_usdt_per_trade" in data

    def test_positions_endpoint(self):
        """GET /api/positions still works"""
        response = requests.get(
            f"{BASE_URL}/api/positions",
            headers=self.headers
        )
        assert response.status_code == 200

    def test_trades_endpoint(self):
        """GET /api/trades still works"""
        response = requests.get(
            f"{BASE_URL}/api/trades",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data
        assert "total" in data

    def test_leaderboard_endpoint(self):
        """GET /api/leaderboard still works"""
        response = requests.get(
            f"{BASE_URL}/api/leaderboard",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "symbol_rankings" in data

    def test_performance_endpoint(self):
        """GET /api/performance still works"""
        response = requests.get(
            f"{BASE_URL}/api/performance",
            headers=self.headers
        )
        assert response.status_code == 200
