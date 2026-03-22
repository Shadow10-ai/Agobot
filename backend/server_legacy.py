from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
import asyncio
import random
import math
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import cross_val_score
import joblib
from binance import AsyncClient as BinanceAsyncClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=False)

# MongoDB connection - production-ready with Atlas support
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(
    mongo_url,
    maxPoolSize=20,
    minPoolSize=2,
    maxIdleTimeMS=30000,
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
    socketTimeoutMS=30000,
    retryWrites=True,
    retryReads=True,
)
db = client[os.environ['DB_NAME']]

# JWT config
SECRET_KEY = os.environ.get('JWT_SECRET', 'cr7pt0-b0t-s3cr3t-k3y-2026')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ====================================================================
# MODELS
# ====================================================================

class UserCreate(BaseModel):
    email: str
    password: str
    name: str = ""

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class BotConfigUpdate(BaseModel):
    symbols: Optional[List[str]] = None
    base_usdt_per_trade: Optional[float] = None
    risk_per_trade_percent: Optional[float] = None
    max_daily_loss_usdt: Optional[float] = None
    max_total_drawdown_percent: Optional[float] = None
    rsi_period: Optional[int] = None
    rsi_overbought: Optional[float] = None
    rsi_oversold: Optional[float] = None
    min_entry_probability: Optional[float] = None
    trailing_stop_activate_pips: Optional[float] = None
    trailing_stop_distance_pips: Optional[float] = None
    allow_short: Optional[bool] = None
    # Phase 1 smart filters
    max_trades_per_hour: Optional[int] = None
    max_trades_per_day: Optional[int] = None
    min_risk_reward_ratio: Optional[float] = None
    cooldown_after_loss_scans: Optional[int] = None
    min_confidence_score: Optional[float] = None
    spread_max_percent: Optional[float] = None
    min_24h_volume_usdt: Optional[float] = None
    max_slippage_percent: Optional[float] = None
    require_trend_alignment: Optional[bool] = None
    ml_min_win_probability: Optional[float] = None

class TelegramConfig(BaseModel):
    telegram_token: str = ""
    telegram_chat_id: str = ""

class BacktestRequest(BaseModel):
    symbol: str = "BTCUSDT"
    period_days: int = 30
    base_usdt_per_trade: float = 50.0
    risk_per_trade_percent: float = 0.5
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    min_entry_probability: float = 0.45
    trailing_stop_activate_pips: float = 2.4
    trailing_stop_distance_pips: float = 1.2
    atr_sl_multiplier: float = 1.2
    atr_tp_multiplier: float = 2.4
    initial_balance: float = 10000.0
    # NEW: Robustness features
    slippage_pct: float = 0.05
    fee_pct: float = 0.1
    volume_filter_multiplier: float = 1.5
    volatility_regime_enabled: bool = True
    volatility_reduce_factor: float = 0.5
    label: str = ""

class StrategyCompareRequest(BaseModel):
    symbol: str = "BTCUSDT"
    period_days: int = 30
    strategy_a: BacktestRequest
    strategy_b: BacktestRequest

# ====================================================================
# AUTH HELPERS
# ====================================================================

def create_token(user_id: str, email: str):
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ====================================================================
# AUTH ROUTES
# ====================================================================

@api_router.post("/auth/register", response_model=TokenResponse)
async def register(data: UserCreate):
    existing = await db.users.find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    user_doc = {
        "id": user_id,
        "email": data.email,
        "name": data.name or data.email.split("@")[0],
        "password_hash": pwd_context.hash(data.password),
        "created_at": now
    }
    await db.users.insert_one(user_doc)
    
    token = create_token(user_id, data.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse(id=user_id, email=data.email, name=user_doc["name"], created_at=now)
    )

@api_router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin):
    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user or not pwd_context.verify(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user["id"], user["email"])
    return TokenResponse(
        access_token=token,
        user=UserResponse(id=user["id"], email=user["email"], name=user["name"], created_at=user["created_at"])
    )

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(user=Depends(get_current_user)):
    return UserResponse(id=user["id"], email=user["email"], name=user["name"], created_at=user["created_at"])

# ====================================================================
# TRADING BOT ENGINE (DRY MODE SIMULATION)
# ====================================================================

# Binance async client (initialized on startup if keys are present)
binance_client = None
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.environ.get('BINANCE_API_SECRET', '')

VALID_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT']

# Simulated price data
SYMBOL_PRICES = {
    'BTCUSDT': 97500.0, 'ETHUSDT': 3450.0, 'BNBUSDT': 680.0, 'SOLUSDT': 185.0,
    'XRPUSDT': 2.35, 'ADAUSDT': 0.85, 'DOGEUSDT': 0.32, 'AVAXUSDT': 38.5
}

bot_state = {
    "running": False,
    "paused": False,
    "mode": "DRY",
    "started_at": None,
    "scan_count": 0,
    "last_scan": None,
}

# ====================================================================
# BINANCE LIVE MODE HELPERS
# ====================================================================

class ModeToggle(BaseModel):
    mode: str  # "DRY" or "LIVE"

async def init_binance_client():
    """Initialize the Binance async client if API keys are available."""
    global binance_client
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        logger.warning("Binance API keys not configured — LIVE mode unavailable")
        return
    try:
        binance_client = await BinanceAsyncClient.create(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET
        )
        logger.info("Binance async client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Binance client: {e}")
        binance_client = None

async def close_binance_client():
    """Close the Binance async client."""
    global binance_client
    if binance_client:
        await binance_client.close_connection()
        binance_client = None
        logger.info("Binance client connection closed")

async def fetch_live_price(symbol: str) -> float:
    """Fetch real-time price from Binance."""
    if not binance_client:
        raise RuntimeError("Binance client not initialized")
    ticker = await binance_client.get_symbol_ticker(symbol=symbol)
    return float(ticker["price"])

async def fetch_live_candles(symbol: str, interval: str = "3m", limit: int = 60):
    """Fetch real kline candles from Binance and return in our internal format."""
    if not binance_client:
        raise RuntimeError("Binance client not initialized")
    raw = await binance_client.get_klines(symbol=symbol, interval=interval, limit=limit)
    candles = []
    for k in raw:
        candles.append({
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "time": int(k[0])
        })
    return candles

async def place_live_market_order(symbol: str, side: str, quote_qty: float):
    """Place a real market order on Binance. Returns order result dict."""
    if not binance_client:
        raise RuntimeError("Binance client not initialized")
    order = await binance_client.create_order(
        symbol=symbol,
        side=side,
        type="MARKET",
        quoteOrderQty=quote_qty
    )
    return {
        "order_id": order["orderId"],
        "status": order["status"],
        "executed_qty": float(order["executedQty"]),
        "cummulative_quote_qty": float(order["cummulativeQuoteQty"]),
        "avg_price": float(order["cummulativeQuoteQty"]) / float(order["executedQty"]) if float(order["executedQty"]) > 0 else 0,
    }

# ====================================================================
# TECHNICAL INDICATORS (ported from Node.js)
# ====================================================================

def ema(values, period):
    if not values or len(values) < period:
        return None
    k = 2 / (period + 1)
    result = sum(values[:period]) / period
    for i in range(period, len(values)):
        result = values[i] * k + result * (1 - k)
    return result if math.isfinite(result) else None

def sma(values, period):
    if not values or len(values) < period:
        return None
    return sum(values[-period:]) / period

def atr_calc(candles, period=14):
    if not candles or len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        tr = max(
            candles[i]['high'] - candles[i]['low'],
            abs(candles[i]['high'] - candles[i-1]['close']),
            abs(candles[i]['low'] - candles[i-1]['close'])
        )
        trs.append(tr)
    return sum(trs[-period:]) / period if trs else None

def rsi_calc(closes, period=14):
    if not closes or len(closes) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i-1]
        if diff >= 0:
            gains += diff
        else:
            losses += abs(diff)
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i-1]
        gain = diff if diff >= 0 else 0
        loss = abs(diff) if diff < 0 else 0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0 and avg_gain == 0:
        return 50
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return max(0, min(100, 100 - 100 / (1 + rs)))

def macd_calc(closes, fast=12, slow=26, signal=9):
    if not closes or len(closes) < slow + signal - 1:
        return None
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    if fast_ema is None or slow_ema is None:
        return None
    macd_val = fast_ema - slow_ema
    return {"macd": macd_val, "signal": macd_val * 0.8, "histogram": macd_val * 0.2}

def bollinger_bands(closes, period=20, std_dev=2):
    if not closes or len(closes) < period:
        return None
    mean = sma(closes, period)
    if mean is None:
        return None
    sq_diffs = [(c - mean) ** 2 for c in closes[-period:]]
    std = math.sqrt(sum(sq_diffs) / period)
    return {"upper": mean + std * std_dev, "middle": mean, "lower": mean - std * std_dev}

# ====================================================================
# ADVANCED FILTERS: Volume, Volatility Regime, Correlation
# ====================================================================

def volume_filter(candles, multiplier=1.5):
    """Check if recent volume exceeds average by multiplier. Low volume = fake signal."""
    if not candles or len(candles) < 20:
        return True, 1.0
    volumes = [c['volume'] for c in candles[-20:]]
    avg_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 1
    current_vol = volumes[-1]
    if avg_vol <= 0:
        return True, 1.0
    vol_ratio = current_vol / avg_vol
    passes = vol_ratio >= multiplier
    return passes, round(vol_ratio, 2)

def volatility_regime(candles, period=14, lookback=100):
    """Detect if market is in high/low volatility regime using ATR percentile."""
    if not candles or len(candles) < lookback + period:
        return "NORMAL", 50.0, 1.0
    
    # Calculate rolling ATR values
    atr_values = []
    for i in range(period + 1, min(len(candles), lookback + period + 1)):
        window = candles[max(0, i - period - 1):i]
        a = atr_calc(window, period)
        if a and a > 0:
            atr_values.append(a)
    
    if len(atr_values) < 10:
        return "NORMAL", 50.0, 1.0
    
    current_atr = atr_values[-1] if atr_values else 0
    sorted_atrs = sorted(atr_values)
    percentile = sorted_atrs.index(min(sorted_atrs, key=lambda x: abs(x - current_atr))) / len(sorted_atrs) * 100
    
    if percentile >= 80:
        regime = "HIGH_VOL"
        size_mult = 0.5  # Reduce size in high vol
    elif percentile <= 20:
        regime = "LOW_VOL"
        size_mult = 0.7  # Cautious in low vol (breakout traps)
    else:
        regime = "NORMAL"
        size_mult = 1.0
    
    return regime, round(percentile, 1), round(size_mult, 2)

# Correlation groups for crypto
CORRELATION_GROUPS = {
    "BTC_ECOSYSTEM": ["BTCUSDT"],
    "ETH_ECOSYSTEM": ["ETHUSDT"],
    "ALT_LAYER1": ["SOLUSDT", "AVAXUSDT", "ADAUSDT"],
    "EXCHANGE": ["BNBUSDT"],
    "MEME": ["DOGEUSDT"],
    "PAYMENT": ["XRPUSDT"],
}

def get_correlation_group(symbol):
    for group, symbols in CORRELATION_GROUPS.items():
        if symbol in symbols:
            return group
    return symbol

async def check_correlation_exposure(symbol, db_ref):
    """Check if we're already exposed to correlated assets."""
    target_group = get_correlation_group(symbol)
    open_positions = await db_ref.positions.find({"status": "OPEN"}, {"_id": 0, "symbol": 1}).to_list(20)
    
    correlated_count = 0
    total_open = len(open_positions)
    for pos in open_positions:
        if get_correlation_group(pos["symbol"]) == target_group:
            correlated_count += 1
    
    # Max 1 position per correlation group, max 3 total
    can_open = correlated_count == 0 and total_open < 3
    exposure_pct = round(correlated_count / max(total_open, 1) * 100, 1) if total_open > 0 else 0
    
    return can_open, {
        "group": target_group,
        "correlated_positions": correlated_count,
        "total_positions": total_open,
        "exposure_pct": exposure_pct
    }

def structure_stop_loss(candles, side='LONG', atr=None, buffer_atr_mult=0.3):
    """Place SL below nearest swing low instead of arbitrary ATR level."""
    if not candles or len(candles) < 5:
        return None
    
    # Find recent swing lows (last 10 candles)
    lows = [c['low'] for c in candles[-10:]]
    swing_low = min(lows)
    
    if atr and atr > 0:
        # Add buffer below swing low
        sl = swing_low - (atr * buffer_atr_mult)
    else:
        sl = swing_low * 0.998
    
    return max(sl, 0)

# ====================================================================
# PHASE 1: SMART FILTERS & DATASET BUILDER
# ====================================================================

# Cooldown state — tracks scans since last loss
_cooldown_state = {"scans_since_loss": 999, "consecutive_losses": 0}

def check_spread(candles, max_spread_pct=0.15):
    """Check if the bid-ask spread is acceptable. 
    In DRY mode, estimate from candle high-low range."""
    if not candles or len(candles) < 2:
        return True, 0.0
    last = candles[-1]
    # Estimate spread as a fraction of the candle range vs price
    candle_range = last['high'] - last['low']
    mid = (last['high'] + last['low']) / 2
    estimated_spread_pct = (candle_range / mid * 100) * 0.1 if mid > 0 else 0
    return estimated_spread_pct <= max_spread_pct, round(estimated_spread_pct, 4)

def estimate_slippage(candles, trade_usdt, max_slippage_pct=0.1):
    """Estimate slippage based on recent volume. Higher trade size relative 
    to volume = more slippage."""
    if not candles or len(candles) < 5:
        return True, 0.0
    recent_vols = [c['volume'] for c in candles[-5:]]
    avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 1
    price = candles[-1]['close']
    avg_vol_usdt = avg_vol * price
    if avg_vol_usdt <= 0:
        return False, 999.0
    # Slippage estimate: trade size / average volume * impact factor
    impact = (trade_usdt / avg_vol_usdt) * 100 * 2  # 2x multiplier for conservative est
    return impact <= max_slippage_pct, round(impact, 4)

def check_min_liquidity(candles, min_volume_usdt=1_000_000):
    """Check if 24h volume (approximated from recent candles) meets minimum."""
    if not candles or len(candles) < 10:
        return True, 0
    # Approximate 24h volume from recent candle data
    price = candles[-1]['close']
    total_vol = sum(c['volume'] for c in candles[-20:])  # ~1h of 3m candles
    estimated_24h = total_vol * 24 * price  # rough extrapolation
    return estimated_24h >= min_volume_usdt, round(estimated_24h, 0)

def check_cooldown(config):
    """Check if we're in a cooldown period after consecutive losses."""
    required = config.get("cooldown_after_loss_scans", 6)
    if _cooldown_state["scans_since_loss"] < required:
        return False, _cooldown_state["scans_since_loss"], required
    return True, _cooldown_state["scans_since_loss"], required

def update_cooldown(is_loss):
    """Update cooldown state after a trade closes."""
    if is_loss:
        _cooldown_state["scans_since_loss"] = 0
        _cooldown_state["consecutive_losses"] += 1
    else:
        _cooldown_state["consecutive_losses"] = 0

def increment_cooldown():
    """Called each scan to count up from last loss."""
    _cooldown_state["scans_since_loss"] += 1

def multi_timeframe_trend(candles, side):
    """Check if trade direction aligns with higher timeframe trend.
    Uses the full candle dataset to simulate higher TF analysis."""
    if not candles or len(candles) < 30:
        return True, "INSUFFICIENT_DATA"
    
    # Short-term trend (last 10 candles ~30min)
    short_closes = [c['close'] for c in candles[-10:]]
    short_ema = ema(short_closes, 5) or short_closes[-1]
    
    # Medium-term trend (last 30 candles ~1.5h)
    med_closes = [c['close'] for c in candles[-30:]]
    med_ema = ema(med_closes, 13) or med_closes[-1]
    
    # Long-term trend (all candles ~3h)
    long_ema = ema([c['close'] for c in candles], 26) or candles[-1]['close']
    
    # Determine trend: all EMAs aligned
    if short_ema > med_ema > long_ema:
        htf_trend = "BULLISH"
    elif short_ema < med_ema < long_ema:
        htf_trend = "BEARISH"
    else:
        htf_trend = "MIXED"
    
    if side == "LONG":
        aligned = htf_trend in ("BULLISH", "MIXED")
    else:  # SHORT
        aligned = htf_trend in ("BEARISH", "MIXED")
    
    return aligned, htf_trend

def check_risk_reward(entry, sl, tp, side, min_rr=2.5):
    """Enforce minimum risk/reward ratio."""
    if side == "LONG":
        risk = abs(entry - sl)
        reward = abs(tp - entry)
    else:
        risk = abs(sl - entry)
        reward = abs(entry - tp)
    
    if risk <= 0:
        return False, 0.0
    rr_ratio = reward / risk
    return rr_ratio >= min_rr, round(rr_ratio, 2)

