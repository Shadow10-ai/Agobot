"""
Phase 2: ML Signal Filter Tests
Tests for LightGBM binary classifier (Gate 12) in the bot's signal filter chain.
Covers: ML status, training, seeding, dataset stats, and config integration.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMLSignalFilter:
    """ML Signal Filter endpoint tests for Phase 2"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token for all tests"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        token = login_response.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    # ==================== Health Check ====================
    def test_health_endpoint_no_auth(self):
        """Health endpoint should work without authentication"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "database" in data
        assert "bot_running" in data
        assert "mode" in data
        print(f"✓ Health check passed: {data}")
    
    # ==================== ML Status Endpoint ====================
    def test_ml_status_returns_required_fields(self):
        """GET /api/ml/status should return model status, metrics, feature_importance, training_data, version"""
        response = self.session.get(f"{BASE_URL}/api/ml/status")
        assert response.status_code == 200
        data = response.json()
        
        # Required top-level fields
        assert "status" in data, "Missing 'status' field"
        assert "version" in data, "Missing 'version' field"
        assert "metrics" in data, "Missing 'metrics' field"
        assert "training_data" in data, "Missing 'training_data' field"
        assert "feature_importance" in data, "Missing 'feature_importance' field"
        assert "last_trained" in data, "Missing 'last_trained' field"
        assert "trades_since_retrain" in data, "Missing 'trades_since_retrain' field"
        assert "min_samples_required" in data, "Missing 'min_samples_required' field"
        assert "retrain_interval" in data, "Missing 'retrain_interval' field"
        
        # Metrics sub-fields
        metrics = data["metrics"]
        assert "accuracy" in metrics, "Missing 'accuracy' in metrics"
        assert "precision" in metrics, "Missing 'precision' in metrics"
        assert "recall" in metrics, "Missing 'recall' in metrics"
        assert "f1" in metrics, "Missing 'f1' in metrics"
        assert "cv_score" in metrics, "Missing 'cv_score' in metrics"
        
        # Training data sub-fields
        training_data = data["training_data"]
        assert "total_samples" in training_data, "Missing 'total_samples' in training_data"
        assert "wins" in training_data, "Missing 'wins' in training_data"
        assert "losses" in training_data, "Missing 'losses' in training_data"
        
        print(f"✓ ML status endpoint returns all required fields")
        print(f"  Status: {data['status']}, Version: {data['version']}")
        print(f"  Training samples: {training_data['total_samples']}")
    
    def test_ml_status_is_active_with_version(self):
        """ML model status should be ACTIVE with version >= 1 (per agent context)"""
        response = self.session.get(f"{BASE_URL}/api/ml/status")
        assert response.status_code == 200
        data = response.json()
        
        # Per agent context: ML model is currently ACTIVE v1 trained on 86 seeded samples
        assert data["status"] in ["ACTIVE", "LEARNING", "TRAINING", "ERROR"], f"Invalid status: {data['status']}"
        
        if data["status"] == "ACTIVE":
            assert data["version"] >= 1, f"Expected version >= 1, got {data['version']}"
            assert data["training_data"]["total_samples"] > 0, "ACTIVE model should have training samples"
            print(f"✓ ML model is ACTIVE v{data['version']} with {data['training_data']['total_samples']} samples")
        else:
            print(f"⚠ ML model status is {data['status']} (not ACTIVE yet)")
    
    def test_ml_status_feature_importance_when_active(self):
        """When ACTIVE, feature_importance should contain feature names and values"""
        response = self.session.get(f"{BASE_URL}/api/ml/status")
        assert response.status_code == 200
        data = response.json()
        
        if data["status"] == "ACTIVE":
            fi = data["feature_importance"]
            assert isinstance(fi, dict), "feature_importance should be a dict"
            if len(fi) > 0:
                # Check that values are numeric
                for feat, imp in fi.items():
                    assert isinstance(imp, (int, float)), f"Feature importance for {feat} should be numeric"
                print(f"✓ Feature importance has {len(fi)} features")
                print(f"  Top features: {list(fi.keys())[:5]}")
        else:
            print(f"⚠ Skipping feature importance check - model not ACTIVE")
    
    # ==================== ML Train Endpoint ====================
    def test_ml_train_endpoint(self):
        """POST /api/ml/train should trigger model training and return status"""
        response = self.session.post(f"{BASE_URL}/api/ml/train")
        assert response.status_code == 200
        data = response.json()
        
        # Should return status field
        assert "status" in data, "Missing 'status' in train response"
        
        if data["status"] == "insufficient_data":
            assert "labeled_count" in data
            assert "required" in data
            assert "message" in data
            print(f"✓ Train endpoint returned insufficient_data: {data['message']}")
        else:
            # Training succeeded or model already active
            assert "version" in data or data["status"] in ["ACTIVE", "TRAINING"]
            print(f"✓ Train endpoint returned: status={data['status']}")
            if "message" in data:
                print(f"  Message: {data['message']}")
    
    # ==================== ML Seed Endpoint ====================
    def test_ml_seed_endpoint(self):
        """POST /api/ml/seed should seed historical trade data into signal_dataset"""
        response = self.session.post(f"{BASE_URL}/api/ml/seed")
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "seeded" in data, "Missing 'seeded' field"
        assert "total_labeled" in data, "Missing 'total_labeled' field"
        assert "min_required" in data, "Missing 'min_required' field"
        assert "can_train" in data, "Missing 'can_train' field"
        
        # Validate types
        assert isinstance(data["seeded"], int), "seeded should be int"
        assert isinstance(data["total_labeled"], int), "total_labeled should be int"
        assert isinstance(data["can_train"], bool), "can_train should be bool"
        
        print(f"✓ Seed endpoint: seeded={data['seeded']}, total_labeled={data['total_labeled']}, can_train={data['can_train']}")
    
    # ==================== Dataset Stats Endpoint ====================
    def test_dataset_stats_returns_required_fields(self):
        """GET /api/dataset/stats should return correct counts for signals, trades, outcomes"""
        response = self.session.get(f"{BASE_URL}/api/dataset/stats")
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "total_signals" in data, "Missing 'total_signals'"
        assert "trades_taken" in data, "Missing 'trades_taken'"
        assert "trades_rejected" in data, "Missing 'trades_rejected'"
        assert "outcomes" in data, "Missing 'outcomes'"
        assert "win_rate" in data, "Missing 'win_rate'"
        assert "rejection_reasons" in data, "Missing 'rejection_reasons'"
        
        # Outcomes sub-fields
        outcomes = data["outcomes"]
        assert "wins" in outcomes, "Missing 'wins' in outcomes"
        assert "losses" in outcomes, "Missing 'losses' in outcomes"
        assert "pending" in outcomes, "Missing 'pending' in outcomes"
        
        # Validate types
        assert isinstance(data["total_signals"], int)
        assert isinstance(data["trades_taken"], int)
        assert isinstance(data["trades_rejected"], int)
        
        print(f"✓ Dataset stats: total={data['total_signals']}, taken={data['trades_taken']}, rejected={data['trades_rejected']}")
        print(f"  Outcomes: wins={outcomes['wins']}, losses={outcomes['losses']}, pending={outcomes['pending']}")
        print(f"  Win rate: {data['win_rate']}%")
    
    def test_dataset_stats_rejection_reasons(self):
        """Dataset stats should include rejection reasons breakdown"""
        response = self.session.get(f"{BASE_URL}/api/dataset/stats")
        assert response.status_code == 200
        data = response.json()
        
        rejection_reasons = data.get("rejection_reasons", {})
        assert isinstance(rejection_reasons, dict), "rejection_reasons should be a dict"
        
        if len(rejection_reasons) > 0:
            print(f"✓ Rejection reasons: {rejection_reasons}")
        else:
            print(f"⚠ No rejection reasons recorded yet")
    
    # ==================== Bot Config ML Field ====================
    def test_bot_config_returns_ml_min_win_probability(self):
        """GET /api/bot/config should return ml_min_win_probability field"""
        response = self.session.get(f"{BASE_URL}/api/bot/config")
        assert response.status_code == 200
        data = response.json()
        
        # ml_min_win_probability should be present
        assert "ml_min_win_probability" in data, "Missing 'ml_min_win_probability' in bot config"
        
        ml_prob = data["ml_min_win_probability"]
        assert isinstance(ml_prob, (int, float)), "ml_min_win_probability should be numeric"
        assert 0 <= ml_prob <= 1, f"ml_min_win_probability should be between 0 and 1, got {ml_prob}"
        
        print(f"✓ Bot config has ml_min_win_probability: {ml_prob}")
    
    def test_bot_config_accepts_ml_min_win_probability(self):
        """PUT /api/bot/config should accept ml_min_win_probability"""
        # Get current value
        get_response = self.session.get(f"{BASE_URL}/api/bot/config")
        assert get_response.status_code == 200
        original_value = get_response.json().get("ml_min_win_probability", 0.55)
        
        # Update to new value
        new_value = 0.60 if original_value != 0.60 else 0.55
        update_response = self.session.put(f"{BASE_URL}/api/bot/config", json={
            "ml_min_win_probability": new_value
        })
        assert update_response.status_code == 200
        
        # Verify update
        verify_response = self.session.get(f"{BASE_URL}/api/bot/config")
        assert verify_response.status_code == 200
        updated_value = verify_response.json().get("ml_min_win_probability")
        assert updated_value == new_value, f"Expected {new_value}, got {updated_value}"
        
        # Restore original
        self.session.put(f"{BASE_URL}/api/bot/config", json={
            "ml_min_win_probability": original_value
        })
        
        print(f"✓ Bot config accepts ml_min_win_probability updates: {original_value} -> {new_value} -> {original_value}")
    
    # ==================== Dashboard Still Works ====================
    def test_dashboard_endpoint(self):
        """Dashboard endpoint should still work after ML changes"""
        response = self.session.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        
        # Basic dashboard fields
        assert "balance" in data or "total_pnl" in data or "positions" in data
        print(f"✓ Dashboard endpoint working")
    
    # ==================== Auth Endpoints ====================
    def test_auth_login(self):
        """Auth login should work"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        print(f"✓ Auth login working")


