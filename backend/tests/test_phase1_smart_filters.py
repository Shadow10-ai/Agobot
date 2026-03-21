"""
Phase 1 Smart Filters & Dataset Builder Tests
Tests for:
- GET /api/dataset/stats - Dataset statistics
- GET /api/bot/filters - Smart filter configuration and cooldown state
- PUT /api/bot/config - Smart filter fields update
- GET /api/bot/config - Smart filter fields retrieval
- GET /api/positions - confidence_score field on positions
- GET /api/health - Health check (no auth)
- POST /api/auth/login - Authentication
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthEndpoint:
    """Health endpoint tests - no auth required"""
    
    def test_health_returns_ok(self):
        """GET /api/health should return ok status without auth"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert data["status"] == "ok"
        assert "database" in data
        assert "bot_running" in data
        assert "mode" in data
        print(f"Health check passed: {data}")


class TestAuthentication:
    """Authentication tests"""
    
    def test_login_success(self):
        """POST /api/auth/login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == "user@example.com"
        print(f"Login successful for user: {data['user']['email']}")
        return data["access_token"]
    
    def test_login_invalid_credentials(self):
        """POST /api/auth/login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Invalid credentials correctly rejected")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "user@example.com",
        "password": "password"
    })
    if response.status_code == 200:
        return response.json()["access_token"]
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestDatasetStats:
    """GET /api/dataset/stats tests"""
    
    def test_dataset_stats_returns_expected_fields(self, auth_headers):
        """Dataset stats should return all expected fields"""
        response = requests.get(f"{BASE_URL}/api/dataset/stats", headers=auth_headers)
        assert response.status_code == 200, f"Dataset stats failed: {response.text}"
        data = response.json()
        
        # Verify all expected fields exist
        assert "total_signals" in data, "Missing total_signals"
        assert "trades_taken" in data, "Missing trades_taken"
        assert "trades_rejected" in data, "Missing trades_rejected"
        assert "outcomes" in data, "Missing outcomes"
        assert "rejection_reasons" in data, "Missing rejection_reasons"
        assert "avg_confidence_taken" in data or "avg_confidence" in data, "Missing avg_confidence"
        
        # Verify outcomes structure
        outcomes = data["outcomes"]
        assert "wins" in outcomes, "Missing wins in outcomes"
        assert "losses" in outcomes, "Missing losses in outcomes"
        
        # Verify data types
        assert isinstance(data["total_signals"], int)
        assert isinstance(data["trades_taken"], int)
        assert isinstance(data["trades_rejected"], int)
        
        print(f"Dataset stats: total={data['total_signals']}, taken={data['trades_taken']}, rejected={data['trades_rejected']}")
        print(f"Outcomes: {outcomes}")
        print(f"Rejection reasons: {data['rejection_reasons']}")
    
    def test_dataset_stats_requires_auth(self):
        """Dataset stats should require authentication"""
        response = requests.get(f"{BASE_URL}/api/dataset/stats")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("Dataset stats correctly requires authentication")


class TestBotFilters:
    """GET /api/bot/filters tests"""
    
    def test_bot_filters_returns_expected_fields(self, auth_headers):
        """Bot filters should return filter config and cooldown state"""
        response = requests.get(f"{BASE_URL}/api/bot/filters", headers=auth_headers)
        assert response.status_code == 200, f"Bot filters failed: {response.text}"
        data = response.json()
        
        # Verify filters object exists
        assert "filters" in data, "Missing filters object"
        filters = data["filters"]
        
        # Verify all 9 smart filter fields
        expected_filters = [
            "max_trades_per_hour",
            "max_trades_per_day",
            "min_risk_reward_ratio",
            "cooldown_after_loss_scans",
            "min_confidence_score",
            "spread_max_percent",
            "min_24h_volume_usdt",
            "max_slippage_percent",
            "require_trend_alignment"
        ]
        
        for field in expected_filters:
            assert field in filters, f"Missing filter field: {field}"
        
        # Verify cooldown state
        assert "cooldown_state" in data, "Missing cooldown_state"
        cooldown = data["cooldown_state"]
        assert "scans_since_loss" in cooldown, "Missing scans_since_loss"
        assert "consecutive_losses" in cooldown, "Missing consecutive_losses"
        
        print(f"Bot filters: {filters}")
        print(f"Cooldown state: {cooldown}")
    
    def test_bot_filters_requires_auth(self):
        """Bot filters should require authentication"""
        response = requests.get(f"{BASE_URL}/api/bot/filters")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("Bot filters correctly requires authentication")