async def check_overtrade_limits(db_ref, config):
    """Check if we've exceeded max trades per hour or per day."""
    max_per_hour = config.get("max_trades_per_hour", 2)
    max_per_day = config.get("max_trades_per_day", 8)
    
    now = datetime.now(timezone.utc)
    hour_ago = (now - timedelta(hours=1)).isoformat()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    trades_last_hour = await db_ref.trades.count_documents({"closed_at": {"$gte": hour_ago}})
    trades_today = await db_ref.trades.count_documents({"closed_at": {"$gte": day_start}})
    
    hour_ok = trades_last_hour < max_per_hour
    day_ok = trades_today < max_per_day
    
    return hour_ok and day_ok, trades_last_hour, max_per_hour, trades_today, max_per_day

def calculate_confidence_score(signal, candles, config):
    """Composite confidence score combining technical probability, 
    volume quality, regime favorability, and trend alignment."""
    tech_prob = signal["probability"]
    
    # Volume quality (0-1)
    vol_score = min(1.0, signal.get("volume_ratio", 0.5) / 2.0) if signal.get("volume_passes") else 0.2
    
    # Regime score
    regime = signal.get("volatility_regime", "NORMAL")
    regime_score = {"LOW_VOL": 0.6, "NORMAL": 0.85, "HIGH_VOL": 0.4}.get(regime, 0.5)
    
    # Trend alignment score
    side = signal.get("side", "LONG")
    aligned, htf = multi_timeframe_trend(candles, side)
    trend_score = 1.0 if aligned and htf != "MIXED" else (0.7 if aligned else 0.3)
    
    # R:R score
    entry, sl, tp = signal["price"], signal["sl"], signal["tp"]
    if side == "LONG":
        risk = abs(entry - sl)
        reward = abs(tp - entry)
    else:
        risk = abs(sl - entry)
        reward = abs(entry - tp)
    rr = reward / risk if risk > 0 else 0
    rr_score = min(1.0, rr / 3.0)
    
    # Weighted composite
    confidence = (
        tech_prob * 0.30 +
        vol_score * 0.15 +
        regime_score * 0.15 +
        trend_score * 0.25 +
        rr_score * 0.15
    )
    
    return round(confidence, 4), {
        "technical": round(tech_prob, 4),
        "volume": round(vol_score, 4),
        "regime": round(regime_score, 4),
        "trend_alignment": round(trend_score, 4),
        "risk_reward": round(rr_score, 4),
        "htf_trend": htf,
        "rr_ratio": round(rr, 2)
    }

async def log_signal_to_dataset(db_ref, signal, candles, confidence, confidence_breakdown, filters_passed, trade_taken, config):
    """Log every signal (taken or rejected) with full features for ML training."""
    if not candles or len(candles) < 20:
        return
    
    last_candle = candles[-1]
    closes = [c['close'] for c in candles]
    price = closes[-1]
    
    # Candle structure features
    body = abs(last_candle['close'] - last_candle['open'])
    upper_wick = last_candle['high'] - max(last_candle['close'], last_candle['open'])
    lower_wick = min(last_candle['close'], last_candle['open']) - last_candle['low']
    candle_range = last_candle['high'] - last_candle['low']
    body_ratio = body / candle_range if candle_range > 0 else 0
    
    # Price change features
    pct_change_5 = (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0
    pct_change_20 = (closes[-1] - closes[-20]) / closes[-20] * 100 if len(closes) >= 20 else 0
    
    # EMA slope
    ema5 = ema(closes, 5)
    ema13 = ema(closes, 13)
    ema_slope = ((ema5 - ema13) / price * 100) if ema5 and ema13 and price > 0 else 0
    
    dataset_entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": signal["symbol"],
        "side": signal.get("side", "LONG"),
        "price": price,
        # Indicators
        "rsi": signal["indicators"]["rsi"],
        "macd_value": signal["indicators"]["macd_value"],
        "macd_signal": signal["indicators"]["macd_signal"],
        "macd_histogram": signal["indicators"]["macd_histogram"],
        "ema_fast": signal["indicators"]["ema_fast"],
        "ema_slow": signal["indicators"]["ema_slow"],
        "ema_slope": round(ema_slope, 6),
        "bb_upper": signal["indicators"]["bb_upper"],
        "bb_middle": signal["indicators"]["bb_middle"],
        "bb_lower": signal["indicators"]["bb_lower"],
        "atr": signal["indicators"]["atr"],
        "atr_percent": round(signal["atr"] / price * 100, 4) if price > 0 else 0,
        # Market conditions
        "volume_ratio": signal.get("volume_ratio", 0),
        "volume_passes": signal.get("volume_passes", False),
        "volatility_regime": signal.get("volatility_regime", "NORMAL"),
        "volatility_percentile": signal.get("volatility_percentile", 0),
        "trend": signal.get("trend", "RANGE"),
        # Candle structure
        "body_ratio": round(body_ratio, 4),
        "upper_wick_ratio": round(upper_wick / candle_range, 4) if candle_range > 0 else 0,
        "lower_wick_ratio": round(lower_wick / candle_range, 4) if candle_range > 0 else 0,
        "pct_change_5": round(pct_change_5, 4),
        "pct_change_20": round(pct_change_20, 4),
        # Scores
        "technical_probability": signal["probability"],
        "confidence_score": confidence,
        "confidence_breakdown": confidence_breakdown,
        # Filters
        "filters_passed": filters_passed,
        "trade_taken": trade_taken,
        # SL/TP
        "sl": signal["sl"],
        "tp": signal["tp"],
        "rr_ratio": confidence_breakdown.get("rr_ratio", 0),
        # Outcome (filled later when trade closes)
        "outcome": None,  # "WIN" or "LOSS"
        "pnl": None,
        "pnl_percent": None,
    }
    
    await db_ref.signal_dataset.insert_one(dataset_entry)

async def update_dataset_outcome(db_ref, symbol, side, entry_price, pnl, pnl_pct, exit_reason, opened_at):
    """Update the signal dataset entry with trade outcome for ML training."""
    outcome = "WIN" if pnl > 0 else "LOSS"
    await db_ref.signal_dataset.update_one(
        {"symbol": symbol, "side": side, "trade_taken": True, "outcome": None, "timestamp": {"$gte": opened_at}},
        {"$set": {"outcome": outcome, "pnl": pnl, "pnl_percent": pnl_pct, "exit_reason": exit_reason}},
    )
    # Trigger ML retrain check
    ml_model_state["trades_since_retrain"] += 1
    if ml_model_state["trades_since_retrain"] >= ML_RETRAIN_INTERVAL:
        asyncio.create_task(train_ml_model(db_ref))

# ====================================================================
# PHASE 2: ML SIGNAL FILTER
# ====================================================================

ML_MODEL_PATH = ROOT_DIR / "ml_model.joblib"
ML_RETRAIN_INTERVAL = 5  # Retrain every 5 closed trades
ML_MIN_SAMPLES = 30  # Minimum labeled outcomes to activate ML
ML_FEATURES = [
    "rsi", "macd_value", "macd_signal", "macd_histogram",
    "ema_slope", "atr_percent", "volume_ratio",
    "volatility_percentile", "body_ratio", "upper_wick_ratio",
    "lower_wick_ratio", "pct_change_5", "pct_change_20",
    "technical_probability", "confidence_score", "rr_ratio",
]

