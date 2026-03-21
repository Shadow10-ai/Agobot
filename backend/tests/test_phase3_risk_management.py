"""
Phase 3: Professional-Grade Risk Management Features Tests
- Drawdown Circuit Breaker (auto-pauses bot)
- Session-Aware Trading (Asia/London/NYC)
- Advanced Market Regime Detection (TRENDING_UP/DOWN/RANGING/VOLATILE/CALM)
- Monte Carlo Risk Simulation (1000 sims)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "user@example.com",
        "password": "password"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")

@pytest.fixture
def api_client(auth_token):
    """Authenticated requests session."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


# ====================================================================
# HEALTH CHECK (no auth required)
# ====================================================================

class TestHealthEndpoint:
    """Health endpoint tests - no auth required."""
    
    def test_health_endpoint_no_auth(self):
        """GET /api/health should work without authentication."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "ok"]


# ====================================================================
# AUTHENTICATION (Phase 1 regression)
# ====================================================================

class TestAuthEndpoints:
    """Auth endpoint regression tests."""
    
    def test_login_success(self):
        """POST /api/auth/login with valid credentials."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == "user@example.com"
    
    def test_login_invalid_credentials(self):
        """POST /api/auth/login with invalid credentials."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401


# ====================================================================
# PHASE 1 REGRESSION: Dataset Stats
# ====================================================================

class TestDatasetStats:
    """Dataset stats endpoint regression test (Phase 1)."""
    
    def test_dataset_stats(self, api_client):
        """GET /api/dataset/stats returns signal dataset statistics."""
        response = api_client.get(f"{BASE_URL}/api/dataset/stats")
        assert response.status_code == 200
        data = response.json()
        # Check required fields
        assert "total_signals" in data
        assert "trades_taken" in data
        assert "trades_rejected" in data
        assert "outcomes" in data
        assert "win_rate" in data


# ====================================================================
# PHASE 2 REGRESSION: ML Status
# ====================================================================

class TestMLStatus:
    """ML status endpoint regression test (Phase 2)."""
    
    def test_ml_status(self, api_client):
        """GET /api/ml/status returns ML model status."""
        response = api_client.get(f"{BASE_URL}/api/ml/status")
        assert response.status_code == 200
        data = response.json()
        # Check required fields
        assert "status" in data
        assert data["status"] in ["LEARNING", "ACTIVE", "TRAINING", "ERROR"]
        assert "version" in data
        # training_samples may be in training_data or at root
        assert "training_data" in data or "training_samples" in data


# ====================================================================
# PHASE 3: CIRCUIT BREAKER
# ====================================================================

class TestCircuitBreaker:
    """Drawdown Circuit Breaker endpoint tests."""
    
    def test_get_circuit_breaker_status(self, api_client):
        """GET /api/risk/circuit-breaker returns breaker status."""
        response = api_client.get(f"{BASE_URL}/api/risk/circuit-breaker")
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "tripped" in data
        assert isinstance(data["tripped"], bool)
        
        assert "current_drawdown" in data
        assert isinstance(data["current_drawdown"], (int, float))
        
        assert "peak_balance" in data
        assert isinstance(data["peak_balance"], (int, float))
        
        assert "max_drawdown_threshold" in data
        assert isinstance(data["max_drawdown_threshold"], (int, float))
        
        # Optional fields when tripped
        assert "tripped_at" in data
        assert "drawdown_at_trip" in data
        assert "current_balance" in data
    
    def test_reset_circuit_breaker(self, api_client):
        """POST /api/risk/circuit-breaker/reset resets the breaker."""
        response = api_client.post(f"{BASE_URL}/api/risk/circuit-breaker/reset")
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert data["status"] == "reset"
        assert "bot_paused" in data
        assert data["bot_paused"] == False
        
        # Verify breaker is now not tripped
        verify_response = api_client.get(f"{BASE_URL}/api/risk/circuit-breaker")
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["tripped"] == False


# ====================================================================
# PHASE 3: MARKET REGIME DETECTION
# ====================================================================

class TestMarketRegime:
    """Advanced Market Regime Detection endpoint tests."""
    
    def test_get_market_regime(self, api_client):
        """GET /api/risk/regime returns regime per symbol."""
        response = api_client.get(f"{BASE_URL}/api/risk/regime")
        assert response.status_code == 200
        data = response.json()
        
        # Check structure
        assert "regimes" in data
        assert isinstance(data["regimes"], dict)
        
        # Check at least one symbol has regime data
        regimes = data["regimes"]
        assert len(regimes) > 0
        
        # Check regime data structure for each symbol
        valid_regimes = ["TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE", "CALM", "UNKNOWN"]
        for symbol, regime_data in regimes.items():
            assert "regime" in regime_data
            assert regime_data["regime"] in valid_regimes
            
            assert "strength" in regime_data
            assert isinstance(regime_data["strength"], (int, float))
            assert 0 <= regime_data["strength"] <= 1
            
            assert "details" in regime_data
            assert isinstance(regime_data["details"], dict)
            
            # Check details contain expected metrics
            details = regime_data["details"]
            if details:  # May be empty for UNKNOWN
                expected_detail_keys = ["trend_slope", "trend_strength", "atr_percent", "adx_proxy", "volume_expansion", "bb_bandwidth"]
                for key in expected_detail_keys:
                    assert key in details, f"Missing {key} in regime details for {symbol}"
    
    def test_regime_includes_session_info(self, api_client):
        """GET /api/risk/regime also returns session info."""
        response = api_client.get(f"{BASE_URL}/api/risk/regime")
        assert response.status_code == 200
        data = response.json()
        
        assert "session" in data
        session = data["session"]
        assert isinstance(session, (list, tuple))
        assert len(session) == 2  # (in_session, session_name)


# ====================================================================
# PHASE 3: TRADING SESSIONS
# ====================================================================

class TestTradingSessions:
    """Session-Aware Trading endpoint tests."""
    
    def test_get_trading_sessions(self, api_client):
        """GET /api/risk/sessions returns session info."""
        response = api_client.get(f"{BASE_URL}/api/risk/sessions")
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "current_utc" in data
        assert "current_hour" in data
        assert isinstance(data["current_hour"], int)
        assert 0 <= data["current_hour"] <= 23
        
        assert "in_session" in data
        assert isinstance(data["in_session"], bool)
        
        assert "active_session" in data
        
        assert "sessions" in data
        sessions = data["sessions"]
        assert isinstance(sessions, dict)
        
        # Check expected sessions exist
        expected_sessions = ["ASIA", "LONDON", "NYC", "OVERLAP"]
        for session_name in expected_sessions:
            assert session_name in sessions, f"Missing session: {session_name}"
            session = sessions[session_name]
            assert "start" in session
            assert "end" in session
        
        assert "allowed" in data
        assert isinstance(data["allowed"], list)


# ====================================================================
# PHASE 3: MONTE CARLO SIMULATION
# ====================================================================

class TestMonteCarlo:
    """Monte Carlo Risk Simulation endpoint tests."""
    
    def test_run_monte_carlo_simulation(self, api_client):
        """POST /api/risk/monte-carlo runs simulation and returns results."""
        response = api_client.post(f"{BASE_URL}/api/risk/monte-carlo", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        # Check if we have enough trades or got an error
        if "error" in data:
            # Expected if not enough historical trades
            assert "trade_count" in data or "Need at least" in data["error"]
            pytest.skip(f"Monte Carlo skipped: {data['error']}")
        
        # Simulation parameters
        assert "simulations" in data
        assert data["simulations"] == 1000
        
        assert "trades_per_sim" in data
        assert data["trades_per_sim"] == 100
        
        assert "initial_balance" in data
        assert "historical_trades_used" in data
        
        # Historical trade stats
        assert "avg_pnl_per_trade" in data
        assert "win_rate" in data
        
        # Results section
        assert "results" in data
        results = data["results"]
        assert "mean_final_balance" in results
        assert "median_final_balance" in results
        assert "std_final_balance" in results
        assert "best_case" in results
        assert "worst_case" in results
        assert "percentile_5" in results
        assert "percentile_25" in results
        assert "percentile_75" in results
        assert "percentile_95" in results
        
        # Risk section
        assert "risk" in data
        risk = data["risk"]
        assert "probability_of_ruin" in risk
        assert "avg_max_drawdown" in risk
        assert "median_max_drawdown" in risk
        assert "worst_drawdown" in risk
        assert "probability_profitable" in risk
        
        # Distribution section
        assert "distribution" in data
        distribution = data["distribution"]
        assert "below_8000" in distribution
        assert "8000_to_10000" in distribution
        assert "10000_to_12000" in distribution
        assert "above_12000" in distribution
        
        # Validate percentages sum to ~100%
        total_pct = sum(distribution.values())
        assert 99 <= total_pct <= 101, f"Distribution percentages should sum to ~100%, got {total_pct}"


# ====================================================================
# REGRESSION: OTHER ENDPOINTS STILL WORK
# ====================================================================

class TestRegressionEndpoints:
    """Ensure Phase 1 & 2 endpoints still work."""
    
    def test_bot_status(self, api_client):
        """GET /api/bot/status still works."""
        response = api_client.get(f"{BASE_URL}/api/bot/status")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "mode" in data
    
    def test_bot_config(self, api_client):
        """GET /api/bot/config still works."""
        response = api_client.get(f"{BASE_URL}/api/bot/config")
        assert response.status_code == 200
        data = response.json()
        assert "symbols" in data
    
    def test_trades_list(self, api_client):
        """GET /api/trades still works."""
        response = api_client.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        data = response.json()
        # May return list or {total, trades} object
        if isinstance(data, dict):
            assert "trades" in data
            assert isinstance(data["trades"], list)
        else:
            assert isinstance(data, list)
    
    def test_positions_list(self, api_client):
        """GET /api/positions still works."""
        response = api_client.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
