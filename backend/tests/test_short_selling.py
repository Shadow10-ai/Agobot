"""
Test suite for Short Selling feature in AgoBot
Tests allow_short config toggle, SHORT position logic, and side field in trades
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://smart-filter-bot-2.preview.emergentagent.com').rstrip('/')

class TestShortSellingConfig:
    """Tests for allow_short configuration field"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_config_returns_allow_short_field(self):
        """GET /api/bot/config should return allow_short field"""
        response = requests.get(f"{BASE_URL}/api/bot/config", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "allow_short" in data, "allow_short field missing from config"
        assert isinstance(data["allow_short"], bool), "allow_short should be boolean"
        print(f"Config allow_short value: {data['allow_short']}")
    
    def test_put_config_enable_short_selling(self):
        """PUT /api/bot/config with allow_short: true enables short selling"""
        # Enable short selling
        response = requests.put(
            f"{BASE_URL}/api/bot/config",
            json={"allow_short": True},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allow_short"] == True, "allow_short should be True after update"
        
        # Verify with GET
        get_response = requests.get(f"{BASE_URL}/api/bot/config", headers=self.headers)
        assert get_response.status_code == 200
        assert get_response.json()["allow_short"] == True, "allow_short not persisted"
        print("Short selling enabled successfully")
    
    def test_put_config_disable_short_selling(self):
        """PUT /api/bot/config with allow_short: false disables short selling"""
        # Disable short selling
        response = requests.put(
            f"{BASE_URL}/api/bot/config",
            json={"allow_short": False},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allow_short"] == False, "allow_short should be False after update"
        
        # Verify with GET
        get_response = requests.get(f"{BASE_URL}/api/bot/config", headers=self.headers)
        assert get_response.status_code == 200
        assert get_response.json()["allow_short"] == False, "allow_short not persisted"
        print("Short selling disabled successfully")
        
        # Re-enable for other tests
        requests.put(
            f"{BASE_URL}/api/bot/config",
            json={"allow_short": True},
            headers=self.headers
        )


class TestShortPositions:
    """Tests for SHORT position behavior"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_positions_have_side_field(self):
        """GET /api/positions should return positions with side field (LONG or SHORT)"""
        response = requests.get(f"{BASE_URL}/api/positions", headers=self.headers)
        assert response.status_code == 200
        positions = response.json()
        
        if not positions:
            pytest.skip("No open positions to test")
        
        for pos in positions:
            assert "side" in pos, f"Position {pos.get('id', 'unknown')} missing side field"
            assert pos["side"] in ["LONG", "SHORT"], f"Invalid side: {pos['side']}"
            print(f"Position {pos['symbol']}: side={pos['side']}")
    
    def test_short_position_sl_above_entry(self):
        """SHORT positions should have stop_loss ABOVE entry_price"""
        response = requests.get(f"{BASE_URL}/api/positions", headers=self.headers)
        assert response.status_code == 200
        positions = response.json()
        
        short_positions = [p for p in positions if p.get("side") == "SHORT"]
        if not short_positions:
            pytest.skip("No SHORT positions to test")
        
        for pos in short_positions:
            assert pos["stop_loss"] > pos["entry_price"], \
                f"SHORT {pos['symbol']}: SL ({pos['stop_loss']}) should be > entry ({pos['entry_price']})"
            print(f"SHORT {pos['symbol']}: SL={pos['stop_loss']} > entry={pos['entry_price']} ✓")
    
    def test_short_position_tp_below_entry(self):
        """SHORT positions should have take_profit BELOW entry_price"""
        response = requests.get(f"{BASE_URL}/api/positions", headers=self.headers)
        assert response.status_code == 200
        positions = response.json()
        
        short_positions = [p for p in positions if p.get("side") == "SHORT"]
        if not short_positions:
            pytest.skip("No SHORT positions to test")
        
        for pos in short_positions:
            assert pos["take_profit"] < pos["entry_price"], \
                f"SHORT {pos['symbol']}: TP ({pos['take_profit']}) should be < entry ({pos['entry_price']})"
            print(f"SHORT {pos['symbol']}: TP={pos['take_profit']} < entry={pos['entry_price']} ✓")
    
    def test_short_position_pnl_positive_when_price_drops(self):
        """SHORT positions: unrealized PnL positive when current_price < entry_price"""
        response = requests.get(f"{BASE_URL}/api/positions", headers=self.headers)
        assert response.status_code == 200
        positions = response.json()
        
        short_positions = [p for p in positions if p.get("side") == "SHORT"]
        if not short_positions:
            pytest.skip("No SHORT positions to test")
        
        for pos in short_positions:
            price_diff = pos["entry_price"] - pos["current_price"]
            expected_sign = "positive" if price_diff > 0 else "negative"
            actual_sign = "positive" if pos["unrealized_pnl"] > 0 else "negative"
            
            # PnL should be positive when price < entry (price_diff > 0) for SHORT
            if price_diff > 0:
                assert pos["unrealized_pnl"] > 0 or abs(pos["unrealized_pnl"]) < 0.01, \
                    f"SHORT {pos['symbol']}: PnL should be positive when price drops"
            elif price_diff < 0:
                assert pos["unrealized_pnl"] < 0 or abs(pos["unrealized_pnl"]) < 0.01, \
                    f"SHORT {pos['symbol']}: PnL should be negative when price rises"
            
            print(f"SHORT {pos['symbol']}: price_diff={price_diff:.4f}, PnL={pos['unrealized_pnl']:.4f} ({actual_sign})")


class TestTradesSideField:
    """Tests for side field in trades history"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_trades_have_side_field(self):
        """GET /api/trades should return trades with side field"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=10", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        trades = data.get("trades", [])
        
        if not trades:
            pytest.skip("No trades to test")
        
        for trade in trades:
            assert "side" in trade, f"Trade {trade.get('id', 'unknown')} missing side field"
            assert trade["side"] in ["LONG", "SHORT"], f"Invalid side: {trade['side']}"
            print(f"Trade {trade['symbol']}: side={trade['side']}, pnl={trade.get('pnl', 0):.4f}")


class TestDashboardWithShortPositions:
    """Tests for dashboard showing SHORT positions correctly"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_dashboard_positions_have_side(self):
        """GET /api/dashboard positions should include side field"""
        response = requests.get(f"{BASE_URL}/api/dashboard", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        positions = data.get("positions", [])
        if not positions:
            pytest.skip("No positions in dashboard")
        
        for pos in positions:
            assert "side" in pos, f"Dashboard position missing side field"
            print(f"Dashboard position: {pos['symbol']} - {pos['side']}")


class TestExistingFeaturesStillWork:
    """Regression tests - ensure existing features still work"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_health_endpoint_no_auth(self):
        """GET /api/health works without auth"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print(f"Health: {data}")
    
    def test_dashboard_endpoint(self):
        """GET /api/dashboard works"""
        response = requests.get(f"{BASE_URL}/api/dashboard", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "balance" in data
        assert "bot_status" in data
        print(f"Dashboard: balance={data['balance']}, bot_running={data['bot_status'].get('running')}")
    
    def test_leaderboard_endpoint(self):
        """GET /api/leaderboard works"""
        response = requests.get(f"{BASE_URL}/api/leaderboard", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "symbol_rankings" in data
        print(f"Leaderboard: {len(data.get('symbol_rankings', []))} symbols ranked")
    
    def test_bot_status_endpoint(self):
        """GET /api/bot/status works"""
        response = requests.get(f"{BASE_URL}/api/bot/status", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "mode" in data
        print(f"Bot status: running={data['running']}, mode={data['mode']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
