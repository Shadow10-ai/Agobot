import requests
import sys
import time
from datetime import datetime

class CryptoTradingBotTester:
    def __init__(self, base_url="https://trading-bot-spot.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failures = []

    def log(self, message, status=None):
        """Log test results with timestamps"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        if status == "PASS":
            print(f"[{timestamp}] ✅ {message}")
        elif status == "FAIL":
            print(f"[{timestamp}] ❌ {message}")
        else:
            print(f"[{timestamp}] 🔍 {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        self.log(f"Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"{name} - Status: {response.status_code}", "PASS")
                return True, response.json() if response.content else {}
            else:
                error_msg = f"{name} - Expected {expected_status}, got {response.status_code}"
                if response.content:
                    try:
                        error_detail = response.json().get('detail', 'No detail')
                        error_msg += f" - {error_detail}"
                    except:
                        error_msg += f" - {response.text[:200]}"
                self.failures.append(error_msg)
                self.log(error_msg, "FAIL")
                return False, {}

        except Exception as e:
            error_msg = f"{name} - Error: {str(e)}"
            self.failures.append(error_msg)
            self.log(error_msg, "FAIL")
            return False, {}

    def test_auth(self):
        """Test authentication endpoints"""
        self.log("=== AUTHENTICATION TESTS ===")
        
        # Test login with test user
        success, response = self.run_test(
            "Login with test user",
            "POST",
            "/auth/login",
            200,
            data={"email": "test@trader.com", "password": "test123"}
        )
        
        if success and 'access_token' in response:
            self.token = response['access_token']
            self.log(f"Token obtained: {self.token[:20]}...")
            
            # Test get current user
            self.run_test(
                "Get current user",
                "GET",
                "/auth/me",
                200
            )
        else:
            self.log("Login failed - cannot proceed with authenticated tests", "FAIL")
            return False
        
        return True

    def test_dashboard(self):
        """Test dashboard endpoint"""
        self.log("=== DASHBOARD TESTS ===")
        
        success, response = self.run_test(
            "Get dashboard data",
            "GET",
            "/dashboard",
            200
        )
        
        if success:
            required_keys = ['balance', 'daily_pnl', 'total_pnl', 'win_rate', 'total_trades', 'bot_status']
            missing_keys = [key for key in required_keys if key not in response]
            if missing_keys:
                self.log(f"Dashboard missing keys: {missing_keys}", "FAIL")
                self.failures.append(f"Dashboard missing required keys: {missing_keys}")
            else:
                self.log("Dashboard contains all required fields", "PASS")
        
        return success

    def test_bot_control(self):
        """Test bot control endpoints"""
        self.log("=== BOT CONTROL TESTS ===")
        
        # Get bot status
        success, status_response = self.run_test(
            "Get bot status",
            "GET",
            "/bot/status",
            200
        )
        
        if success:
            required_status_keys = ['running', 'paused', 'mode', 'scan_count']
            missing_keys = [key for key in required_status_keys if key not in status_response]
            if missing_keys:
                self.log(f"Bot status missing keys: {missing_keys}", "FAIL")
                self.failures.append(f"Bot status missing required keys: {missing_keys}")
        
        # Test bot pause
        self.run_test(
            "Pause bot",
            "POST",
            "/bot/pause",
            200
        )
        
        # Wait a moment
        time.sleep(1)
        
        # Test bot resume
        self.run_test(
            "Resume bot",
            "POST",
            "/bot/resume",
            200
        )
        
        # Test bot stop
        self.run_test(
            "Stop bot",
            "POST",
            "/bot/stop",
            200
        )
        
        # Test bot start
        self.run_test(
            "Start bot",
            "POST",
            "/bot/start",
            200
        )
        
        return True

    def test_bot_config(self):
        """Test bot configuration endpoints"""
        self.log("=== BOT CONFIG TESTS ===")
        
        # Get config
        success, config_response = self.run_test(
            "Get bot config",
            "GET",
            "/bot/config",
            200
        )
        
        if success:
            required_config_keys = ['symbols', 'base_usdt_per_trade', 'risk_per_trade_percent', 'min_entry_probability']
            missing_keys = [key for key in required_config_keys if key not in config_response]
            if missing_keys:
                self.log(f"Bot config missing keys: {missing_keys}", "FAIL")
                self.failures.append(f"Bot config missing required keys: {missing_keys}")
        
        # Update config
        update_data = {
            "base_usdt_per_trade": 25.0,
            "min_entry_probability": 0.7
        }
        self.run_test(
            "Update bot config",
            "PUT",
            "/bot/config",
            200,
            data=update_data
        )
        
        return success

    def test_trading_data(self):
        """Test trading data endpoints"""
        self.log("=== TRADING DATA TESTS ===")
        
        # Test trades
        self.run_test(
            "Get trades",
            "GET",
            "/trades",
            200
        )
        
        # Test positions
        self.run_test(
            "Get positions",
            "GET",
            "/positions",
            200
        )
        
        # Test performance
        self.run_test(
            "Get performance",
            "GET",
            "/performance",
            200
        )
        
        # Test prices
        self.run_test(
            "Get prices",
            "GET",
            "/prices",
            200
        )
        
        return True

    def test_registration(self):
        """Test user registration with new user"""
        self.log("=== REGISTRATION TEST ===")
        
        # Create unique test user
        timestamp = int(time.time())
        test_email = f"test_user_{timestamp}@crypto.test"
        
        success, response = self.run_test(
            "Register new user",
            "POST",
            "/auth/register",
            200,
            data={
                "email": test_email,
                "password": "testpassword123",
                "name": f"Test User {timestamp}"
            }
        )
        
        if success and 'access_token' in response:
            self.log("Registration successful with token", "PASS")
        
        return success

    def run_all_tests(self):
        """Run all test suites"""
        self.log("🚀 Starting Crypto Trading Bot API Tests")
        self.log(f"Testing against: {self.base_url}")
        
        # Test registration first
        self.test_registration()
        
        # Test authentication
        if not self.test_auth():
            self.log("Authentication failed - stopping tests", "FAIL")
            return self.get_results()
        
        # Test all endpoints
        self.test_dashboard()
        self.test_bot_control()
        self.test_bot_config() 
        self.test_trading_data()
        
        return self.get_results()

    def get_results(self):
        """Get test results summary"""
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        self.log("=" * 50)
        self.log(f"📊 FINAL RESULTS:")
        self.log(f"   Tests Run: {self.tests_run}")
        self.log(f"   Tests Passed: {self.tests_passed}")
        self.log(f"   Tests Failed: {self.tests_run - self.tests_passed}")
        self.log(f"   Success Rate: {success_rate:.1f}%")
        
        if self.failures:
            self.log("\n❌ FAILED TESTS:")
            for failure in self.failures:
                self.log(f"   - {failure}")
        
        return {
            'tests_run': self.tests_run,
            'tests_passed': self.tests_passed,
            'success_rate': success_rate,
            'failures': self.failures
        }

def main():
    tester = CryptoTradingBotTester()
    results = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if results['success_rate'] >= 80 else 1

if __name__ == "__main__":
    sys.exit(main())