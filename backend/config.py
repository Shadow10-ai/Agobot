"""Application constants and configuration."""
from pathlib import Path
from dotenv import load_dotenv
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=False)

# JWT config
SECRET_KEY = os.environ.get('JWT_SECRET', 'cr7pt0-b0t-s3cr3t-k3y-2026')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Binance
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.environ.get('BINANCE_API_SECRET', '')

# Valid trading symbols
VALID_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT']

# Correlation groups for crypto
CORRELATION_GROUPS = {
    "BTC_ECOSYSTEM": ["BTCUSDT"],
    "ETH_ECOSYSTEM": ["ETHUSDT"],
    "ALT_LAYER1": ["SOLUSDT", "AVAXUSDT", "ADAUSDT"],
    "EXCHANGE": ["BNBUSDT"],
    "MEME": ["DOGEUSDT"],
    "PAYMENT": ["XRPUSDT"],
}

# Trading sessions (UTC hours)
TRADING_SESSIONS = {
    "ASIA": {"start": 0, "end": 8},
    "LONDON": {"start": 7, "end": 16},
    "NYC": {"start": 13, "end": 22},
    "OVERLAP": {"start": 13, "end": 16},
}

# ML configuration
ML_MODEL_PATH = ROOT_DIR / "ml_model.joblib"
ML_RETRAIN_INTERVAL = 5
ML_MIN_SAMPLES = 30
ML_FEATURES = [
    "rsi", "macd_value", "macd_signal", "macd_histogram",
    "ema_slope", "atr_percent", "volume_ratio",
    "volatility_percentile", "body_ratio", "upper_wick_ratio",
    "lower_wick_ratio", "pct_change_5", "pct_change_20",
    "technical_probability", "confidence_score", "rr_ratio",
]
ALL_ML_FEATURES = ML_FEATURES + ["side_encoded", "regime_encoded", "trend_encoded", "volume_passes_encoded"]