ml_model_state = {
    "model": None,
    "status": "LEARNING",  # LEARNING | ACTIVE | TRAINING | ERROR
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

def extract_ml_features(doc):
    """Extract feature vector from a signal_dataset document."""
    features = []
    for feat in ML_FEATURES:
        val = doc.get(feat, 0)
        if val is None:
            val = 0
        features.append(float(val))
    # Add encoded categorical features
    side_val = 1.0 if doc.get("side") == "LONG" else 0.0
    regime_map = {"LOW_VOL": 0.0, "NORMAL": 0.5, "HIGH_VOL": 1.0}
    regime_val = regime_map.get(doc.get("volatility_regime", "NORMAL"), 0.5)
    trend_map = {"DOWNTREND": 0.0, "RANGE": 0.5, "UPTREND": 1.0}
    trend_val = trend_map.get(doc.get("trend", "RANGE"), 0.5)
    volume_passes = 1.0 if doc.get("volume_passes") else 0.0
    features.extend([side_val, regime_val, trend_val, volume_passes])
    return features

ALL_ML_FEATURES = ML_FEATURES + ["side_encoded", "regime_encoded", "trend_encoded", "volume_passes_encoded"]

async def train_ml_model(db_ref):
    """Train or retrain the ML model on signal_dataset outcomes."""
    global ml_model_state
    
    if ml_model_state["status"] == "TRAINING":
        return  # Already training
    
    ml_model_state["status"] = "TRAINING"
    ml_model_state["trades_since_retrain"] = 0
    
    try:
        # Fetch all labeled data
        labeled = await db_ref.signal_dataset.find(
            {"outcome": {"$in": ["WIN", "LOSS"]}}, {"_id": 0}
        ).to_list(10000)
        
        if len(labeled) < ML_MIN_SAMPLES:
            ml_model_state["status"] = "LEARNING"
            ml_model_state["training_samples"] = len(labeled)
            logger.info(f"ML: Only {len(labeled)} labeled samples (need {ML_MIN_SAMPLES}). Staying in LEARNING mode.")
            return
        
        # Build feature matrix and labels
        X, y = [], []
        for doc in labeled:
            features = extract_ml_features(doc)
            label = 1 if doc["outcome"] == "WIN" else 0
            X.append(features)
            y.append(label)
        
        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.int32)
        
        # Use DataFrame for feature names
        import pandas as pd
        X_df = pd.DataFrame(X, columns=ALL_ML_FEATURES)
        
        wins = int(np.sum(y))
        losses = len(y) - wins
        
        # Handle class imbalance
        scale_pos = losses / max(wins, 1)
        
        # Train LightGBM
        model = lgb.LGBMClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.05,
            min_child_samples=max(3, len(y) // 20),
            scale_pos_weight=scale_pos,
            verbose=-1,
            random_state=42,
        )
        
        # Cross-validation
        n_folds = min(5, max(2, len(y) // 10))
        cv_scores = cross_val_score(model, X_df, y, cv=n_folds, scoring="accuracy")
        
        # Fit on all data
        model.fit(X_df, y)
        
        # Feature importance
        importances = model.feature_importances_
        feature_imp = {name: round(float(imp), 4) for name, imp in zip(ALL_ML_FEATURES, importances)}
        feature_imp = dict(sorted(feature_imp.items(), key=lambda x: -x[1])[:10])
        
        # Evaluate
        preds = model.predict(X_df)
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        acc = accuracy_score(y, preds)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        f1 = f1_score(y, preds, zero_division=0)
        
        # Save model
        joblib.dump(model, ML_MODEL_PATH)
        
        ml_model_state.update({
            "model": model,
            "status": "ACTIVE",
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "cv_score": round(float(np.mean(cv_scores)), 4),
            "training_samples": len(y),
            "wins_in_training": wins,
            "losses_in_training": losses,
            "last_trained": datetime.now(timezone.utc).isoformat(),
            "feature_importance": feature_imp,
            "version": ml_model_state["version"] + 1,
        })
        
        logger.info(f"ML Model trained v{ml_model_state['version']}: {len(y)} samples, "
                     f"acc={acc:.3f}, prec={prec:.3f}, rec={rec:.3f}, f1={f1:.3f}, cv={np.mean(cv_scores):.3f}")
    
    except Exception as e:
        ml_model_state["status"] = "ERROR"
        logger.error(f"ML training failed: {e}")

def ml_predict(signal_doc):
    """Predict WIN probability for a signal using the trained ML model.
    Returns (probability, prediction) or (None, None) if model not active."""
    if ml_model_state["status"] != "ACTIVE" or ml_model_state["model"] is None:
        return None, None
    
    try:
        features = extract_ml_features(signal_doc)
        X = np.array([features], dtype=np.float32)
        # Use DataFrame for consistent feature names
        import pandas as pd
        X_df = pd.DataFrame(X, columns=ALL_ML_FEATURES)
        prob = ml_model_state["model"].predict_proba(X_df)[0]
        win_prob = float(prob[1]) if len(prob) > 1 else float(prob[0])
        prediction = "WIN" if win_prob >= 0.5 else "LOSS"
        return round(win_prob, 4), prediction
    except Exception as e:
        logger.warning(f"ML prediction failed: {e}")
        return None, None

async def load_ml_model():
    """Load saved ML model on startup, then retrain if data available."""
    if ML_MODEL_PATH.exists():
        try:
            ml_model_state["model"] = joblib.load(ML_MODEL_PATH)
            ml_model_state["status"] = "ACTIVE"
            logger.info("ML model loaded from disk")
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}")
            ml_model_state["status"] = "LEARNING"
    else:
        ml_model_state["status"] = "LEARNING"
        logger.info("No saved ML model found. Starting in LEARNING mode.")

async def seed_dataset_from_trades(db_ref):
    """Seed the signal_dataset from historical trades that don't have dataset entries.
    This gives the ML model initial training data."""
    existing_count = await db_ref.signal_dataset.count_documents({"outcome": {"$ne": None}})
    if existing_count >= ML_MIN_SAMPLES:
        return  # Already have enough data
    
    trades = await db_ref.trades.find({}, {"_id": 0}).sort("closed_at", -1).limit(200).to_list(200)
    seeded = 0
    for trade in trades:
        # Check if this trade already has a dataset entry
        exists = await db_ref.signal_dataset.find_one({
            "symbol": trade["symbol"],
            "trade_taken": True,
            "outcome": {"$ne": None},
            "timestamp": trade.get("opened_at", "")
        })
        if exists:
            continue
        
        # Create a synthetic dataset entry from the trade
        entry_price = trade.get("entry_price", 0)
        if entry_price <= 0:
            continue
        
        pnl = trade.get("pnl", 0)
        outcome = "WIN" if pnl > 0 else "LOSS"
        atr_est = abs(trade.get("stop_loss", entry_price) - entry_price) / 1.2 if trade.get("stop_loss") else entry_price * 0.01
        
        dataset_entry = {
            "id": str(uuid.uuid4()),
            "timestamp": trade.get("opened_at", datetime.now(timezone.utc).isoformat()),
            "symbol": trade["symbol"],
            "side": trade.get("side", "LONG"),
            "price": entry_price,
            "rsi": 45 + random.uniform(-10, 10),
            "macd_value": random.uniform(-0.001, 0.001),
            "macd_signal": random.uniform(-0.001, 0.001),
            "macd_histogram": random.uniform(-0.0005, 0.0005),
            "ema_fast": entry_price * (1 + random.uniform(-0.002, 0.002)),
            "ema_slow": entry_price * (1 + random.uniform(-0.003, 0.003)),
            "ema_slope": random.uniform(-0.5, 0.5),
            "bb_upper": entry_price * 1.02,
            "bb_middle": entry_price,
            "bb_lower": entry_price * 0.98,
            "atr": round(atr_est, 6),
            "atr_percent": round(atr_est / entry_price * 100, 4),
            "volume_ratio": random.uniform(0.5, 2.5),
            "volume_passes": random.choice([True, False]),
            "volatility_regime": random.choice(["LOW_VOL", "NORMAL", "HIGH_VOL"]),
            "volatility_percentile": random.uniform(0.1, 0.9),
            "trend": random.choice(["UPTREND", "RANGE", "DOWNTREND"]),
            "body_ratio": random.uniform(0.2, 0.8),
            "upper_wick_ratio": random.uniform(0.05, 0.3),
            "lower_wick_ratio": random.uniform(0.05, 0.3),
            "pct_change_5": random.uniform(-2, 2),
            "pct_change_20": random.uniform(-5, 5),
            "technical_probability": random.uniform(0.5, 0.85),
            "confidence_score": random.uniform(0.5, 0.9),
            "confidence_breakdown": {},
            "filters_passed": {},
            "trade_taken": True,
            "sl": trade.get("stop_loss", 0),
            "tp": trade.get("take_profit", 0),
            "rr_ratio": 2.0 + random.uniform(-0.5, 1.0),
            "outcome": outcome,
            "pnl": pnl,
            "pnl_percent": trade.get("pnl_percent", 0),
            "exit_reason": trade.get("exit_reason", "UNKNOWN"),
            "source": "seeded_from_trades",
        }
        await db_ref.signal_dataset.insert_one(dataset_entry)
        seeded += 1
    
    if seeded > 0:
        logger.info(f"ML: Seeded {seeded} entries from historical trades into dataset")

# ====================================================================
# SIMULATED PRICE GENERATION
# ====================================================================

def generate_candles(symbol, count=60):
    base_price = SYMBOL_PRICES.get(symbol, 100.0)
    candles = []
    price = base_price * (1 + random.uniform(-0.02, 0.02))
    for i in range(count):
        volatility = base_price * 0.003
        open_p = price
        change = random.gauss(0, volatility)
        close_p = open_p + change
        high_p = max(open_p, close_p) + abs(random.gauss(0, volatility * 0.5))
        low_p = min(open_p, close_p) - abs(random.gauss(0, volatility * 0.5))
        candles.append({
            "open": round(open_p, 8),
            "high": round(high_p, 8),
            "low": round(low_p, 8),
            "close": round(close_p, 8),
            "volume": round(random.uniform(100, 10000), 2),
            "time": int((datetime.now(timezone.utc) - timedelta(minutes=(count - i) * 3)).timestamp() * 1000)
        })
        price = close_p
    # Update current price
    SYMBOL_PRICES[symbol] = round(candles[-1]['close'], 8)
    return candles

# ====================================================================
# PHASE 3: PROFESSIONAL-GRADE FEATURES
# ====================================================================

# --- 1. DRAWDOWN CIRCUIT BREAKER ---
_circuit_breaker = {
    "peak_balance": 10000.0,
    "tripped": False,
    "tripped_at": None,
    "drawdown_at_trip": 0.0,
}

async def check_circuit_breaker(db_ref, config):
    """Check if drawdown exceeds threshold, auto-pause bot if so."""
    max_dd = config.get("max_total_drawdown_percent", 5.0)
    
    bal_doc = await db_ref.bot_state.find_one({"key": "account_balance"})
    current_balance = bal_doc["value"] if bal_doc else 10000.0
    
    if current_balance > _circuit_breaker["peak_balance"]:
        _circuit_breaker["peak_balance"] = current_balance
    
    peak = _circuit_breaker["peak_balance"]
    drawdown_pct = ((peak - current_balance) / peak) * 100 if peak > 0 else 0
    
    if drawdown_pct >= max_dd and not _circuit_breaker["tripped"]:
        _circuit_breaker["tripped"] = True
        _circuit_breaker["tripped_at"] = datetime.now(timezone.utc).isoformat()
        _circuit_breaker["drawdown_at_trip"] = round(drawdown_pct, 2)
        bot_state["paused"] = True
        logger.warning(f"CIRCUIT BREAKER TRIPPED: Drawdown {drawdown_pct:.2f}% >= {max_dd}%. Bot paused.")
        return False, round(drawdown_pct, 2)
    
    return True, round(drawdown_pct, 2)

def reset_circuit_breaker():
    """Manually reset the circuit breaker."""
    _circuit_breaker["tripped"] = False
    _circuit_breaker["tripped_at"] = None
    _circuit_breaker["drawdown_at_trip"] = 0.0

# --- 2. SESSION-AWARE TRADING ---
TRADING_SESSIONS = {
    "ASIA": {"start": 0, "end": 8},       # 00:00-08:00 UTC
    "LONDON": {"start": 7, "end": 16},     # 07:00-16:00 UTC
    "NYC": {"start": 13, "end": 22},       # 13:00-22:00 UTC
    "OVERLAP": {"start": 13, "end": 16},   # 13:00-16:00 UTC (highest liquidity)
}

def check_trading_session(config):
    """Check if current time falls within allowed trading sessions."""
    allowed = config.get("allowed_sessions", ["ASIA", "LONDON", "NYC"])
    if not allowed or "ALL" in allowed:
        return True, "ALL"
    
    now_utc = datetime.now(timezone.utc)
    current_hour = now_utc.hour
    
    for session_name in allowed:
        session = TRADING_SESSIONS.get(session_name)
        if not session:
            continue
        start, end = session["start"], session["end"]
        if start <= end:
            if start <= current_hour < end:
                return True, session_name
        else:  # Wraps around midnight
            if current_hour >= start or current_hour < end:
                return True, session_name
    
    return False, "OUTSIDE_SESSION"

# --- 3. ADVANCED MARKET REGIME DETECTION ---
def detect_market_regime_advanced(candles):
    """Advanced market regime detection using multiple signals.
    Returns: regime (TRENDING_UP, TRENDING_DOWN, RANGING, VOLATILE, CALM), 
    strength (0-1), and details."""
    if not candles or len(candles) < 30:
        return "UNKNOWN", 0.5, {}
    
    closes = np.array([c['close'] for c in candles])
    highs = np.array([c['high'] for c in candles])
    lows = np.array([c['low'] for c in candles])
    volumes = np.array([c['volume'] for c in candles])
    
    # 1. Trend strength via linear regression slope
    x = np.arange(len(closes))
    slope = np.polyfit(x, closes, 1)[0]
    price_mean = np.mean(closes)
    trend_strength = abs(slope / price_mean * 1000) if price_mean > 0 else 0  # Normalized
    
    # 2. Volatility (ATR-based)
    ranges = highs - lows
    atr = np.mean(ranges[-14:])
    atr_pct = (atr / closes[-1] * 100) if closes[-1] > 0 else 0
    
    # 3. ADX-like directional indicator (simplified)
    up_moves = np.diff(highs)
    down_moves = -np.diff(lows)
    plus_dm = np.where((up_moves > down_moves) & (up_moves > 0), up_moves, 0)
    minus_dm = np.where((down_moves > up_moves) & (down_moves > 0), down_moves, 0)
    adx_proxy = abs(np.mean(plus_dm[-14:]) - np.mean(minus_dm[-14:])) / max(atr, 0.0001)
    
    # 4. Volume trend
    vol_recent = np.mean(volumes[-5:])
    vol_avg = np.mean(volumes[-20:])
    vol_expansion = vol_recent / vol_avg if vol_avg > 0 else 1.0
    
    # 5. Price range compression (Bollinger bandwidth)
    bb_std = np.std(closes[-20:])
    bb_bandwidth = (bb_std / price_mean * 100) if price_mean > 0 else 0
    
    # Classify regime
    if atr_pct > 2.0 and vol_expansion > 1.5:
        regime = "VOLATILE"
        strength = min(1.0, atr_pct / 3.0)
    elif trend_strength > 0.3 and adx_proxy > 0.3:
        regime = "TRENDING_UP" if slope > 0 else "TRENDING_DOWN"
        strength = min(1.0, trend_strength)
    elif bb_bandwidth < 1.0 and atr_pct < 0.8:
        regime = "CALM"
        strength = min(1.0, 1.0 - bb_bandwidth)
    else:
        regime = "RANGING"
        strength = 0.5
    
    details = {
        "trend_slope": round(float(slope), 8),
        "trend_strength": round(float(trend_strength), 4),
        "atr_percent": round(float(atr_pct), 4),
        "adx_proxy": round(float(adx_proxy), 4),
        "volume_expansion": round(float(vol_expansion), 4),
        "bb_bandwidth": round(float(bb_bandwidth), 4),
    }
    
    return regime, round(float(strength), 4), details

# --- 4. MONTE CARLO RISK ANALYSIS ---
async def run_monte_carlo(db_ref, n_simulations=1000, n_trades_per_sim=100, initial_balance=10000):
    """Run Monte Carlo simulation using historical trade distribution."""
    trades = await db_ref.trades.find({}, {"_id": 0, "pnl": 1, "pnl_percent": 1}).to_list(5000)
    if len(trades) < 10:
        return {"error": "Need at least 10 historical trades", "trade_count": len(trades)}
    
    pnls = np.array([t["pnl"] for t in trades if t.get("pnl") is not None])
    if len(pnls) < 10:
        return {"error": "Not enough PnL data", "trade_count": len(pnls)}
    
    results = []
    ruin_count = 0
    max_drawdowns = []
    
    for _ in range(n_simulations):
        balance = initial_balance
        peak = balance
        max_dd = 0
        
        sampled_pnls = np.random.choice(pnls, size=n_trades_per_sim, replace=True)
        
        for pnl in sampled_pnls:
            balance += pnl
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
            if balance <= 0:
                ruin_count += 1
                break
        
        results.append(balance)
        max_drawdowns.append(max_dd)
    
    results = np.array(results)
    max_drawdowns = np.array(max_drawdowns)
    
    return {
        "simulations": n_simulations,
        "trades_per_sim": n_trades_per_sim,
        "initial_balance": initial_balance,
        "historical_trades_used": len(pnls),
        "avg_pnl_per_trade": round(float(np.mean(pnls)), 4),
        "win_rate": round(float(np.sum(pnls > 0) / len(pnls) * 100), 1),
        "results": {
            "mean_final_balance": round(float(np.mean(results)), 2),
            "median_final_balance": round(float(np.median(results)), 2),
            "std_final_balance": round(float(np.std(results)), 2),
            "best_case": round(float(np.max(results)), 2),
            "worst_case": round(float(np.min(results)), 2),
            "percentile_5": round(float(np.percentile(results, 5)), 2),
            "percentile_25": round(float(np.percentile(results, 25)), 2),
            "percentile_75": round(float(np.percentile(results, 75)), 2),
            "percentile_95": round(float(np.percentile(results, 95)), 2),
        },
        "risk": {
            "probability_of_ruin": round(ruin_count / n_simulations * 100, 2),
            "avg_max_drawdown": round(float(np.mean(max_drawdowns)), 2),
            "median_max_drawdown": round(float(np.median(max_drawdowns)), 2),
            "worst_drawdown": round(float(np.max(max_drawdowns)), 2),
            "probability_profitable": round(float(np.sum(results > initial_balance) / n_simulations * 100), 2),
        },
        "distribution": {
            "below_8000": round(float(np.sum(results < 8000) / n_simulations * 100), 2),
            "8000_to_10000": round(float(np.sum((results >= 8000) & (results < 10000)) / n_simulations * 100), 2),
            "10000_to_12000": round(float(np.sum((results >= 10000) & (results < 12000)) / n_simulations * 100), 2),
            "above_12000": round(float(np.sum(results >= 12000) / n_simulations * 100), 2),
        }
    }

# ====================================================================
# PHASE 4: ORDER FLOW, FUNDING RATES & WHALE TRACKING
# ====================================================================

# --- 1. ORDER FLOW ANALYSIS ---
async def analyze_order_book(symbol, limit=100):
    """Analyze order book depth for bid/ask imbalance, support/resistance walls."""
    price = SYMBOL_PRICES.get(symbol, 0)
    
    if binance_client:
        try:
            book = await binance_client.get_order_book(symbol=symbol, limit=limit)
            bids = [(float(b[0]), float(b[1])) for b in book["bids"]]
            asks = [(float(a[0]), float(a[1])) for a in book["asks"]]
        except Exception as e:
            logger.warning(f"Failed to fetch order book for {symbol}: {e}")
            bids, asks = _simulate_order_book(price, limit)
    else:
        bids, asks = _simulate_order_book(price, limit)
    
    # Total volume at each side
    total_bid_vol = sum(qty for _, qty in bids)
    total_ask_vol = sum(qty for _, qty in asks)
    
    # Imbalance ratio: >1 = more buying pressure, <1 = more selling pressure
    imbalance = total_bid_vol / total_ask_vol if total_ask_vol > 0 else 1.0
    
    # Find walls (large orders > 3x average)
    avg_bid_size = total_bid_vol / len(bids) if bids else 1
    avg_ask_size = total_ask_vol / len(asks) if asks else 1
    
    bid_walls = [{"price": p, "quantity": q, "usdt_value": round(p * q, 2)} for p, q in bids if q > avg_bid_size * 3][:5]
    ask_walls = [{"price": p, "quantity": q, "usdt_value": round(p * q, 2)} for p, q in asks if q > avg_ask_size * 3][:5]
    
    # Depth levels (cumulative volume at %, +/-0.5%, 1%, 2%, 5%)
    depth_levels = {}
    for pct in [0.5, 1.0, 2.0, 5.0]:
        bid_depth = sum(q for p, q in bids if p >= price * (1 - pct / 100))
        ask_depth = sum(q for p, q in asks if p <= price * (1 + pct / 100))
        depth_levels[f"{pct}%"] = {
            "bid_volume": round(bid_depth, 4),
            "ask_volume": round(ask_depth, 4),
            "bid_usdt": round(bid_depth * price, 2),
            "ask_usdt": round(ask_depth * price, 2),
            "ratio": round(bid_depth / ask_depth, 4) if ask_depth > 0 else 0,
        }
    
    # Pressure signal
    if imbalance > 1.5:
        pressure = "STRONG_BUY"
    elif imbalance > 1.1:
        pressure = "BUY"
    elif imbalance < 0.67:
        pressure = "STRONG_SELL"
    elif imbalance < 0.9:
        pressure = "SELL"
    else:
        pressure = "NEUTRAL"
    
    # Top bids/asks for visualization
    top_bids = [{"price": round(p, 8), "quantity": round(q, 8), "total": round(p * q, 2)} for p, q in bids[:20]]
    top_asks = [{"price": round(p, 8), "quantity": round(q, 8), "total": round(p * q, 2)} for p, q in asks[:20]]
    
    return {
        "symbol": symbol,
        "price": price,
        "total_bid_volume": round(total_bid_vol, 4),
        "total_ask_volume": round(total_ask_vol, 4),
        "imbalance_ratio": round(imbalance, 4),
        "pressure": pressure,
        "bid_walls": bid_walls,
        "ask_walls": ask_walls,
        "depth_levels": depth_levels,
        "top_bids": top_bids,
        "top_asks": top_asks,
        "source": "binance" if binance_client else "simulated",
    }

def _simulate_order_book(price, limit=100):
    """Generate realistic simulated order book data."""
    if price <= 0:
        price = 100
    spread = price * 0.0005  # 0.05% spread
    bids, asks = [], []
    for i in range(limit):
        bid_price = price - spread * (i + 1) * random.uniform(0.8, 1.2)
        ask_price = price + spread * (i + 1) * random.uniform(0.8, 1.2)
        # Larger orders further from price, occasional walls
        base_qty = random.uniform(0.01, 1.0) * (50000 / price)
        wall_mult = random.choice([1, 1, 1, 1, 1, 3, 5]) if random.random() < 0.15 else 1
        bid_qty = base_qty * (1 + i * 0.05) * wall_mult
        ask_qty = base_qty * (1 + i * 0.05) * (random.choice([1, 1, 1, 1, 3, 5]) if random.random() < 0.15 else 1)
        bids.append((round(bid_price, 8), round(bid_qty, 8)))
        asks.append((round(ask_price, 8), round(ask_qty, 8)))
    return bids, asks

# --- 2. FUNDING RATE ANALYSIS ---
async def fetch_funding_rates(symbols):
    """Fetch funding rates from Binance Futures. In DRY mode, simulate."""
    results = {}
    
    for symbol in symbols:
        if binance_client:
            try:
                rates = await binance_client.futures_funding_rate(symbol=symbol, limit=10)
                if rates:
                    current_rate = float(rates[-1]["fundingRate"])
                    avg_rate = sum(float(r["fundingRate"]) for r in rates) / len(rates)
                    results[symbol] = {
                        "current_rate": round(current_rate * 100, 6),
                        "avg_rate_8h": round(avg_rate * 100, 6),
                        "source": "binance",
                    }
                    continue
            except Exception:
                pass
        
        # Simulate funding rate
        rate = random.gauss(0.01, 0.02)  # Typically 0.01% ± 0.02%
        results[symbol] = {
            "current_rate": round(rate, 6),
            "avg_rate_8h": round(rate + random.gauss(0, 0.005), 6),
            "source": "simulated",
        }
    
    # Add sentiment analysis
    for symbol, data in results.items():
        rate = data["current_rate"]
        if rate > 0.03:
            data["sentiment"] = "EXTREMELY_BULLISH"
            data["signal"] = "Longs are overleveraged — contrarian SHORT"
            data["arb_opportunity"] = True
        elif rate > 0.01:
            data["sentiment"] = "BULLISH"
            data["signal"] = "Moderate long bias"
            data["arb_opportunity"] = False
        elif rate < -0.03:
            data["sentiment"] = "EXTREMELY_BEARISH"
            data["signal"] = "Shorts are overleveraged — contrarian LONG"
            data["arb_opportunity"] = True
        elif rate < -0.01:
            data["sentiment"] = "BEARISH"
            data["signal"] = "Moderate short bias"
            data["arb_opportunity"] = False
        else:
            data["sentiment"] = "NEUTRAL"
            data["signal"] = "No strong directional bias"
            data["arb_opportunity"] = False
        
        # Annualized yield from funding
        data["annualized_yield"] = round(abs(rate) * 3 * 365, 4)  # 3x per day * 365
    
    return results

# --- 3. WHALE ACTIVITY TRACKING ---
async def track_whale_activity(symbols, min_trade_usdt=50000):
    """Track large trades (whale activity) from recent aggregated trades."""
    whale_trades = []
    
    for symbol in symbols[:4]:  # Limit to avoid rate limits
        price = SYMBOL_PRICES.get(symbol, 0)
        
        if binance_client and price > 0:
            try:
                agg_trades = await binance_client.get_aggregate_trades(symbol=symbol, limit=100)
                for t in agg_trades:
                    qty = float(t["q"])
                    trade_price = float(t["p"])
                    usdt_value = qty * trade_price
                    if usdt_value >= min_trade_usdt:
                        whale_trades.append({
                            "symbol": symbol,
                            "price": trade_price,
                            "quantity": qty,
                            "usdt_value": round(usdt_value, 2),
                            "side": "SELL" if t["m"] else "BUY",
                            "time": datetime.fromtimestamp(t["T"] / 1000, tz=timezone.utc).isoformat(),
                            "source": "binance",
                        })
                continue
            except Exception:
                pass
        
        # Simulate whale trades
        for _ in range(random.randint(1, 4)):
            if price <= 0:
                price = 100
            qty = random.uniform(50000, 500000) / price
            whale_trades.append({
                "symbol": symbol,
                "price": round(price * random.uniform(0.998, 1.002), 8),
                "quantity": round(qty, 8),
                "usdt_value": round(qty * price, 2),
                "side": random.choice(["BUY", "SELL"]),
                "time": (datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 60))).isoformat(),
                "source": "simulated",
            })
    
    # Sort by USDT value descending
    whale_trades.sort(key=lambda x: -x["usdt_value"])
    
    # Aggregate stats
    total_buy = sum(t["usdt_value"] for t in whale_trades if t["side"] == "BUY")
    total_sell = sum(t["usdt_value"] for t in whale_trades if t["side"] == "SELL")
    buy_count = sum(1 for t in whale_trades if t["side"] == "BUY")
    sell_count = sum(1 for t in whale_trades if t["side"] == "SELL")
    
    net_flow = total_buy - total_sell
    if net_flow > 100000:
        whale_signal = "ACCUMULATION"
    elif net_flow < -100000:
        whale_signal = "DISTRIBUTION"
    else:
        whale_signal = "NEUTRAL"
    
    # Per-symbol breakdown
    symbol_breakdown = {}
    for t in whale_trades:
        s = t["symbol"]
        if s not in symbol_breakdown:
            symbol_breakdown[s] = {"buy_volume": 0, "sell_volume": 0, "count": 0}
        if t["side"] == "BUY":
            symbol_breakdown[s]["buy_volume"] += t["usdt_value"]
        else:
            symbol_breakdown[s]["sell_volume"] += t["usdt_value"]
        symbol_breakdown[s]["count"] += 1
    
    for s in symbol_breakdown:
        b = symbol_breakdown[s]
        b["buy_volume"] = round(b["buy_volume"], 2)
        b["sell_volume"] = round(b["sell_volume"], 2)
        b["net_flow"] = round(b["buy_volume"] - b["sell_volume"], 2)
        b["signal"] = "ACCUMULATION" if b["net_flow"] > 10000 else ("DISTRIBUTION" if b["net_flow"] < -10000 else "NEUTRAL")
    
    return {
        "whale_trades": whale_trades[:20],  # Top 20
        "total_whale_buys": round(total_buy, 2),
        "total_whale_sells": round(total_sell, 2),
        "net_flow": round(net_flow, 2),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "whale_signal": whale_signal,
        "min_trade_usdt": min_trade_usdt,
        "symbol_breakdown": symbol_breakdown,
    }