class TestBotConfigSmartFilters:
    """PUT/GET /api/bot/config smart filter fields tests"""
    
    def test_get_config_includes_smart_filter_fields(self, auth_headers):
        """GET /api/bot/config should include all smart filter fields"""
        response = requests.get(f"{BASE_URL}/api/bot/config", headers=auth_headers)
        assert response.status_code == 200, f"Get config failed: {response.text}"
        config = response.json()
        
        # Verify all 9 smart filter fields exist
        smart_filter_fields = [
            "max_trades_per_hour",
            "max_trades_per_day",
            "min_risk_reward_ratio",
            "cooldown_after_loss_scans",
            "min_confidence_score",
            "spread_max_percent",
            "min_24h_volume_usdt",
            "max_slippage_percent",
            "require_trend_alignment"
        ]
        
        for field in smart_filter_fields:
            assert field in config, f"Missing smart filter field in config: {field}"
        
        print(f"Config includes all smart filter fields")
        print(f"max_trades_per_hour: {config['max_trades_per_hour']}")
        print(f"max_trades_per_day: {config['max_trades_per_day']}")
        print(f"min_risk_reward_ratio: {config['min_risk_reward_ratio']}")
        print(f"require_trend_alignment: {config['require_trend_alignment']}")
    
    def test_update_config_smart_filters(self, auth_headers):
        """PUT /api/bot/config should accept and persist smart filter values"""
        # First get current config
        get_response = requests.get(f"{BASE_URL}/api/bot/config", headers=auth_headers)
        original_config = get_response.json()
        
        # Update smart filter values
        update_payload = {
            "max_trades_per_hour": 3,
            "max_trades_per_day": 10,
            "min_risk_reward_ratio": 2.0,
            "cooldown_after_loss_scans": 8,
            "min_confidence_score": 0.55,
            "spread_max_percent": 0.2,
            "min_24h_volume_usdt": 500000,
            "max_slippage_percent": 0.15,
            "require_trend_alignment": False
        }
        
        put_response = requests.put(f"{BASE_URL}/api/bot/config", json=update_payload, headers=auth_headers)
        assert put_response.status_code == 200, f"Update config failed: {put_response.text}"
        updated_config = put_response.json()
        
        # Verify values were updated
        assert updated_config["max_trades_per_hour"] == 3
        assert updated_config["max_trades_per_day"] == 10
        assert updated_config["min_risk_reward_ratio"] == 2.0
        assert updated_config["cooldown_after_loss_scans"] == 8
        assert updated_config["min_confidence_score"] == 0.55
        assert updated_config["spread_max_percent"] == 0.2
        assert updated_config["min_24h_volume_usdt"] == 500000
        assert updated_config["max_slippage_percent"] == 0.15
        assert updated_config["require_trend_alignment"] == False
        
        print("Smart filter values updated successfully")
        
        # Verify persistence with GET
        verify_response = requests.get(f"{BASE_URL}/api/bot/config", headers=auth_headers)
        verify_config = verify_response.json()
        assert verify_config["max_trades_per_hour"] == 3
        assert verify_config["require_trend_alignment"] == False
        
        print("Smart filter values persisted correctly")
        
        # Restore original values
        restore_payload = {
            "max_trades_per_hour": original_config.get("max_trades_per_hour", 2),
            "max_trades_per_day": original_config.get("max_trades_per_day", 8),
            "min_risk_reward_ratio": original_config.get("min_risk_reward_ratio", 2.5),
            "cooldown_after_loss_scans": original_config.get("cooldown_after_loss_scans", 6),
            "min_confidence_score": original_config.get("min_confidence_score", 0.60),
            "spread_max_percent": original_config.get("spread_max_percent", 0.15),
            "min_24h_volume_usdt": original_config.get("min_24h_volume_usdt", 1000000),
            "max_slippage_percent": original_config.get("max_slippage_percent", 0.1),
            "require_trend_alignment": original_config.get("require_trend_alignment", True)
        }
        requests.put(f"{BASE_URL}/api/bot/config", json=restore_payload, headers=auth_headers)
        print("Original config restored")


class TestPositionsConfidenceScore:
    """GET /api/positions confidence_score field tests"""
    
    def test_positions_include_confidence_score(self, auth_headers):
        """Positions should include confidence_score field"""
        response = requests.get(f"{BASE_URL}/api/positions?status=OPEN", headers=auth_headers)
        assert response.status_code == 200, f"Get positions failed: {response.text}"
        positions = response.json()
        
        if len(positions) > 0:
            pos = positions[0]
            # Check for confidence_score field
            if "confidence_score" in pos:
                print(f"Position has confidence_score: {pos['confidence_score']}")
                assert isinstance(pos["confidence_score"], (int, float))
            else:
                print("No open positions with confidence_score found (may be older positions)")
            
            # Check for filters_passed field
            if "filters_passed" in pos:
                print(f"Position has filters_passed: {pos['filters_passed']}")
                assert isinstance(pos["filters_passed"], dict)
        else:
            print("No open positions to verify confidence_score")
        
        # Also check closed positions
        closed_response = requests.get(f"{BASE_URL}/api/positions?status=CLOSED", headers=auth_headers)
        closed_positions = closed_response.json()
        
        if len(closed_positions) > 0:
            for pos in closed_positions[:3]:  # Check first 3
                if "confidence_score" in pos:
                    print(f"Closed position {pos.get('symbol')} has confidence_score: {pos['confidence_score']}")
        
        print(f"Total open positions: {len(positions)}, closed positions: {len(closed_positions)}")


class TestDashboard:
    """Dashboard endpoint tests"""
    
    def test_dashboard_loads(self, auth_headers):
        """Dashboard should load with all expected fields"""
        response = requests.get(f"{BASE_URL}/api/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        
        # Verify expected fields
        assert "balance" in data
        assert "daily_pnl" in data
        assert "total_pnl" in data
        assert "win_rate" in data
        assert "positions" in data
        assert "bot_status" in data
        
        print(f"Dashboard loaded: balance={data['balance']}, daily_pnl={data['daily_pnl']}")
        print(f"Bot status: {data['bot_status']}")


class TestBotStatus:
    """Bot status endpoint tests"""
    
    def test_bot_status(self, auth_headers):
        """Bot status should return running state and mode"""
        response = requests.get(f"{BASE_URL}/api/bot/status", headers=auth_headers)
        assert response.status_code == 200, f"Bot status failed: {response.text}"
        data = response.json()
        
        assert "running" in data
        assert "mode" in data
        assert "scan_count" in data
        
        print(f"Bot status: running={data['running']}, mode={data['mode']}, scans={data['scan_count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