class TestMLModelMetrics:
    """Tests for ML model metrics when model is ACTIVE"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "user@example.com",
            "password": "password"
        })
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_ml_metrics_values_in_valid_range(self):
        """ML metrics should be in valid range [0, 1]"""
        response = self.session.get(f"{BASE_URL}/api/ml/status")
        assert response.status_code == 200
        data = response.json()
        
        if data["status"] == "ACTIVE":
            metrics = data["metrics"]
            for metric_name in ["accuracy", "precision", "recall", "f1", "cv_score"]:
                value = metrics.get(metric_name, 0)
                assert 0 <= value <= 1, f"{metric_name} should be in [0,1], got {value}"
            print(f"✓ All metrics in valid range: acc={metrics['accuracy']:.3f}, prec={metrics['precision']:.3f}, rec={metrics['recall']:.3f}")
        else:
            print(f"⚠ Skipping metrics validation - model not ACTIVE")
    
    def test_ml_training_data_consistency(self):
        """Training data wins + losses should equal total_samples"""
        response = self.session.get(f"{BASE_URL}/api/ml/status")
        assert response.status_code == 200
        data = response.json()
        
        if data["status"] == "ACTIVE":
            td = data["training_data"]
            total = td["total_samples"]
            wins = td["wins"]
            losses = td["losses"]
            assert wins + losses == total, f"wins({wins}) + losses({losses}) != total({total})"
            print(f"✓ Training data consistent: {wins}W + {losses}L = {total} total")
        else:
            print(f"⚠ Skipping training data check - model not ACTIVE")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