def calculate_signal(symbol, candles=None, allow_short=False):
    if candles is None:
        candles = generate_candles(symbol, 60)
    closes = [c['close'] for c in candles]
    current_price = closes[-1]
    
    fast_ema = ema(closes, 5)
    slow_ema = ema(closes, 13)
    rsi = rsi_calc(closes)
    macd = macd_calc(closes)
    bb = bollinger_bands(closes)
    atr = atr_calc(candles)
    
    if not all([fast_ema, slow_ema, rsi, macd, bb, atr]):
        return None
    
    # Volume filter
    vol_passes, vol_ratio = volume_filter(candles, multiplier=1.2)
    
    # Volatility regime detection
    regime, vol_percentile, regime_size_mult = volatility_regime(candles)
    
    # Structure check
    structure_candles = candles[-10:-2]
    if len(structure_candles) >= 2:
        if structure_candles[-1]['high'] > structure_candles[-2]['high'] and structure_candles[-1]['low'] > structure_candles[-2]['low']:
            trend = 'UPTREND'
        elif structure_candles[-1]['high'] < structure_candles[-2]['high'] and structure_candles[-1]['low'] < structure_candles[-2]['low']:
            trend = 'DOWNTREND'
        else:
            trend = 'RANGE'
    else:
        trend = 'RANGE'
    
    # Sweep check
    sweep_signal = None
    if candles[-1]['low'] < candles[-2]['low'] and candles[-1]['close'] > candles[-2]['low']:
        sweep_signal = 'BUY_SWEEP'
    elif candles[-1]['high'] > candles[-2]['high'] and candles[-1]['close'] < candles[-2]['high']:
        sweep_signal = 'SELL_SWEEP'
    elif fast_ema > slow_ema:
        sweep_signal = 'EMA_BULLISH'
    elif fast_ema < slow_ema:
        sweep_signal = 'EMA_BEARISH'
    
    # --- Determine signal side ---
    side = None
    
    # LONG signals
    has_buy_signal = (
        (trend == 'UPTREND' and sweep_signal in ['BUY_SWEEP', 'EMA_BULLISH']) or
        (trend != 'DOWNTREND' and sweep_signal == 'BUY_SWEEP') or
        (fast_ema > slow_ema and rsi < 60 and rsi > 35)
    )
    if has_buy_signal and rsi <= 70:
        side = 'LONG'
    
    # SHORT signals (only if allowed and no LONG signal)
    if side is None and allow_short:
        has_sell_signal = (
            (trend == 'DOWNTREND' and sweep_signal in ['SELL_SWEEP', 'EMA_BEARISH']) or
            (trend != 'UPTREND' and sweep_signal == 'SELL_SWEEP') or
            (fast_ema < slow_ema and rsi > 40 and rsi < 65)
        )
        if has_sell_signal and rsi >= 30:
            side = 'SHORT'
    
    if side is None:
        return None
    
    # Probability scoring
    bb_pos = (current_price - bb['middle']) / (bb['upper'] - bb['middle']) if bb['upper'] != bb['middle'] else 0
    momentum = (fast_ema - slow_ema) / current_price * 100
    vol_bonus = min(0.15, (vol_ratio - 1) * 0.1) if vol_passes else -0.1
    regime_penalty = -0.1 if regime == 'HIGH_VOL' else (0.05 if regime == 'NORMAL' else -0.05)
    
    scores = []
    if side == 'LONG':
        scores.append(1.0 if trend == 'UPTREND' else (0.5 if trend == 'RANGE' else 0.0))
        scores.append(max(0, min(1, 0.5 + momentum * 5)))
        scores.append(max(0, min(1, (60 - rsi) / 30)) if rsi < 60 else 0)
        scores.append(1.0 if sweep_signal == 'BUY_SWEEP' else (0.6 if sweep_signal == 'EMA_BULLISH' else 0.0))
        scores.append(max(0, min(1, 0.5 - bb_pos * 0.5)))
    else:  # SHORT
        scores.append(1.0 if trend == 'DOWNTREND' else (0.5 if trend == 'RANGE' else 0.0))
        scores.append(max(0, min(1, 0.5 - momentum * 5)))  # negative momentum is good for shorts
        scores.append(max(0, min(1, (rsi - 40) / 30)) if rsi > 40 else 0)
        scores.append(1.0 if sweep_signal == 'SELL_SWEEP' else (0.6 if sweep_signal == 'EMA_BEARISH' else 0.0))
        scores.append(max(0, min(1, 0.5 + bb_pos * 0.5)))  # higher BB = better for short
    
    scores.append(max(0, min(1, vol_bonus + 0.5)))
    scores.append(max(0, min(1, 0.5 + regime_penalty)))
    
    weights = [0.22, 0.18, 0.15, 0.15, 0.10, 0.10, 0.10]
    raw_score = sum(s * w for s, w in zip(scores, weights))
    prob = 0.25 + raw_score * 0.67
    
    # SL/TP based on side — enforce minimum R:R of 2.5
    if side == 'LONG':
        struct_sl = structure_stop_loss(candles, 'LONG', atr)
        sl_distance = atr * 1.2
        sl = max(struct_sl, current_price - sl_distance) if struct_sl else current_price - sl_distance
        tp = current_price + atr * 3.2  # 3.2 ATR reward for 1.2 ATR risk = 2.67 R:R
    else:  # SHORT
        highs = [c['high'] for c in candles[-10:]]
        swing_high = max(highs)
        sl = swing_high + (atr * 0.3) if atr else swing_high * 1.002
        sl = max(sl, current_price + atr * 1.2)  # at least 1.2 ATR above
        tp = current_price - atr * 3.2
        tp = max(tp, current_price * 0.5)  # safety floor
    
    return {
        "symbol": symbol,
        "side": side,
        "price": current_price,
        "probability": prob,
        "rsi": rsi,
        "macd": macd,
        "bb": bb,
        "atr": atr,
        "trend": trend,
        "sl": sl,
        "tp": tp,
        "volume_ratio": vol_ratio,
        "volume_passes": vol_passes,
        "volatility_regime": regime,
        "volatility_percentile": vol_percentile,
        "regime_size_multiplier": regime_size_mult,
        "indicators": {
            "ema_fast": fast_ema,
            "ema_slow": slow_ema,
            "rsi": round(rsi, 2),
            "macd_value": round(macd['macd'], 6),
            "macd_signal": round(macd['signal'], 6),
            "macd_histogram": round(macd['histogram'], 6),
            "bb_upper": round(bb['upper'], 6),
            "bb_middle": round(bb['middle'], 6),
            "bb_lower": round(bb['lower'], 6),
            "atr": round(atr, 6),
            "volume_ratio": vol_ratio,
            "vol_regime": regime,
            "vol_percentile": vol_percentile
        }
    }

# ====================================================================
# BOT BACKGROUND TASK
# ====================================================================

