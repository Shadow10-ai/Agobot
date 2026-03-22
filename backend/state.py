"""Mutable global application state shared across modules."""
from config import VALID_SYMBOLS

# Simulated price data (mutable dict — contents updated, not reassigned)
SYMBOL_PRICES = {
    'BTCUSDT': 97500.0, 'ETHUSDT': 3450.0, 'BNBUSDT': 680.0, 'SOLUSDT': 185.0,
    'XRPUSDT': 2.35, 'ADAUSDT': 0.85, 'DOGEUSDT': 0.32, 'AVAXUSDT': 38.5
}

# Bot runtime state
bot_state = {
    "running": False,
    "paused": False,
    "mode": "DRY",
    "started_at": None,
    "scan_count": 0,
    "last_scan": None,
}

# Cooldown state — tracks scans since last loss
_cooldown_state = {"scans_since_loss": 999, "consecutive_losses": 0}

# Circuit breaker state
_circuit_breaker = {
    "peak_balance": 10000.0,
    "tripped": False,
    "tripped_at": None,
    "drawdown_at_trip": 0.0,
}

# ML model state
ml_model_state = {
    "model": None,
    "status": "LEARNING",
    "accuracy": 0.0,
    "precision": 0.0,
    "recall": 0.0,
    "f1": 0.0,
    "cv_score": 0.0,
    "training_samples": 0,
    "wins_in_training": 0,
    "losses_in_training": 0,
    "last_trained": None,
    "trades_since_retrain": 0,
    "feature_importance": {},
    "version": 0,
}

# Binance async client (reassigned — use `import state; state.binance_client = ...`)
binance_client = None

# Bot background asyncio task (reassigned — same pattern)
bot_task = None
