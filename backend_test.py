import requests
import sys
import json
import time
from datetime import datetime

class AgoBacktesterTester:
    def __init__(self, base_url="https://trading-bot-spot.preview.emergentagent.com"):
        self.base_url = base_url + "/api"
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test with detailed tracking"""
        url = f"{self.base_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=30)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                self.test_results.append({"test": name, "status": "PASS", "response_code": response.status_code})
                return success, response.json() if response.content else {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")
                self.test_results.append({"test": name, "status": "FAIL", "expected": expected_status, "actual": response.status_code, "error": response.text[:200]})
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.test_results.append({"test": name, "status": "ERROR", "error": str(e)})
            return False, {}

    def test_auth_flow(self):
        """Test authentication with existing user"""
        print("\n🔑 Testing Authentication...")
        success, response = self.run_test(
            "Login with test user",
            "POST",
            "auth/login",
            200,
            data={"email": "test@trader.com", "password": "test123"}
        )
        if success and 'access_token' in response:
            self.token = response['access_token']
            print(f"   Token obtained for user: {response.get('user', {}).get('email')}")
            return True
        else:
            # Try to register test user if login fails
            print("   Login failed, attempting to register test user...")
            success, response = self.run_test(
                "Register test user",
                "POST",
                "auth/register",
                200,
                data={"email": "test@trader.com", "password": "test123", "name": "Test Trader"}
            )
            if success and 'access_token' in response:
                self.token = response['access_token']
                print(f"   Test user registered and token obtained")
                return True
        return False

    def test_backtest_api(self):
        """Test the new backtest functionality with robustness improvements"""
        print("\n🧪 Testing Backtest API with Robustness Features...")
        
        # Test backtest with NEW robustness parameters
        backtest_params = {
            "symbol": "BTCUSDT",
            "period_days": 30,
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
            "initial_balance": 10000.0,
            # NEW: Robustness parameters
            "slippage_pct": 0.05,
            "fee_pct": 0.1,
            "volume_filter_multiplier": 1.5,
            "volatility_regime_enabled": True,
            "volatility_reduce_factor": 0.5
        }
        
        success, response = self.run_test(
            "Run 30-day BTC backtest",
            "POST",
            "backtest",
            200,
            data=backtest_params
        )
        
        if success:
            # Verify response structure
            required_fields = ['summary', 'trades', 'equity_curve', 'monthly_pnl', 'exit_breakdown']
            missing_fields = [f for f in required_fields if f not in response]
            if missing_fields:
                print(f"   ❌ Missing required fields: {missing_fields}")
                return False
                
            summary = response.get('summary', {})
            required_summary_fields = [
                'total_trades', 'win_rate', 'total_pnl', 'max_drawdown', 'profit_factor', 'sharpe_ratio',
                # NEW: Robustness metrics
                'total_fees', 'total_slippage', 'signals_rejected_volume', 'signals_rejected_regime'
            ]
            missing_summary = [f for f in required_summary_fields if f not in summary]
            if missing_summary:
                print(f"   ❌ Missing summary fields: {missing_summary}")
                return False
                
            print(f"   ✅ Backtest completed:")
            print(f"      Total Trades: {summary.get('total_trades')}")
    def test_strategy_comparison_api(self):
        """Test the NEW strategy comparison functionality"""
        print("\n🆚 Testing Strategy Comparison API...")
        
        # Define two different strategies for comparison
        conservative_strategy = {
            "symbol": "BTCUSDT",
            "period_days": 30,
            "base_usdt_per_trade": 30.0,
            "risk_per_trade_percent": 0.3,
            "min_entry_probability": 0.6,
            "rsi_overbought": 65.0,
            "rsi_oversold": 35.0,
            "atr_sl_multiplier": 1.5,
            "atr_tp_multiplier": 3.0,
            "trailing_stop_activate_pips": 3.0,
            "trailing_stop_distance_pips": 1.5,
            "initial_balance": 10000.0,
            "slippage_pct": 0.05,
            "fee_pct": 0.1,
            "volume_filter_multiplier": 2.0,
            "volatility_regime_enabled": True,
            "volatility_reduce_factor": 0.3,
            "label": "Conservative"
        }
        
        aggressive_strategy = {
            "symbol": "BTCUSDT", 
            "period_days": 30,
            "base_usdt_per_trade": 80.0,
            "risk_per_trade_percent": 1.0,
            "min_entry_probability": 0.35,
            "rsi_overbought": 75.0,
            "rsi_oversold": 25.0,
            "atr_sl_multiplier": 1.0,
            "atr_tp_multiplier": 2.0,
            "trailing_stop_activate_pips": 1.8,
            "trailing_stop_distance_pips": 0.8,
            "initial_balance": 10000.0,
            "slippage_pct": 0.05,
            "fee_pct": 0.1,
            "volume_filter_multiplier": 1.0,
            "volatility_regime_enabled": False,
            "volatility_reduce_factor": 1.0,
            "label": "Aggressive"
        }
        
        compare_params = {
            "symbol": "BTCUSDT",
            "period_days": 30,
            "strategy_a": conservative_strategy,
            "strategy_b": aggressive_strategy
        }
        
        success, response = self.run_test(
            "Strategy Comparison: Conservative vs Aggressive",
            "POST",
            "backtest/compare",
            200,
            data=compare_params
        )
        
        if success:
            # Verify comparison response structure
            required_fields = ['overall_winner', 'a_wins', 'b_wins', 'strategy_a', 'strategy_b', 'comparison', 'candle_count']
            missing_fields = [f for f in required_fields if f not in response]
            if missing_fields:
                print(f"   ❌ Missing required comparison fields: {missing_fields}")
                return False
            
            # Check strategy results
            strategy_a = response.get('strategy_a', {})
            strategy_b = response.get('strategy_b', {})
            
            for strategy_key, strategy_data in [('A', strategy_a), ('B', strategy_b)]:
                if 'summary' not in strategy_data:
                    print(f"   ❌ Missing summary in strategy {strategy_key}")
                    return False
                    
                summary = strategy_data['summary']
                required_summary_fields = [
                    'total_trades', 'win_rate', 'total_pnl', 'total_fees', 'total_slippage',
                    'signals_rejected_volume', 'signals_rejected_regime'
                ]
                missing_summary = [f for f in required_summary_fields if f not in summary]
                if missing_summary:
                    print(f"   ❌ Missing summary fields in strategy {strategy_key}: {missing_summary}")
                    return False
            
            print(f"   ✅ Strategy Comparison completed:")
            print(f"      Winner: {response.get('overall_winner')}")
            print(f"      Metric wins: A={response.get('a_wins')}, B={response.get('b_wins')}")
            print(f"      Candles analyzed: {response.get('candle_count')}")
            
            # Display strategy results
            sa_summary = strategy_a.get('summary', {})
            sb_summary = strategy_b.get('summary', {})
            print(f"      Strategy A (Conservative): {sa_summary.get('total_trades', 0)} trades, ${sa_summary.get('total_pnl', 0):.2f} PnL")
            print(f"      Strategy B (Aggressive): {sb_summary.get('total_trades', 0)} trades, ${sb_summary.get('total_pnl', 0):.2f} PnL")
            
            # Check comparison metrics
            comparison = response.get('comparison', {})
            print(f"      Comparison metrics available: {list(comparison.keys())}")
            
            return True
        return False
    
    def test_robustness_parameters(self):
        """Test specific robustness parameter variations"""
        print("\n🛡️ Testing Robustness Parameter Variations...")
        
        # Test with volume filter disabled
        no_vol_filter = {
            "symbol": "ETHUSDT",
            "period_days": 15,
            "initial_balance": 5000.0,
            "volume_filter_multiplier": 0.1,  # Very low = accept all volumes
            "volatility_regime_enabled": False,
            "slippage_pct": 0.0,
            "fee_pct": 0.0,
            "min_entry_probability": 0.3
        }
        
        success, response = self.run_test(
            "Backtest with minimal robustness filters",
            "POST", 
            "backtest",
            200,
            data=no_vol_filter
        )
        
        if success:
            summary = response.get('summary', {})
            print(f"   ✅ No filters: {summary.get('total_trades', 0)} trades, ${summary.get('total_pnl', 0):.2f} PnL")
            print(f"      Volume rejects: {summary.get('signals_rejected_volume', 0)}")
            print(f"      Regime rejects: {summary.get('signals_rejected_regime', 0)}")
        
        # Test with maximum robustness
        max_robust = {
            "symbol": "ETHUSDT",
            "period_days": 15,
            "initial_balance": 5000.0,
            "volume_filter_multiplier": 3.0,  # High filter
            "volatility_regime_enabled": True,
            "volatility_reduce_factor": 0.2,   # Aggressive reduction
            "slippage_pct": 0.15,  # High slippage
            "fee_pct": 0.25,       # High fees
            "min_entry_probability": 0.7  # Very selective
        }
        
        success, response = self.run_test(
            "Backtest with maximum robustness filters",
            "POST",
            "backtest", 
            200,
            data=max_robust
        )
        
        if success:
            summary = response.get('summary', {})
            print(f"   ✅ Max filters: {summary.get('total_trades', 0)} trades, ${summary.get('total_pnl', 0):.2f} PnL")
            print(f"      Total fees: ${summary.get('total_fees', 0):.2f}")
            print(f"      Total slippage: ${summary.get('total_slippage', 0):.2f}")
            print(f"      Volume rejects: {summary.get('signals_rejected_volume', 0)}")
            print(f"      Regime rejects: {summary.get('signals_rejected_regime', 0)}")
            
            return True
        return False
            print(f"      Win Rate: {summary.get('win_rate')}%")
            print(f"      Total PnL: ${summary.get('total_pnl')}")
            print(f"      Max Drawdown: {summary.get('max_drawdown_pct')}%")
            print(f"      Profit Factor: {summary.get('profit_factor')}")
            print(f"      Sharpe Ratio: {summary.get('sharpe_ratio')}")
            # NEW: Robustness metrics
            print(f"      Total Fees: ${summary.get('total_fees', 0):.4f}")
            print(f"      Total Slippage: ${summary.get('total_slippage', 0):.4f}")
            print(f"      Volume Filter Rejects: {summary.get('signals_rejected_volume', 0)}")
            print(f"      Regime Adjustments: {summary.get('signals_rejected_regime', 0)}")
            print(f"      Equity Curve Points: {len(response.get('equity_curve', []))}")
            print(f"      Trade Details: {len(response.get('trades', []))}")
            
            return True
        return False

    def test_backtest_history(self):
        """Test backtest history retrieval"""
        print("\n📈 Testing Backtest History...")
        
        success, response = self.run_test(
            "Get backtest history",
            "GET",
            "backtests",
            200
        )
        
        if success:
            backtests = response if isinstance(response, list) else []
            print(f"   ✅ Retrieved {len(backtests)} previous backtests")
            
            if backtests:
                latest = backtests[0]
                required_fields = ['id', 'symbol', 'params', 'summary', 'created_at']
                missing = [f for f in required_fields if f not in latest]
                if missing:
                    print(f"   ❌ Missing fields in backtest history: {missing}")
                    return False
                print(f"   Latest: {latest.get('symbol')} - ${latest.get('summary', {}).get('total_pnl', 0):.2f} PnL")
            
            return True
        return False

    def test_backtest_validation(self):
        """Test backtest parameter validation"""
        print("\n🔍 Testing Backtest Validation...")
        
        # Test invalid symbol
        invalid_params = {
            "symbol": "INVALIDCOIN",
            "period_days": 30,
            "initial_balance": 10000.0
        }
        
        success, response = self.run_test(
            "Backtest with invalid symbol",
            "POST",
            "backtest",
            400,
            data=invalid_params
        )
        
        if success:
            print("   ✅ Invalid symbol correctly rejected")
        
        # Test invalid period
        invalid_period = {
            "symbol": "BTCUSDT",
            "period_days": 500,  # Too long
            "initial_balance": 10000.0
        }
        
        success, response = self.run_test(
            "Backtest with invalid period",
            "POST",
            "backtest",
            400,
            data=invalid_period
        )
        
        if success:
            print("   ✅ Invalid period correctly rejected")
            
        return True

    def test_different_symbols(self):
        """Test backtesting with different symbols"""
        print("\n🔄 Testing Multiple Symbols...")
        
        symbols_to_test = ["ETHUSDT", "SOLUSDT"]
        for symbol in symbols_to_test:
            params = {
                "symbol": symbol,
                "period_days": 15,  # Shorter for faster testing
                "initial_balance": 5000.0,
                "min_entry_probability": 0.4
            }
            
            success, response = self.run_test(
                f"Backtest {symbol}",
                "POST",
                "backtest",
                200,
                data=params
            )
            
            if success:
                summary = response.get('summary', {})
                print(f"   ✅ {symbol}: {summary.get('total_trades', 0)} trades, ${summary.get('total_pnl', 0):.2f} PnL")
            else:
                return False
                
        return True

    def test_existing_endpoints(self):
        """Test that existing endpoints still work"""
        print("\n🔧 Testing Existing Endpoints...")
        
        endpoints = [
            ("Dashboard", "GET", "dashboard", 200),
            ("Bot Status", "GET", "bot/status", 200),
            ("Trades", "GET", "trades", 200),
            ("Performance", "GET", "performance", 200),
            ("Leaderboard", "GET", "leaderboard", 200)
        ]
        
        all_passed = True
        for name, method, endpoint, expected in endpoints:
            success, _ = self.run_test(name, method, endpoint, expected)
            if not success:
                all_passed = False
                
        return all_passed

    def print_summary(self):
        """Print test summary"""
        print(f"\n📊 Test Summary:")
        print(f"   Tests run: {self.tests_run}")
        print(f"   Tests passed: {self.tests_passed}")
        print(f"   Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.tests_passed != self.tests_run:
            print(f"\n❌ Failed tests:")
            for result in self.test_results:
                if result['status'] != 'PASS':
                    print(f"   - {result['test']}: {result['status']}")

def main():
    tester = AgoBacktesterTester()
    
    # Test authentication first
    if not tester.test_auth_flow():
        print("❌ Authentication failed, cannot proceed with protected endpoints")
        return 1
    
    print("\n" + "="*60)
    print("AGOBOT STRATEGY BACKTESTER - COMPREHENSIVE TESTING")
    print("="*60)
    
    # Run all tests
    tests = [
        ("Backtest API", tester.test_backtest_api),
        ("Strategy Comparison API", tester.test_strategy_comparison_api),
        ("Robustness Parameters", tester.test_robustness_parameters), 
        ("Backtest History", tester.test_backtest_history),
        ("Backtest Validation", tester.test_backtest_validation),
        ("Multiple Symbols", tester.test_different_symbols),
        ("Existing Endpoints", tester.test_existing_endpoints)
    ]
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name.upper()} {'='*20}")
        try:
            success = test_func()
            if not success:
                print(f"❌ {test_name} tests failed")
        except Exception as e:
            print(f"❌ {test_name} tests crashed: {e}")
            tester.test_results.append({"test": test_name, "status": "CRASH", "error": str(e)})
    
    tester.print_summary()
    
    # Return exit code based on results
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())