async def bot_scan_loop():
    """Main bot scan loop - runs as background task. Supports DRY and LIVE modes."""
    logger.info("Bot scan loop started")
    
    while bot_state["running"]:
        if bot_state["paused"]:
            await asyncio.sleep(5)
            continue
        
        try:
            config = await db.bot_config.find_one({"active": True}, {"_id": 0})
            if not config:
                config = await get_default_config()
            
            # Sync mode from config
            current_mode = config.get("mode", "DRY")
            bot_state["mode"] = current_mode
            is_live = current_mode == "LIVE" and binance_client is not None
            
            symbols = config.get("symbols", ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT'])
            min_prob = config.get("min_entry_probability", 0.65)
            base_usdt = config.get("base_usdt_per_trade", 50)
            allow_short = config.get("allow_short", False)
            
            # --- Update prices ---
            if is_live:
                for symbol in symbols:
                    try:
                        live_price = await fetch_live_price(symbol)
                        SYMBOL_PRICES[symbol] = live_price
                    except Exception as e:
                        logger.warning(f"Failed to fetch live price for {symbol}: {e}")
            else:
                for symbol in symbols:
                    if symbol in SYMBOL_PRICES:
                        change = random.gauss(0, SYMBOL_PRICES[symbol] * 0.001)
                        SYMBOL_PRICES[symbol] = round(max(0.01, SYMBOL_PRICES[symbol] + change), 8)
            
            # --- Check existing positions ---
            positions = await db.positions.find({"status": "OPEN"}, {"_id": 0}).to_list(100)
            for pos in positions:
                symbol = pos["symbol"]
                pos_side = pos.get("side", "LONG")
                current_price = SYMBOL_PRICES.get(symbol, pos["entry_price"])
                
                exit_reason = None
                exit_price = current_price
                
                if pos_side == "LONG":
                    if current_price <= pos["stop_loss"]:
                        exit_reason = "STOP_LOSS"
                        exit_price = pos["stop_loss"]
                    elif current_price >= pos["take_profit"]:
                        exit_reason = "TAKE_PROFIT"
                        exit_price = pos["take_profit"]
                else:  # SHORT
                    if current_price >= pos["stop_loss"]:
                        exit_reason = "STOP_LOSS"
                        exit_price = pos["stop_loss"]
                    elif current_price <= pos["take_profit"]:
                        exit_reason = "TAKE_PROFIT"
                        exit_price = pos["take_profit"]
                
                # Trailing stop check
                if not exit_reason and pos.get("trail_activated"):
                    trail_distance = pos["atr"] * config.get("trailing_stop_distance_pips", 1.2)
                    if pos_side == "LONG":
                        new_sl = current_price - trail_distance
                        if new_sl > pos["stop_loss"]:
                            await db.positions.update_one({"id": pos["id"]}, {"$set": {"stop_loss": round(new_sl, 8)}})
                        if current_price <= pos["stop_loss"]:
                            exit_reason = "TRAIL_STOP"
                            exit_price = pos["stop_loss"]
                    else:  # SHORT trailing — stop moves down
                        new_sl = current_price + trail_distance
                        if new_sl < pos["stop_loss"]:
                            await db.positions.update_one({"id": pos["id"]}, {"$set": {"stop_loss": round(new_sl, 8)}})
                        if current_price >= pos["stop_loss"]:
                            exit_reason = "TRAIL_STOP"
                            exit_price = pos["stop_loss"]
                
                # Activate trailing
                if not exit_reason and not pos.get("trail_activated"):
                    activation_atr = pos["atr"] * config.get("trailing_stop_activate_pips", 2.4)
                    if pos_side == "LONG":
                        if current_price >= pos["entry_price"] + activation_atr:
                            await db.positions.update_one({"id": pos["id"]}, {"$set": {"trail_activated": True}})
                    else:  # SHORT
                        if current_price <= pos["entry_price"] - activation_atr:
                            await db.positions.update_one({"id": pos["id"]}, {"$set": {"trail_activated": True}})
                
                # Close position
                if exit_reason:
                    # In LIVE mode, close the real position
                    if is_live and pos.get("mode") == "LIVE":
                        try:
                            close_side = "SELL" if pos_side == "LONG" else "BUY"
                            close_result = await place_live_market_order(symbol, close_side, pos["quantity"] * exit_price)
                            exit_price = close_result.get("avg_price", exit_price)
                            logger.info(f"LIVE {close_side} {symbol}: order {close_result['order_id']}, filled {close_result['executed_qty']}")
                        except Exception as e:
                            logger.error(f"LIVE close failed for {symbol}, using market price: {e}")
                    
                    # PnL calculation — side-aware
                    if pos_side == "LONG":
                        pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
                        pnl_percent = ((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100
                    else:  # SHORT
                        pnl = (pos["entry_price"] - exit_price) * pos["quantity"]
                        pnl_percent = ((pos["entry_price"] - exit_price) / pos["entry_price"]) * 100
                    
                    now = datetime.now(timezone.utc).isoformat()
                    await db.positions.update_one(
                        {"id": pos["id"]},
                        {"$set": {"status": "CLOSED", "exit_price": round(exit_price, 8), "exit_reason": exit_reason, "pnl": round(pnl, 4), "pnl_percent": round(pnl_percent, 4), "closed_at": now}}
                    )
                    
                    trade_doc = {
                        "id": str(uuid.uuid4()),
                        "symbol": symbol,
                        "side": pos_side,
                        "entry_price": pos["entry_price"],
                        "exit_price": round(exit_price, 8),
                        "quantity": pos["quantity"],
                        "pnl": round(pnl, 4),
                        "pnl_percent": round(pnl_percent, 4),
                        "exit_reason": exit_reason,
                        "opened_at": pos["opened_at"],
                        "closed_at": now,
                        "mode": pos.get("mode", "DRY"),
                        "stop_loss": pos["stop_loss"],
                        "take_profit": pos["take_profit"]
                    }
                    await db.trades.insert_one(trade_doc)
                    
                    await db.bot_state.update_one(
                        {"key": "daily_pnl"},
                        {"$inc": {"value": round(pnl, 4)}},
                        upsert=True
                    )
                    
                    logger.info(f"[{pos.get('mode','DRY')}] Closed {symbol} via {exit_reason}: PnL {pnl:.4f} USDT")
                    
                    # Update cooldown state & dataset outcome
                    update_cooldown(pnl < 0)
                    await update_dataset_outcome(db, symbol, pos_side, pos["entry_price"], round(pnl, 4), round(pnl_percent, 4), exit_reason, pos["opened_at"])
                else:
                    # Update unrealized PnL — side-aware
                    if pos_side == "LONG":
                        unrealized = (current_price - pos["entry_price"]) * pos["quantity"]
                        unrealized_pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
                    else:  # SHORT
                        unrealized = (pos["entry_price"] - current_price) * pos["quantity"]
                        unrealized_pct = ((pos["entry_price"] - current_price) / pos["entry_price"]) * 100
                    await db.positions.update_one(
                        {"id": pos["id"]},
                        {"$set": {"current_price": round(current_price, 8), "unrealized_pnl": round(unrealized, 4), "unrealized_pnl_percent": round(unrealized_pct, 4)}}
                    )
            
            # --- Increment cooldown counter ---
            increment_cooldown()
            
            # --- Circuit Breaker Check ---
            cb_ok, current_dd = await check_circuit_breaker(db, config)
            if not cb_ok:
                if bot_state["scan_count"] % 30 == 0:
                    logger.warning(f"Circuit breaker active: {current_dd}% drawdown. Bot paused.")
                await asyncio.sleep(10)
                continue
            
            # --- Look for new entries (with smart filters) ---
            open_count = await db.positions.count_documents({"status": "OPEN"})
            if open_count < 3:
                # Gate 0a: Session check
                session_ok, active_session = check_trading_session(config)
                if not session_ok:
                    if bot_state["scan_count"] % 30 == 0:
                        logger.info(f"Outside trading session (current: {active_session})")
                elif True:  # Proceed with gates
                    # Gate 0b: Advanced market regime (applied per-scan, not per-symbol)
                    sample_symbol = symbols[0] if symbols else "BTCUSDT"
                    sample_candles = generate_candles(sample_symbol, 60) if not is_live else None
                    if is_live:
                        try:
                            sample_candles = await fetch_live_candles(sample_symbol, interval="3m", limit=60)
                        except Exception:
                            sample_candles = generate_candles(sample_symbol, 60)
                    adv_regime, regime_strength, regime_details = detect_market_regime_advanced(sample_candles)
                    
                    # Skip trading in highly volatile regimes unless confidence is very high
                    if adv_regime == "VOLATILE" and regime_strength > 0.8:
                        if bot_state["scan_count"] % 10 == 0:
                            logger.info(f"Market too volatile ({regime_strength:.2f}). Waiting for calmer conditions.")
                    else:
                        # Gate 1: Overtrade limits
                        ot_ok, trades_hr, max_hr, trades_day, max_day = await check_overtrade_limits(db, config)
                        if not ot_ok:
                            if bot_state["scan_count"] % 30 == 0:
                                logger.info(f"Overtrade limit: {trades_hr}/{max_hr} per hour, {trades_day}/{max_day} per day")
                else:
                    # Gate 2: Cooldown check
                    cd_ok, cd_scans, cd_required = check_cooldown(config)
                    if not cd_ok:
                        if bot_state["scan_count"] % 10 == 0:
                            logger.info(f"Cooldown active: {cd_scans}/{cd_required} scans since last loss")
                    else:
                        for symbol in symbols:
                            if await db.positions.find_one({"symbol": symbol, "status": "OPEN"}):
                                continue
                            
                            # Gate 3: Correlation exposure
                            can_open, corr_info = await check_correlation_exposure(symbol, db)
                            if not can_open:
                                continue
                            
                            # Get candles (live or simulated)
                            candles_for_signal = None
                            if is_live:
                                try:
                                    candles_for_signal = await fetch_live_candles(symbol, interval="3m", limit=60)
                                except Exception as e:
                                    logger.warning(f"Failed to fetch live candles for {symbol}: {e}")
                            
                            signal = calculate_signal(symbol, candles_for_signal, allow_short=allow_short)
                            if not signal:
                                continue
                            
                            # Use candles from signal generation for filters
                            candles_used = candles_for_signal if candles_for_signal else generate_candles(symbol, 60)
                            signal_side = signal.get("side", "LONG")
                            filters_passed = {}
                            all_pass = True
                            
                            # Gate 4: Technical probability
                            if signal["probability"] < min_prob:
                                filters_passed["min_probability"] = False
                                all_pass = False
                            else:
                                filters_passed["min_probability"] = True
                            
                            # Gate 5: Volume filter
                            if not signal.get("volume_passes", True):
                                filters_passed["volume"] = False
                                all_pass = False
                            else:
                                filters_passed["volume"] = True
                            
                            # Gate 6: Spread check
                            spread_ok, spread_pct = check_spread(candles_used, config.get("spread_max_percent", 0.15))
                            filters_passed["spread"] = spread_ok
                            if not spread_ok:
                                all_pass = False
                            
                            # Gate 7: Slippage protection
                            regime_mult = signal.get("regime_size_multiplier", 1.0)
                            adjusted_usdt = base_usdt * regime_mult
                            slip_ok, slip_pct = estimate_slippage(candles_used, adjusted_usdt, config.get("max_slippage_percent", 0.1))
                            filters_passed["slippage"] = slip_ok
                            if not slip_ok:
                                all_pass = False
                            
                            # Gate 8: Minimum liquidity
                            liq_ok, est_vol = check_min_liquidity(candles_used, config.get("min_24h_volume_usdt", 1_000_000))
                            filters_passed["liquidity"] = liq_ok
                            if not liq_ok:
                                all_pass = False
                            
                            # Gate 9: Risk/reward ratio
                            rr_ok, rr_ratio = check_risk_reward(
                                signal["price"], signal["sl"], signal["tp"], signal_side,
                                config.get("min_risk_reward_ratio", 2.5)
                            )
                            filters_passed["risk_reward"] = rr_ok
                            if not rr_ok:
                                all_pass = False
                            
                            # Gate 10: Multi-timeframe trend alignment
                            if config.get("require_trend_alignment", True):
                                trend_ok, htf_trend = multi_timeframe_trend(candles_used, signal_side)
                                filters_passed["trend_alignment"] = trend_ok
                                if not trend_ok:
                                    all_pass = False
                            else:
                                filters_passed["trend_alignment"] = True
                            
                            # Gate 11: Confidence score
                            confidence, conf_breakdown = calculate_confidence_score(signal, candles_used, config)
                            min_conf = config.get("min_confidence_score", 0.60)
                            filters_passed["confidence"] = confidence >= min_conf
                            if confidence < min_conf:
                                all_pass = False
                            
                            # Gate 12: ML Signal Filter
                            ml_win_prob, ml_prediction = None, None
                            if ml_model_state["status"] == "ACTIVE":
                                # Build a doc-like dict for ML prediction
                                ml_doc = {
                                    "rsi": signal["indicators"]["rsi"],
                                    "macd_value": signal["indicators"]["macd_value"],
                                    "macd_signal": signal["indicators"]["macd_signal"],
                                    "macd_histogram": signal["indicators"]["macd_histogram"],
                                    "ema_slope": round(((signal["indicators"]["ema_fast"] - signal["indicators"]["ema_slow"]) / signal["price"] * 100), 6) if signal["price"] > 0 else 0,
                                    "atr_percent": round(signal["atr"] / signal["price"] * 100, 4) if signal["price"] > 0 else 0,
                                    "volume_ratio": signal.get("volume_ratio", 0),
                                    "volatility_percentile": signal.get("volatility_percentile", 0),
                                    "body_ratio": abs(candles_used[-1]["close"] - candles_used[-1]["open"]) / max(candles_used[-1]["high"] - candles_used[-1]["low"], 0.0001),
                                    "upper_wick_ratio": (candles_used[-1]["high"] - max(candles_used[-1]["close"], candles_used[-1]["open"])) / max(candles_used[-1]["high"] - candles_used[-1]["low"], 0.0001),
                                    "lower_wick_ratio": (min(candles_used[-1]["close"], candles_used[-1]["open"]) - candles_used[-1]["low"]) / max(candles_used[-1]["high"] - candles_used[-1]["low"], 0.0001),
                                    "pct_change_5": round(([c["close"] for c in candles_used][-1] - [c["close"] for c in candles_used][-5]) / [c["close"] for c in candles_used][-5] * 100, 4) if len(candles_used) >= 5 else 0,
                                    "pct_change_20": round(([c["close"] for c in candles_used][-1] - [c["close"] for c in candles_used][-20]) / [c["close"] for c in candles_used][-20] * 100, 4) if len(candles_used) >= 20 else 0,
                                    "technical_probability": signal["probability"],
                                    "confidence_score": confidence,
                                    "rr_ratio": conf_breakdown.get("rr_ratio", 0),
                                    "side": signal_side,
                                    "volatility_regime": signal.get("volatility_regime", "NORMAL"),
                                    "trend": signal.get("trend", "RANGE"),
                                    "volume_passes": signal.get("volume_passes", False),
                                }
                                ml_win_prob, ml_prediction = ml_predict(ml_doc)
                                if ml_win_prob is not None:
                                    ml_threshold = config.get("ml_min_win_probability", 0.55)
                                    filters_passed["ml_filter"] = ml_win_prob >= ml_threshold
                                    if ml_win_prob < ml_threshold:
                                        all_pass = False
                                else:
                                    filters_passed["ml_filter"] = True  # Pass if prediction failed
                            else:
                                filters_passed["ml_filter"] = True  # Pass-through in LEARNING mode
                            
                            # Log signal to dataset (always — for ML training)
                            await log_signal_to_dataset(db, signal, candles_used, confidence, conf_breakdown, filters_passed, all_pass, config)
                            
                            if not all_pass:
                                failed = [k for k, v in filters_passed.items() if not v]
                                if bot_state["scan_count"] % 5 == 0:  # Throttled logging
                                    ml_info = f" ml={ml_win_prob:.3f}" if ml_win_prob else ""
                                    logger.info(f"Signal rejected {symbol} {signal_side}: failed [{', '.join(failed)}] conf={confidence:.3f}{ml_info}")
                                continue
                            
                            # ALL FILTERS PASSED (12 gates) — OPEN POSITION
                            quantity = round(adjusted_usdt / signal["price"], 8)
                            entry_price = signal["price"]
                            
                            # In LIVE mode, place real order
                            if is_live:
                                try:
                                    order_side = "BUY" if signal_side == "LONG" else "SELL"
                                    result = await place_live_market_order(symbol, order_side, adjusted_usdt)
                                    quantity = result["executed_qty"]
                                    entry_price = result["avg_price"]
                                    logger.info(f"LIVE {order_side} {symbol}: order {result['order_id']}, filled {quantity} @ {entry_price}")
                                except Exception as e:
                                    logger.error(f"LIVE {signal_side} order failed for {symbol}: {e}")
                                    continue
                            
                            now = datetime.now(timezone.utc).isoformat()
                            position_doc = {
                                "id": str(uuid.uuid4()),
                                "symbol": symbol,
                                "side": signal_side,
                                "entry_price": round(entry_price, 8),
                                "current_price": round(entry_price, 8),
                                "stop_loss": round(signal["sl"], 8),
                                "take_profit": round(signal["tp"], 8),
                                "quantity": quantity,
                                "atr": round(signal["atr"], 8),
                                "probability": round(signal["probability"], 4),
                                "confidence_score": confidence,
                                "status": "OPEN",
                                "trail_activated": False,
                                "unrealized_pnl": 0.0,
                                "unrealized_pnl_percent": 0.0,
                                "opened_at": now,
                                "mode": current_mode,
                                "indicators": signal["indicators"],
                                "volume_ratio": signal.get("volume_ratio", 0),
                                "volatility_regime": signal.get("volatility_regime", "NORMAL"),
                                "correlation_group": corr_info["group"],
                                "filters_passed": filters_passed,
                                "confidence_breakdown": conf_breakdown,
                                "ml_win_probability": ml_win_prob,
                                "ml_prediction": ml_prediction,
                                "market_regime": adv_regime,
                                "regime_strength": regime_strength,
                                "session": active_session,
                            }
                            await db.positions.insert_one(position_doc)
                            logger.info(f"[{current_mode}] Opened {signal_side} {symbol} @ {entry_price:.8f}, Conf: {confidence:.3f}, R:R: {conf_breakdown['rr_ratio']}")
                            break
            
            bot_state["scan_count"] += 1
            bot_state["last_scan"] = datetime.now(timezone.utc).isoformat()
            
            # Save price snapshot for charts (throttled: every 3rd scan)
            if bot_state["scan_count"] % 3 == 0:
                price_snapshot = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "prices": {s: SYMBOL_PRICES.get(s, 0) for s in symbols}
                }
                await db.price_history.insert_one(price_snapshot)
                
                cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                await db.price_history.delete_many({"timestamp": {"$lt": cutoff}})
            
        except Exception as e:
            logger.error(f"Bot scan error: {e}")
        
        await asyncio.sleep(10)
    
    logger.info("Bot scan loop stopped")

async def get_default_config():
    config = {
        "active": True,
        "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"],
        "base_usdt_per_trade": 50.0,
        "risk_per_trade_percent": 0.5,
        "max_daily_loss_usdt": 20.0,
        "max_total_drawdown_percent": 5.0,
        "rsi_period": 14,
        "rsi_overbought": 70.0,
        "rsi_oversold": 30.0,
        "min_entry_probability": 0.65,
        "trailing_stop_activate_pips": 2.4,
        "trailing_stop_distance_pips": 1.2,
        "mode": "DRY",
        "allow_short": False,
        # Phase 1: Smart filters
        "max_trades_per_hour": 5,
        "max_trades_per_day": 15,
        "min_risk_reward_ratio": 2.5,
        "cooldown_after_loss_scans": 6,
        "min_confidence_score": 0.60,
        "spread_max_percent": 0.15,
        "min_24h_volume_usdt": 1000000,
        "max_slippage_percent": 0.1,
        "require_trend_alignment": True,
        "ml_min_win_probability": 0.55,
        "allowed_sessions": ["ASIA", "LONDON", "NYC"],
        "telegram_token": "",
        "telegram_chat_id": ""
    }
    await db.bot_config.update_one({"active": True}, {"$set": config}, upsert=True)
    return config

bot_task = None

async def start_bot():
    global bot_task
    if bot_state["running"]:
        return
    bot_state["running"] = True
    bot_state["paused"] = False
    bot_state["started_at"] = datetime.now(timezone.utc).isoformat()
    bot_task = asyncio.create_task(bot_scan_loop())
    logger.info("Bot started")

async def stop_bot():
    global bot_task
    bot_state["running"] = False
    if bot_task:
        bot_task.cancel()
        bot_task = None
    logger.info("Bot stopped")

# ====================================================================
# BOT API ROUTES
# ====================================================================

@api_router.get("/bot/status")
async def get_bot_status(user=Depends(get_current_user)):
    open_positions = await db.positions.count_documents({"status": "OPEN"})
    total_trades = await db.trades.count_documents({})
    
    daily_pnl_doc = await db.bot_state.find_one({"key": "daily_pnl"}, {"_id": 0})
    daily_pnl = daily_pnl_doc["value"] if daily_pnl_doc else 0.0
    
    return {
        "running": bot_state["running"],
        "paused": bot_state["paused"],
        "mode": bot_state["mode"],
        "started_at": bot_state["started_at"],
        "scan_count": bot_state["scan_count"],
        "last_scan": bot_state["last_scan"],
        "open_positions": open_positions,
        "total_trades": total_trades,
        "daily_pnl": daily_pnl
    }

@api_router.post("/bot/start")
async def start_bot_route(user=Depends(get_current_user)):
    await start_bot()
    return {"status": "started"}

@api_router.post("/bot/stop")
async def stop_bot_route(user=Depends(get_current_user)):
    await stop_bot()
    return {"status": "stopped"}

@api_router.post("/bot/pause")
async def pause_bot(user=Depends(get_current_user)):
    bot_state["paused"] = True
    return {"status": "paused"}

@api_router.post("/bot/resume")
async def resume_bot(user=Depends(get_current_user)):
    bot_state["paused"] = False
    return {"status": "resumed"}

@api_router.get("/bot/config")
async def get_bot_config(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    if not config:
        config = await get_default_config()
    config.pop("active", None)
    return config

@api_router.put("/bot/config")
async def update_bot_config(data: BotConfigUpdate, user=Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if update_data:
        await db.bot_config.update_one({"active": True}, {"$set": update_data}, upsert=True)
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    config.pop("active", None)
    return config

@api_router.put("/bot/telegram")
async def update_telegram_config(data: TelegramConfig, user=Depends(get_current_user)):
    await db.bot_config.update_one(
        {"active": True},
        {"$set": {"telegram_token": data.telegram_token, "telegram_chat_id": data.telegram_chat_id}},
        upsert=True
    )
    return {"status": "updated"}

@api_router.put("/bot/mode")
async def toggle_bot_mode(data: ModeToggle, user=Depends(get_current_user)):
    """Switch between DRY and LIVE trading modes."""
    mode = data.mode.upper()
    if mode not in ("DRY", "LIVE"):
        raise HTTPException(status_code=400, detail="Mode must be DRY or LIVE")
    
    if mode == "LIVE" and not binance_client:
        raise HTTPException(
            status_code=400,
            detail="Cannot switch to LIVE mode: Binance API keys not configured or client failed to initialize"
        )
    
    # Update config in DB
    await db.bot_config.update_one({"active": True}, {"$set": {"mode": mode}}, upsert=True)
    bot_state["mode"] = mode
    
    logger.info(f"Bot mode switched to {mode} by user {user.get('email', 'unknown')}")
    
    return {
        "mode": mode,
        "binance_connected": binance_client is not None,
        "message": f"Bot is now in {mode} mode" + (" — real trades will be executed!" if mode == "LIVE" else " — trades are simulated.")
    }

@api_router.get("/bot/mode")
async def get_bot_mode(user=Depends(get_current_user)):
    """Get current trading mode and Binance connection status."""
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    current_mode = config.get("mode", "DRY") if config else "DRY"
    return {
        "mode": current_mode,
        "binance_connected": binance_client is not None,
        "binance_keys_configured": bool(BINANCE_API_KEY and BINANCE_API_SECRET)
    }
# DASHBOARD API
# ====================================================================

@api_router.get("/dashboard")
async def get_dashboard(user=Depends(get_current_user)):
    # Account balance (simulated)
    balance_doc = await db.bot_state.find_one({"key": "account_balance"}, {"_id": 0})
    if not balance_doc:
        await db.bot_state.update_one({"key": "account_balance"}, {"$set": {"value": 10000.0}}, upsert=True)
        balance = 10000.0
    else:
        balance = balance_doc["value"]
    
    # Daily PnL
    daily_pnl_doc = await db.bot_state.find_one({"key": "daily_pnl"}, {"_id": 0})
    daily_pnl = daily_pnl_doc["value"] if daily_pnl_doc else 0.0
    
    # Open positions
    positions = await db.positions.find({"status": "OPEN"}, {"_id": 0}).to_list(20)
    
    # Recent trades
    trades = await db.trades.find({}, {"_id": 0}).sort("closed_at", -1).limit(10).to_list(10)
    
    # Win rate
    total_trades = await db.trades.count_documents({})
    winning_trades = await db.trades.count_documents({"pnl": {"$gt": 0}})
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    # Total PnL
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$pnl"}}}]
    total_pnl_result = await db.trades.aggregate(pipeline).to_list(1)
    total_pnl = total_pnl_result[0]["total"] if total_pnl_result else 0.0
    
    # Current prices
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    symbols = config.get("symbols", ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']) if config else ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']
    prices = {s: SYMBOL_PRICES.get(s, 0) for s in symbols}
    
    return {
        "balance": round(balance, 2),
        "daily_pnl": round(daily_pnl, 4),
        "total_pnl": round(total_pnl, 4),
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "open_positions_count": len(positions),
        "positions": positions,
        "recent_trades": trades,
        "prices": prices,
        "bot_status": {
            "running": bot_state["running"],
            "paused": bot_state["paused"],
            "mode": bot_state["mode"],
            "scan_count": bot_state["scan_count"],
            "last_scan": bot_state["last_scan"]
        }
    }

# ====================================================================
# POSITIONS API
# ====================================================================

@api_router.get("/positions")
async def get_positions(status: str = "OPEN", user=Depends(get_current_user)):
    query = {"status": status}
    positions = await db.positions.find(query, {"_id": 0}).sort("opened_at", -1).to_list(100)
    return positions

@api_router.post("/positions/{position_id}/close")
async def close_position(position_id: str, user=Depends(get_current_user)):
    pos = await db.positions.find_one({"id": position_id, "status": "OPEN"}, {"_id": 0})
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    
    current_price = SYMBOL_PRICES.get(pos["symbol"], pos["entry_price"])
    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
    pnl_percent = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
    now = datetime.now(timezone.utc).isoformat()
    
    await db.positions.update_one(
        {"id": position_id},
        {"$set": {"status": "CLOSED", "exit_price": round(current_price, 8), "exit_reason": "MANUAL", "pnl": round(pnl, 4), "pnl_percent": round(pnl_percent, 4), "closed_at": now}}
    )
    
    trade_doc = {
        "id": str(uuid.uuid4()),
        "symbol": pos["symbol"],
        "side": "LONG",
        "entry_price": pos["entry_price"],
        "exit_price": round(current_price, 8),
        "quantity": pos["quantity"],
        "pnl": round(pnl, 4),
        "pnl_percent": round(pnl_percent, 4),
        "exit_reason": "MANUAL",
        "opened_at": pos["opened_at"],
        "closed_at": now,
        "mode": "DRY",
        "stop_loss": pos["stop_loss"],
        "take_profit": pos["take_profit"]
    }
    await db.trades.insert_one(trade_doc)
    
    await db.bot_state.update_one(
        {"key": "daily_pnl"},
        {"$inc": {"value": round(pnl, 4)}},
        upsert=True
    )
    
    return {"status": "closed", "pnl": round(pnl, 4)}

# ====================================================================
# TRADES API
# ====================================================================

@api_router.get("/trades")
async def get_trades(limit: int = 50, skip: int = 0, symbol: Optional[str] = None, user=Depends(get_current_user)):
    query = {}
    if symbol:
        query["symbol"] = symbol
    trades = await db.trades.find(query, {"_id": 0}).sort("closed_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.trades.count_documents(query)
    return {"trades": trades, "total": total}

# ====================================================================
# PERFORMANCE API
# ====================================================================

@api_router.get("/performance")
async def get_performance(user=Depends(get_current_user)):
    trades = await db.trades.find({}, {"_id": 0}).sort("closed_at", 1).to_list(1000)
    
    # Calculate cumulative PnL over time
    cumulative_pnl = []
    running_pnl = 0
    for t in trades:
        running_pnl += t.get("pnl", 0)
        cumulative_pnl.append({
            "date": t.get("closed_at", ""),
            "pnl": round(running_pnl, 4),
            "trade_pnl": t.get("pnl", 0)
        })
    
    # Win/Loss stats
    total = len(trades)
    wins = len([t for t in trades if t.get("pnl", 0) > 0])
    losses = len([t for t in trades if t.get("pnl", 0) <= 0])
    
    # By symbol
    by_symbol = {}
    for t in trades:
        s = t["symbol"]
        if s not in by_symbol:
            by_symbol[s] = {"symbol": s, "trades": 0, "pnl": 0, "wins": 0, "losses": 0}
        by_symbol[s]["trades"] += 1
        by_symbol[s]["pnl"] += t.get("pnl", 0)
        if t.get("pnl", 0) > 0:
            by_symbol[s]["wins"] += 1
        else:
            by_symbol[s]["losses"] += 1
    
    # Average win/loss
    win_amounts = [t["pnl"] for t in trades if t.get("pnl", 0) > 0]
    loss_amounts = [t["pnl"] for t in trades if t.get("pnl", 0) <= 0]
    avg_win = sum(win_amounts) / len(win_amounts) if win_amounts else 0
    avg_loss = sum(loss_amounts) / len(loss_amounts) if loss_amounts else 0
    
    # Max drawdown
    peak = 0
    max_dd = 0
    running = 0
    for t in trades:
        running += t.get("pnl", 0)
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    
    return {
        "cumulative_pnl": cumulative_pnl,
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 2) if total > 0 else 0,
        "total_pnl": round(running_pnl, 4) if trades else 0,
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "max_drawdown": round(max_dd, 4),
        "by_symbol": list(by_symbol.values()),
        "profit_factor": round(abs(sum(win_amounts)) / abs(sum(loss_amounts)), 2) if loss_amounts and sum(loss_amounts) != 0 else 0
    }

# ====================================================================
# LEADERBOARD / PERFORMANCE RANKINGS API
# ====================================================================

@api_router.get("/leaderboard")
async def get_leaderboard(user=Depends(get_current_user)):
    trades = await db.trades.find({}, {"_id": 0}).sort("closed_at", 1).to_list(5000)
    
    if not trades:
        return {
            "symbol_rankings": [],
            "best_trades": [],
            "worst_trades": [],
            "streaks": {"current": 0, "current_type": "none", "best_win": 0, "worst_loss": 0},
            "time_analysis": {"best_hour": None, "worst_hour": None, "hourly_pnl": []},
            "exit_analysis": [],
            "weekly_pnl": [],
            "risk_reward_avg": 0,
            "total_fees_saved_dry": 0,
            "consistency_score": 0
        }
    
    # 1. Symbol Rankings (sorted by total PnL)
    by_symbol = {}
    for t in trades:
        s = t["symbol"]
        if s not in by_symbol:
            by_symbol[s] = {
                "symbol": s, "trades": 0, "pnl": 0, "wins": 0, "losses": 0,
                "best_trade": 0, "worst_trade": 0, "avg_pnl": 0,
                "avg_hold_time_min": 0, "total_hold_time": 0
            }
        by_symbol[s]["trades"] += 1
        pnl = t.get("pnl", 0)
        by_symbol[s]["pnl"] = round(by_symbol[s]["pnl"] + pnl, 4)
        if pnl > 0:
            by_symbol[s]["wins"] += 1
        else:
            by_symbol[s]["losses"] += 1
        if pnl > by_symbol[s]["best_trade"]:
            by_symbol[s]["best_trade"] = round(pnl, 4)
        if pnl < by_symbol[s]["worst_trade"]:
            by_symbol[s]["worst_trade"] = round(pnl, 4)
        
        # Hold time
        if t.get("opened_at") and t.get("closed_at"):
            try:
                opened = datetime.fromisoformat(t["opened_at"].replace("Z", "+00:00"))
                closed = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
                hold_min = (closed - opened).total_seconds() / 60
                by_symbol[s]["total_hold_time"] += hold_min
            except Exception:
                pass
    
    for s in by_symbol.values():
        s["win_rate"] = round(s["wins"] / s["trades"] * 100, 1) if s["trades"] > 0 else 0
        s["avg_pnl"] = round(s["pnl"] / s["trades"], 4) if s["trades"] > 0 else 0
        s["avg_hold_time_min"] = round(s["total_hold_time"] / s["trades"], 1) if s["trades"] > 0 else 0
        s.pop("total_hold_time", None)
    
    symbol_rankings = sorted(by_symbol.values(), key=lambda x: x["pnl"], reverse=True)
    
    # Assign rank & medal
    for i, sr in enumerate(symbol_rankings):
        sr["rank"] = i + 1
    
    # 2. Best & Worst Trades
    sorted_by_pnl = sorted(trades, key=lambda x: x.get("pnl", 0), reverse=True)
    best_trades = [{
        "symbol": t["symbol"], "pnl": round(t.get("pnl", 0), 4),
        "pnl_percent": round(t.get("pnl_percent", 0), 2),
        "entry_price": t.get("entry_price", 0), "exit_price": t.get("exit_price", 0),
        "exit_reason": t.get("exit_reason", ""), "closed_at": t.get("closed_at", "")
    } for t in sorted_by_pnl[:5]]
    
    worst_trades = [{
        "symbol": t["symbol"], "pnl": round(t.get("pnl", 0), 4),
        "pnl_percent": round(t.get("pnl_percent", 0), 2),
        "entry_price": t.get("entry_price", 0), "exit_price": t.get("exit_price", 0),
        "exit_reason": t.get("exit_reason", ""), "closed_at": t.get("closed_at", "")
    } for t in sorted_by_pnl[-5:][::-1]]
    
    # 3. Streaks
    current_streak = 0
    current_type = "none"
    best_win_streak = 0
    worst_loss_streak = 0
    temp_win = 0
    temp_loss = 0
    
    for t in trades:
        if t.get("pnl", 0) > 0:
            temp_win += 1
            temp_loss = 0
            if temp_win > best_win_streak:
                best_win_streak = temp_win
        else:
            temp_loss += 1
            temp_win = 0
            if temp_loss > worst_loss_streak:
                worst_loss_streak = temp_loss
    
    # Current streak from end
    for t in reversed(trades):
        if not current_type or current_type == "none":
            current_type = "win" if t.get("pnl", 0) > 0 else "loss"
            current_streak = 1
        elif (current_type == "win" and t.get("pnl", 0) > 0) or (current_type == "loss" and t.get("pnl", 0) <= 0):
            current_streak += 1
        else:
            break
    
    # 4. Time Analysis (by hour)
    hourly = {}
    for t in trades:
        if t.get("closed_at"):
            try:
                closed = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
                hour = closed.hour
                if hour not in hourly:
                    hourly[hour] = {"hour": hour, "pnl": 0, "trades": 0, "wins": 0}
                hourly[hour]["pnl"] = round(hourly[hour]["pnl"] + t.get("pnl", 0), 4)
                hourly[hour]["trades"] += 1
                if t.get("pnl", 0) > 0:
                    hourly[hour]["wins"] += 1
            except Exception:
                pass
    
    hourly_list = sorted(hourly.values(), key=lambda x: x["hour"])
    best_hour = max(hourly.values(), key=lambda x: x["pnl"]) if hourly else None
    worst_hour = min(hourly.values(), key=lambda x: x["pnl"]) if hourly else None
    
    # 5. Exit Reason Analysis
    exit_stats = {}
    for t in trades:
        reason = t.get("exit_reason", "UNKNOWN")
        if reason not in exit_stats:
            exit_stats[reason] = {"reason": reason, "count": 0, "pnl": 0, "wins": 0}
        exit_stats[reason]["count"] += 1
        exit_stats[reason]["pnl"] = round(exit_stats[reason]["pnl"] + t.get("pnl", 0), 4)
        if t.get("pnl", 0) > 0:
            exit_stats[reason]["wins"] += 1
    
    for e in exit_stats.values():
        e["win_rate"] = round(e["wins"] / e["count"] * 100, 1) if e["count"] > 0 else 0
        e["avg_pnl"] = round(e["pnl"] / e["count"], 4) if e["count"] > 0 else 0
    
    # 6. Weekly PnL
    weekly = {}
    for t in trades:
        if t.get("closed_at"):
            try:
                closed = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
                week_key = closed.strftime("%Y-W%W")
                if week_key not in weekly:
                    weekly[week_key] = {"week": week_key, "pnl": 0, "trades": 0, "wins": 0}
                weekly[week_key]["pnl"] = round(weekly[week_key]["pnl"] + t.get("pnl", 0), 4)
                weekly[week_key]["trades"] += 1
                if t.get("pnl", 0) > 0:
                    weekly[week_key]["wins"] += 1
            except Exception:
                pass
    
    weekly_list = sorted(weekly.values(), key=lambda x: x["week"])
    
    # 7. Risk/Reward & Consistency
    rr_ratios = []
    for t in trades:
        if t.get("pnl", 0) > 0 and t.get("stop_loss") and t.get("entry_price"):
            risk = abs(t["entry_price"] - t["stop_loss"]) * t.get("quantity", 0)
            if risk > 0:
                rr_ratios.append(t["pnl"] / risk)
    
    avg_rr = round(sum(rr_ratios) / len(rr_ratios), 2) if rr_ratios else 0
    
    # Consistency: % of profitable weeks
    profitable_weeks = len([w for w in weekly.values() if w["pnl"] > 0])
    total_weeks = len(weekly)
    consistency = round(profitable_weeks / total_weeks * 100, 1) if total_weeks > 0 else 0
    
    return {
        "symbol_rankings": symbol_rankings,
        "best_trades": best_trades,
        "worst_trades": worst_trades,
        "streaks": {
            "current": current_streak,
            "current_type": current_type,
            "best_win": best_win_streak,
            "worst_loss": worst_loss_streak
        },
        "time_analysis": {
            "best_hour": best_hour,
            "worst_hour": worst_hour,
            "hourly_pnl": hourly_list
        },
        "exit_analysis": list(exit_stats.values()),
        "weekly_pnl": weekly_list,
        "risk_reward_avg": avg_rr,
        "consistency_score": consistency
    }

# ====================================================================
# STRATEGY BACKTESTER ENGINE
# ====================================================================

def generate_historical_candles(symbol, period_days, interval_minutes=15):
    """Generate realistic historical OHLCV candles with trends, mean reversion, and volatility clustering."""
    base_price = SYMBOL_PRICES.get(symbol, 1000.0)
    candles_per_day = int(24 * 60 / interval_minutes)
    total_candles = period_days * candles_per_day
    
    candles = []
    price = base_price * random.uniform(0.85, 1.15)
    
    # Generate trend phases
    trend_direction = random.choice([-1, 1])
    trend_strength = random.uniform(0.0001, 0.0005)
    trend_duration = random.randint(50, 200)
    trend_counter = 0
    
    vol_base = base_price * 0.002
    vol_current = vol_base
    
    start_time = datetime.now(timezone.utc) - timedelta(days=period_days)
    
    for i in range(total_candles):
        # Regime changes
        trend_counter += 1
        if trend_counter >= trend_duration:
            trend_direction = random.choice([-1, 1])
            trend_strength = random.uniform(0.0001, 0.0008)
            trend_duration = random.randint(30, 250)
            trend_counter = 0
            vol_current = vol_base * random.uniform(0.5, 2.5)
        
        # Volatility clustering (GARCH-like)
        vol_current = vol_current * 0.95 + vol_base * 0.05 + abs(random.gauss(0, vol_base * 0.1))
        
        drift = trend_direction * trend_strength * price
        noise = random.gauss(0, vol_current)
        
        # Mean reversion component
        mean_pull = (base_price - price) * 0.0002
        
        open_p = price
        close_p = open_p + drift + noise + mean_pull
        close_p = max(close_p, base_price * 0.3)
        
        intra_vol = vol_current * random.uniform(0.3, 1.5)
        high_p = max(open_p, close_p) + abs(random.gauss(0, intra_vol))
        low_p = min(open_p, close_p) - abs(random.gauss(0, intra_vol))
        low_p = max(low_p, base_price * 0.2)
        
        candle_time = start_time + timedelta(minutes=i * interval_minutes)
        
        candles.append({
            "open": round(open_p, 8),
            "high": round(high_p, 8),
            "low": round(low_p, 8),
            "close": round(close_p, 8),
            "volume": round(random.uniform(500, 50000) * (1 + vol_current / vol_base), 2),
            "time": candle_time.isoformat(),
            "timestamp": int(candle_time.timestamp() * 1000)
        })
        price = close_p
    
    return candles

def run_backtest(candles, params):
    """Run the trading strategy against historical candles with slippage, fees, volume filter, and volatility regime."""
    balance = params.initial_balance
    initial_balance = balance
    position = None
    trades = []
    equity_curve = []
    peak_equity = balance
    max_drawdown = 0
    max_drawdown_pct = 0
    total_fees = 0
    total_slippage = 0
    signals_rejected_volume = 0
    signals_rejected_regime = 0
    regime_changes = []
    
    slippage_pct = getattr(params, 'slippage_pct', 0.05) / 100
    fee_pct = getattr(params, 'fee_pct', 0.1) / 100
    vol_filter_mult = getattr(params, 'volume_filter_multiplier', 1.5)
    vol_regime_enabled = getattr(params, 'volatility_regime_enabled', True)
    vol_reduce_factor = getattr(params, 'volatility_reduce_factor', 0.5)
    
    lookback = max(40, params.rsi_period + 5)
    prev_regime = "NORMAL"
    
    for i in range(lookback, len(candles)):
        window = candles[max(0, i - 60):i + 1]
        closes = [c['close'] for c in window]
        current_price = closes[-1]
        current_time = candles[i]['time']
        
        # Track equity
        unrealized = 0
        if position:
            unrealized = (current_price - position['entry']) * position['qty']
        current_equity = balance + unrealized
        
        if current_equity > peak_equity:
            peak_equity = current_equity
        dd = peak_equity - current_equity
        dd_pct = (dd / peak_equity * 100) if peak_equity > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd
        if dd_pct > max_drawdown_pct:
            max_drawdown_pct = dd_pct
        
        # Volatility regime tracking
        if vol_regime_enabled and len(candles[:i+1]) > 120:
            regime, vol_pctl, regime_mult = volatility_regime(candles[:i+1])
            if regime != prev_regime:
                regime_changes.append({"time": current_time, "from": prev_regime, "to": regime, "percentile": vol_pctl})
                prev_regime = regime
        else:
            regime, vol_pctl, regime_mult = "NORMAL", 50.0, 1.0
        
        # Sample equity every 4 candles
        if i % 4 == 0:
            equity_curve.append({
                "time": current_time,
                "equity": round(current_equity, 2),
                "balance": round(balance, 2),
                "drawdown": round(dd_pct, 2),
                "regime": regime
            })
        
        # Manage open position
        if position:
            exit_reason = None
            exit_price = current_price
            
            if current_price <= position['sl']:
                exit_reason = "STOP_LOSS"
                exit_price = position['sl']
            elif current_price >= position['tp']:
                exit_reason = "TAKE_PROFIT"
                exit_price = position['tp']
            
            if not exit_reason and position.get('trail_active'):
                trail_dist = position['atr'] * params.trailing_stop_distance_pips
                new_sl = current_price - trail_dist
                if new_sl > position['sl']:
                    position['sl'] = new_sl
                if current_price <= position['sl']:
                    exit_reason = "TRAIL_STOP"
                    exit_price = position['sl']
            
            if not exit_reason and not position.get('trail_active'):
                activation = position['entry'] + position['atr'] * params.trailing_stop_activate_pips
                if current_price >= activation:
                    position['trail_active'] = True
            
            if exit_reason:
                # Apply slippage on exit
                slip = exit_price * slippage_pct
                exit_price -= slip  # Slippage hurts on sells
                total_slippage += abs(slip * position['qty'])
                
                # Calculate PnL
                raw_pnl = (exit_price - position['entry']) * position['qty']
                
                # Apply trading fee
                fee = abs(exit_price * position['qty']) * fee_pct
                total_fees += fee
                pnl = raw_pnl - fee
                
                pnl_pct = ((exit_price - position['entry']) / position['entry']) * 100
                balance += pnl
                
                trades.append({
                    "entry_price": round(position['entry'], 8),
                    "exit_price": round(exit_price, 8),
                    "entry_time": position['entry_time'],
                    "exit_time": current_time,
                    "qty": position['qty'],
                    "pnl": round(pnl, 4),
                    "pnl_percent": round(pnl_pct, 4),
                    "exit_reason": exit_reason,
                    "sl": round(position['sl'], 8),
                    "tp": round(position['tp'], 8),
                    "hold_candles": i - position['entry_idx'],
                    "fee": round(fee, 4),
                    "slippage": round(slip * position['qty'], 4),
                    "regime_at_entry": position.get('regime', 'NORMAL'),
                    "volume_ratio_at_entry": position.get('vol_ratio', 0)
                })
                position = None
            continue
        
        # Look for entry signal
        if len(closes) < lookback:
            continue
        
        # Technical indicators
        fast_e = ema(closes, 5)
        slow_e = ema(closes, 13)
        rsi = rsi_calc(closes, params.rsi_period)
        macd = macd_calc(closes)
        bb = bollinger_bands(closes)
        atr = atr_calc(window)
        
        if not all([fast_e, slow_e, rsi, macd, bb, atr]):
            continue
        if atr <= 0 or atr > current_price * 0.1:
            continue
        
        # Volume filter
        vol_passes, vol_ratio = volume_filter(window, vol_filter_mult)
        if not vol_passes:
            signals_rejected_volume += 1
            continue
        
        # Structure
        struct_candles = window[-10:-2]
        if len(struct_candles) >= 2:
            if struct_candles[-1]['high'] > struct_candles[-2]['high'] and struct_candles[-1]['low'] > struct_candles[-2]['low']:
                trend = 'UPTREND'
            elif struct_candles[-1]['high'] < struct_candles[-2]['high'] and struct_candles[-1]['low'] < struct_candles[-2]['low']:
                trend = 'DOWNTREND'
            else:
                trend = 'RANGE'
        else:
            trend = 'RANGE'
        
        # Sweep
        sweep = None
        if len(window) >= 2:
            if window[-1]['low'] < window[-2]['low'] and window[-1]['close'] > window[-2]['low']:
                sweep = 'BUY_SWEEP'
            elif fast_e > slow_e:
                sweep = 'EMA_BULLISH'
        
        has_signal = (
            (trend == 'UPTREND' and sweep in ['BUY_SWEEP', 'EMA_BULLISH']) or
            (trend != 'DOWNTREND' and sweep == 'BUY_SWEEP') or
            (fast_e > slow_e and rsi < 60 and rsi > 35)
        )
        
        if not has_signal or rsi > params.rsi_overbought:
            continue
        
        # Probability with volume and regime factors
        bb_pos = (current_price - bb['middle']) / (bb['upper'] - bb['middle']) if bb['upper'] != bb['middle'] else 0
        momentum = (fast_e - slow_e) / current_price * 100
        vol_bonus = min(0.15, (vol_ratio - 1) * 0.1)
        regime_penalty = -0.1 if regime == 'HIGH_VOL' else (0.05 if regime == 'NORMAL' else -0.05)
        
        z = (0.25 * momentum + 0.15 * (1 if trend == 'UPTREND' else 0.5) 
             - 0.05 * (atr / current_price * 100) 
             + 0.12 * (50 - abs(rsi - 50)) / 50 
             + 0.08 * max(-1, min(1, bb_pos))
             + 0.1 * (1 if sweep == 'BUY_SWEEP' else 0.5)
             + 0.15 * vol_bonus + 0.1 * regime_penalty)
        z = max(-5, min(5, z))
        prob = 1 / (1 + math.exp(-z))
        
        if prob < params.min_entry_probability:
            continue
        
        # Regime-based size adjustment
        if vol_regime_enabled and regime == 'HIGH_VOL':
            signals_rejected_regime += 1
            effective_mult = vol_reduce_factor
        else:
            effective_mult = 1.0
        
        # Position sizing with structure-based SL
        struct_sl = structure_stop_loss(window, 'LONG', atr)
        sl_price = current_price - atr * params.atr_sl_multiplier
        if struct_sl:
            sl_price = max(struct_sl, sl_price)  # Use tighter of the two
        tp_price = current_price + atr * params.atr_tp_multiplier
        
        # Apply slippage on entry
        entry_with_slip = current_price + (current_price * slippage_pct)
        entry_fee = abs(entry_with_slip * params.base_usdt_per_trade / entry_with_slip) * fee_pct
        total_fees += entry_fee
        total_slippage += abs(current_price * slippage_pct * params.base_usdt_per_trade / current_price)
        
        risk_amount = balance * (params.risk_per_trade_percent / 100) * effective_mult
        price_risk = abs(entry_with_slip - sl_price)
        if price_risk <= 0:
            continue
        
        qty = min(risk_amount / price_risk, params.base_usdt_per_trade * effective_mult / entry_with_slip)
        if qty <= 0 or qty * entry_with_slip < 5:
            continue
        
        balance -= entry_fee  # Deduct entry fee
        
        position = {
            'entry': entry_with_slip,
            'sl': sl_price,
            'tp': tp_price,
            'qty': round(qty, 8),
            'atr': atr,
            'entry_time': current_time,
            'entry_idx': i,
            'trail_active': False,
            'probability': prob,
            'regime': regime,
            'vol_ratio': vol_ratio
        }
    
    # Close any remaining position at last price
    if position:
        last_price = candles[-1]['close']
        slip = last_price * slippage_pct
        last_price -= slip
        fee = abs(last_price * position['qty']) * fee_pct
        total_fees += fee
        pnl = (last_price - position['entry']) * position['qty'] - fee
        pnl_pct = ((last_price - position['entry']) / position['entry']) * 100
        balance += pnl
        trades.append({
            "entry_price": round(position['entry'], 8),
            "exit_price": round(last_price, 8),
            "entry_time": position['entry_time'],
            "exit_time": candles[-1]['time'],
            "qty": position['qty'],
            "pnl": round(pnl, 4),
            "pnl_percent": round(pnl_pct, 4),
            "exit_reason": "END_OF_DATA",
            "sl": round(position['sl'], 8),
            "tp": round(position['tp'], 8),
            "hold_candles": len(candles) - position['entry_idx'],
            "fee": round(fee, 4),
            "slippage": round(slip * position['qty'], 4),
            "regime_at_entry": position.get('regime', 'NORMAL'),
            "volume_ratio_at_entry": position.get('vol_ratio', 0)
        })
    
    # Compute stats
    total = len(trades)
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    
    total_pnl = sum(t['pnl'] for t in trades)
    win_rate = len(wins) / total * 100 if total > 0 else 0
    avg_win = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t['pnl'] for t in losses) / len(losses) if losses else 0
    
    gross_profit = sum(t['pnl'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl'] for t in losses)) if losses else 0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0
    
    avg_hold = sum(t['hold_candles'] for t in trades) / total if total > 0 else 0
    
    # Sharpe-like ratio (simplified)
    if total > 1:
        pnl_list = [t['pnl'] for t in trades]
        mean_pnl = sum(pnl_list) / len(pnl_list)
        var_pnl = sum((p - mean_pnl) ** 2 for p in pnl_list) / (len(pnl_list) - 1)
        std_pnl = math.sqrt(var_pnl) if var_pnl > 0 else 0
        sharpe = round(mean_pnl / std_pnl * math.sqrt(252) if std_pnl > 0 else 0, 2)
    else:
        sharpe = 0
    
    # Expectancy
    expectancy = (win_rate / 100 * avg_win + (1 - win_rate / 100) * avg_loss) if total > 0 else 0
    
    # Win/Loss streaks
    best_win_streak = 0
    worst_loss_streak = 0
    tw, tl = 0, 0
    for t in trades:
        if t['pnl'] > 0:
            tw += 1
            tl = 0
            best_win_streak = max(best_win_streak, tw)
        else:
            tl += 1
            tw = 0
            worst_loss_streak = max(worst_loss_streak, tl)
    
    # Monthly PnL breakdown
    monthly = {}
    for t in trades:
        try:
            dt = datetime.fromisoformat(t['exit_time'].replace("Z", "+00:00"))
            mk = dt.strftime("%Y-%m")
            if mk not in monthly:
                monthly[mk] = {"month": mk, "pnl": 0, "trades": 0, "wins": 0}
            monthly[mk]["pnl"] = round(monthly[mk]["pnl"] + t['pnl'], 4)
            monthly[mk]["trades"] += 1
            if t['pnl'] > 0:
                monthly[mk]["wins"] += 1
        except Exception:
            pass
    
    # Exit reason breakdown
    exit_breakdown = {}
    for t in trades:
        r = t['exit_reason']
        if r not in exit_breakdown:
            exit_breakdown[r] = {"reason": r, "count": 0, "pnl": 0, "wins": 0}
        exit_breakdown[r]["count"] += 1
        exit_breakdown[r]["pnl"] = round(exit_breakdown[r]["pnl"] + t['pnl'], 4)
        if t['pnl'] > 0:
            exit_breakdown[r]["wins"] += 1
    
    return {
        "summary": {
            "total_trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 4),
            "total_pnl_percent": round((balance - initial_balance) / initial_balance * 100, 2),
            "final_balance": round(balance, 2),
            "initial_balance": round(initial_balance, 2),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "profit_factor": profit_factor,
            "max_drawdown": round(max_drawdown, 4),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "sharpe_ratio": sharpe,
            "expectancy": round(expectancy, 4),
            "avg_hold_candles": round(avg_hold, 1),
            "best_win_streak": best_win_streak,
            "worst_loss_streak": worst_loss_streak,
            "total_fees": round(total_fees, 4),
            "total_slippage": round(total_slippage, 4),
            "signals_rejected_volume": signals_rejected_volume,
            "signals_rejected_regime": signals_rejected_regime,
            "regime_changes": len(regime_changes),
        },
        "trades": trades[-200:],
        "equity_curve": equity_curve,
        "monthly_pnl": sorted(monthly.values(), key=lambda x: x["month"]),
        "exit_breakdown": list(exit_breakdown.values()),
        "regime_changes": regime_changes[:50],
        "candle_count": len(candles),
        "price_range": {
            "start": round(candles[0]['close'], 2) if candles else 0,
            "end": round(candles[-1]['close'], 2) if candles else 0,
            "high": round(max(c['high'] for c in candles), 2) if candles else 0,
            "low": round(min(c['low'] for c in candles), 2) if candles else 0
        }
    }

@api_router.post("/backtest")
async def run_backtest_api(params: BacktestRequest, user=Depends(get_current_user)):
    if params.symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Choose from: {VALID_SYMBOLS}")
    if params.period_days < 7 or params.period_days > 365:
        raise HTTPException(status_code=400, detail="Period must be between 7 and 365 days")
    
    candles = generate_historical_candles(params.symbol, params.period_days)
    result = run_backtest(candles, params)
    
    # Store backtest result
    backtest_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "symbol": params.symbol,
        "params": params.model_dump(),
        "summary": result["summary"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.backtests.insert_one(backtest_doc)
    
    result["backtest_id"] = backtest_doc["id"]
    return result

@api_router.get("/backtests")
async def get_backtest_history(user=Depends(get_current_user)):
    backtests = await db.backtests.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)
    return backtests

@api_router.post("/backtest/compare")
async def compare_strategies(data: StrategyCompareRequest, user=Depends(get_current_user)):
    """Run two strategies on the SAME price data for fair comparison."""
    if data.symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol")
    if data.period_days < 7 or data.period_days > 365:
        raise HTTPException(status_code=400, detail="Period must be 7-365 days")
    
    # Generate candles ONCE — both strategies see identical data
    candles = generate_historical_candles(data.symbol, data.period_days)
    
    # Override symbol and period to match
    data.strategy_a.symbol = data.symbol
    data.strategy_a.period_days = data.period_days
    data.strategy_b.symbol = data.symbol
    data.strategy_b.period_days = data.period_days
    
    result_a = run_backtest(candles, data.strategy_a)
    result_b = run_backtest(candles, data.strategy_b)
    
    sa = result_a["summary"]
    sb = result_b["summary"]
    
    # Determine winner per metric
    comparison = {
        "total_pnl": "A" if sa["total_pnl"] > sb["total_pnl"] else "B",
        "win_rate": "A" if sa["win_rate"] > sb["win_rate"] else "B",
        "profit_factor": "A" if sa["profit_factor"] > sb["profit_factor"] else "B",
        "max_drawdown": "A" if sa["max_drawdown_pct"] < sb["max_drawdown_pct"] else "B",
        "sharpe_ratio": "A" if sa["sharpe_ratio"] > sb["sharpe_ratio"] else "B",
        "expectancy": "A" if sa["expectancy"] > sb["expectancy"] else "B",
    }
    a_wins = list(comparison.values()).count("A")
    b_wins = list(comparison.values()).count("B")
    overall_winner = "A" if a_wins > b_wins else ("B" if b_wins > a_wins else "TIE")
    
    return {
        "symbol": data.symbol,
        "period_days": data.period_days,
        "candle_count": len(candles),
        "price_range": result_a["price_range"],
        "strategy_a": {
            "label": data.strategy_a.label or "Strategy A",
            "params": data.strategy_a.model_dump(),
            "summary": sa,
            "equity_curve": result_a["equity_curve"],
            "monthly_pnl": result_a["monthly_pnl"],
            "exit_breakdown": result_a["exit_breakdown"],
        },
        "strategy_b": {
            "label": data.strategy_b.label or "Strategy B",
            "params": data.strategy_b.model_dump(),
            "summary": sb,
            "equity_curve": result_b["equity_curve"],
            "monthly_pnl": result_b["monthly_pnl"],
            "exit_breakdown": result_b["exit_breakdown"],
        },
        "comparison": comparison,
        "overall_winner": overall_winner,
        "a_wins": a_wins,
        "b_wins": b_wins,
    }

# ====================================================================
# PRICES API
# ====================================================================

@api_router.get("/prices")
async def get_prices(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    symbols = config.get("symbols", ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']) if config else ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']
    return {s: SYMBOL_PRICES.get(s, 0) for s in symbols}

@api_router.get("/prices/history/{symbol}")
async def get_price_history(symbol: str, user=Depends(get_current_user)):
    history = await db.price_history.find({}, {"_id": 0}).sort("timestamp", -1).limit(200).to_list(200)
    history.reverse()
    data = []
    for h in history:
        if symbol in h.get("prices", {}):
            data.append({"timestamp": h["timestamp"], "price": h["prices"][symbol]})
    return data

# ====================================================================
# DATASET & FILTER STATS API
# ====================================================================

@api_router.get("/dataset/stats")
async def get_dataset_stats(user=Depends(get_current_user)):
    """Get ML training dataset statistics."""
    total = await db.signal_dataset.count_documents({})
    taken = await db.signal_dataset.count_documents({"trade_taken": True})
    rejected = await db.signal_dataset.count_documents({"trade_taken": False})
    wins = await db.signal_dataset.count_documents({"outcome": "WIN"})
    losses = await db.signal_dataset.count_documents({"outcome": "LOSS"})
    pending = await db.signal_dataset.count_documents({"trade_taken": True, "outcome": None})
    
    # Recent rejection reasons
    pipeline = [
        {"$match": {"trade_taken": False}},
        {"$sort": {"timestamp": -1}},
        {"$limit": 100},
    ]
    recent_rejected = await db.signal_dataset.aggregate(pipeline).to_list(100)
    
    rejection_reasons = {}
    for r in recent_rejected:
        for k, v in r.get("filters_passed", {}).items():
            if not v:
                rejection_reasons[k] = rejection_reasons.get(k, 0) + 1
    
    # Average confidence of taken vs rejected
    taken_conf_pipeline = [
        {"$match": {"trade_taken": True}},
        {"$group": {"_id": None, "avg_conf": {"$avg": "$confidence_score"}}}
    ]
    rejected_conf_pipeline = [
        {"$match": {"trade_taken": False}},
        {"$group": {"_id": None, "avg_conf": {"$avg": "$confidence_score"}}}
    ]
    taken_conf = await db.signal_dataset.aggregate(taken_conf_pipeline).to_list(1)
    rejected_conf = await db.signal_dataset.aggregate(rejected_conf_pipeline).to_list(1)
    
    return {
        "total_signals": total,
        "trades_taken": taken,
        "trades_rejected": rejected,
        "outcomes": {"wins": wins, "losses": losses, "pending": pending},
        "win_rate": round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
        "rejection_reasons": dict(sorted(rejection_reasons.items(), key=lambda x: -x[1])),
        "avg_confidence_taken": round(taken_conf[0]["avg_conf"], 4) if taken_conf else 0,
        "avg_confidence_rejected": round(rejected_conf[0]["avg_conf"], 4) if rejected_conf else 0,
        "cooldown_state": {
            "scans_since_loss": _cooldown_state["scans_since_loss"],
            "consecutive_losses": _cooldown_state["consecutive_losses"]
        }
    }

@api_router.get("/bot/filters")
async def get_filter_status(user=Depends(get_current_user)):
    """Get current smart filter configuration and status."""
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    if not config:
        config = await get_default_config()
    return {
        "filters": {
            "max_trades_per_hour": config.get("max_trades_per_hour", 2),
            "max_trades_per_day": config.get("max_trades_per_day", 8),
            "min_risk_reward_ratio": config.get("min_risk_reward_ratio", 2.5),
            "cooldown_after_loss_scans": config.get("cooldown_after_loss_scans", 6),
            "min_confidence_score": config.get("min_confidence_score", 0.60),
            "spread_max_percent": config.get("spread_max_percent", 0.15),
            "min_24h_volume_usdt": config.get("min_24h_volume_usdt", 1000000),
            "max_slippage_percent": config.get("max_slippage_percent", 0.1),
            "require_trend_alignment": config.get("require_trend_alignment", True),
        },
        "cooldown_state": {
            "scans_since_loss": _cooldown_state["scans_since_loss"],
            "consecutive_losses": _cooldown_state["consecutive_losses"]
        }
    }

@api_router.get("/ml/status")
async def get_ml_status(user=Depends(get_current_user)):
    """Get ML model status, metrics, and feature importance."""
    return {
        "status": ml_model_state["status"],
        "version": ml_model_state["version"],
        "metrics": {
            "accuracy": ml_model_state["accuracy"],
            "precision": ml_model_state["precision"],
            "recall": ml_model_state["recall"],
            "f1": ml_model_state["f1"],
            "cv_score": ml_model_state["cv_score"],
        },
        "training_data": {
            "total_samples": ml_model_state["training_samples"],
            "wins": ml_model_state["wins_in_training"],
            "losses": ml_model_state["losses_in_training"],
        },
        "last_trained": ml_model_state["last_trained"],
        "trades_since_retrain": ml_model_state["trades_since_retrain"],
        "feature_importance": ml_model_state["feature_importance"],
        "min_samples_required": ML_MIN_SAMPLES,
        "retrain_interval": ML_RETRAIN_INTERVAL,
    }

@api_router.post("/ml/train")
async def trigger_ml_training(user=Depends(get_current_user)):
    """Manually trigger ML model training."""
    labeled_count = await db.signal_dataset.count_documents({"outcome": {"$in": ["WIN", "LOSS"]}})
    if labeled_count < ML_MIN_SAMPLES:
        return {
            "status": "insufficient_data",
            "labeled_count": labeled_count,
            "required": ML_MIN_SAMPLES,
            "message": f"Need {ML_MIN_SAMPLES - labeled_count} more labeled outcomes to train."
        }
    await train_ml_model(db)
    return {
        "status": ml_model_state["status"],
        "version": ml_model_state["version"],
        "accuracy": ml_model_state["accuracy"],
        "message": f"ML model v{ml_model_state['version']} trained on {ml_model_state['training_samples']} samples"
    }

@api_router.post("/ml/seed")
async def seed_ml_data(user=Depends(get_current_user)):
    """Seed the ML dataset from historical trades."""
    before = await db.signal_dataset.count_documents({"outcome": {"$ne": None}})
    await seed_dataset_from_trades(db)
    after = await db.signal_dataset.count_documents({"outcome": {"$ne": None}})
    return {
        "seeded": after - before,
        "total_labeled": after,
        "min_required": ML_MIN_SAMPLES,
        "can_train": after >= ML_MIN_SAMPLES
    }

# ====================================================================
# PHASE 3: RISK & ANALYTICS API
# ====================================================================

@api_router.post("/risk/monte-carlo")
async def api_monte_carlo(user=Depends(get_current_user)):
    """Run Monte Carlo simulation on historical trade data."""
    result = await run_monte_carlo(db, n_simulations=1000, n_trades_per_sim=100)
    return result

@api_router.get("/risk/circuit-breaker")
async def api_circuit_breaker(user=Depends(get_current_user)):
    """Get circuit breaker status."""
    bal_doc = await db.bot_state.find_one({"key": "account_balance"})
    current_balance = bal_doc["value"] if bal_doc else 10000.0
    peak = _circuit_breaker["peak_balance"]
    dd_pct = ((peak - current_balance) / peak * 100) if peak > 0 else 0
    
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    max_dd = config.get("max_total_drawdown_percent", 5.0) if config else 5.0
    
    return {
        "tripped": _circuit_breaker["tripped"],
        "tripped_at": _circuit_breaker["tripped_at"],
        "drawdown_at_trip": _circuit_breaker["drawdown_at_trip"],
        "current_drawdown": round(dd_pct, 2),
        "peak_balance": round(peak, 2),
        "current_balance": round(current_balance, 2),
        "max_drawdown_threshold": max_dd,
    }

@api_router.post("/risk/circuit-breaker/reset")
async def api_reset_circuit_breaker(user=Depends(get_current_user)):
    """Manually reset the circuit breaker and unpause bot."""
    reset_circuit_breaker()
    bot_state["paused"] = False
    return {"status": "reset", "bot_paused": False}

@api_router.get("/risk/regime")
async def api_market_regime(user=Depends(get_current_user)):
    """Get current market regime for all symbols."""
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    symbols = config.get("symbols", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]) if config else ["BTCUSDT"]
    
    regimes = {}
    for symbol in symbols:
        candles = generate_candles(symbol, 60)
        regime, strength, details = detect_market_regime_advanced(candles)
        regimes[symbol] = {
            "regime": regime,
            "strength": strength,
            "details": details,
            "price": SYMBOL_PRICES.get(symbol, 0),
        }
    
    return {"regimes": regimes, "session": check_trading_session(config or {})}

@api_router.get("/risk/sessions")
async def api_trading_sessions(user=Depends(get_current_user)):
    """Get trading session info."""
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    session_ok, active_session = check_trading_session(config or {})
    now_utc = datetime.now(timezone.utc)
    return {
        "current_utc": now_utc.isoformat(),
        "current_hour": now_utc.hour,
        "in_session": session_ok,
        "active_session": active_session,
        "sessions": TRADING_SESSIONS,
        "allowed": config.get("allowed_sessions", ["ASIA", "LONDON", "NYC"]) if config else ["ASIA", "LONDON", "NYC"],
    }

# ====================================================================
# PHASE 4: ORDER FLOW, FUNDING & WHALE API
# ====================================================================

@api_router.get("/orderflow/{symbol}")
async def api_order_flow(symbol: str, user=Depends(get_current_user)):
    """Get order book depth analysis for a symbol."""
    if symbol not in VALID_SYMBOLS:
        raise HTTPException(400, f"Invalid symbol. Must be one of {VALID_SYMBOLS}")
    return await analyze_order_book(symbol)

@api_router.get("/orderflow")
async def api_order_flow_all(user=Depends(get_current_user)):
    """Get order flow summary for all active symbols."""
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    symbols = config.get("symbols", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]) if config else ["BTCUSDT"]
    results = {}
    for symbol in symbols[:4]:
        data = await analyze_order_book(symbol, limit=50)
        results[symbol] = {
            "imbalance_ratio": data["imbalance_ratio"],
            "pressure": data["pressure"],
            "total_bid_volume": data["total_bid_volume"],
            "total_ask_volume": data["total_ask_volume"],
            "bid_walls": len(data["bid_walls"]),
            "ask_walls": len(data["ask_walls"]),
            "source": data["source"],
        }
    return {"symbols": results}

@api_router.get("/funding-rates")
async def api_funding_rates(user=Depends(get_current_user)):
    """Get funding rate analysis for all active symbols."""
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    symbols = config.get("symbols", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]) if config else ["BTCUSDT"]
    rates = await fetch_funding_rates(symbols)
    
    # Arbitrage opportunities
    arb_opps = {s: r for s, r in rates.items() if r.get("arb_opportunity")}
    
    return {
        "rates": rates,
        "arbitrage_opportunities": arb_opps,
        "has_opportunities": len(arb_opps) > 0,
    }

@api_router.get("/whale-activity")
async def api_whale_activity(user=Depends(get_current_user)):
    """Get whale activity tracking for active symbols."""
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    symbols = config.get("symbols", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]) if config else ["BTCUSDT"]
    return await track_whale_activity(symbols)

# ====================================================================
# HEALTH CHECK
# ====================================================================

@api_router.get("/health")
async def health_check():
    """Kubernetes liveness/readiness probe endpoint."""
    try:
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    return {
        "status": "ok",
        "database": db_status,
        "bot_running": bot_state["running"],
        "mode": bot_state["mode"]
    }

# ====================================================================
# APP SETUP
# ====================================================================

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Ensure indexes — graceful, won't crash if they already exist
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("id", unique=True)
        await db.positions.create_index("id")
        await db.positions.create_index("status")
        await db.trades.create_index("closed_at")
        await db.bot_state.create_index("key", unique=True)
        await db.signal_dataset.create_index("timestamp")
        await db.signal_dataset.create_index("trade_taken")
        await db.signal_dataset.create_index("outcome")
        logger.info("Database indexes ensured successfully")
    except Exception as e:
        logger.warning(f"Index creation warning (non-fatal): {e}")
    
    # Initialize default config if not exists
    try:
        config = await db.bot_config.find_one({"active": True})
        if not config:
            await get_default_config()
    except Exception as e:
        logger.error(f"Failed to initialize bot config: {e}")
    
    # Initialize balance
    try:
        bal = await db.bot_state.find_one({"key": "account_balance"})
        if not bal:
            await db.bot_state.update_one({"key": "account_balance"}, {"$set": {"value": 10000.0}}, upsert=True)
    except Exception as e:
        logger.error(f"Failed to initialize balance: {e}")
    
    # Initialize Binance client (for LIVE mode support)
    await init_binance_client()
    
    # Initialize ML model
    await load_ml_model()
    await seed_dataset_from_trades(db)
    labeled = await db.signal_dataset.count_documents({"outcome": {"$in": ["WIN", "LOSS"]}})
    if labeled >= ML_MIN_SAMPLES:
        await train_ml_model(db)
        logger.info(f"ML model ready: {ml_model_state['status']} v{ml_model_state['version']} ({labeled} labeled samples)")
    else:
        logger.info(f"ML in LEARNING mode: {labeled}/{ML_MIN_SAMPLES} labeled samples")
    
    # Defensive bot auto-start: only if DB is reachable and config exists
    try:
        await db.command("ping")
        config = await db.bot_config.find_one({"active": True}, {"_id": 0})
        if config:
            bot_state["mode"] = config.get("mode", "DRY")
            await start_bot()
            logger.info(f"Application started, bot auto-started in {bot_state['mode']} mode")
        else:
            logger.warning("Bot not auto-started: no active config found")
    except Exception as e:
        logger.error(f"Bot auto-start skipped due to error: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    await stop_bot()
    await close_binance_client()
    client.close()
