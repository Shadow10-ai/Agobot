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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
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

class TelegramConfig(BaseModel):
    telegram_token: str = ""
    telegram_chat_id: str = ""

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

def calculate_signal(symbol):
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
    
    # Multi-timeframe structure check (use earlier candles for structure)
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
    
    # Sweep check on most recent candles
    sweep_signal = None
    if candles[-1]['low'] < candles[-2]['low'] and candles[-1]['close'] > candles[-2]['low']:
        sweep_signal = 'BUY_SWEEP'
    # Also check if EMA crossover is bullish
    elif fast_ema > slow_ema:
        sweep_signal = 'EMA_BULLISH'
    
    # Buy signals: uptrend + sweep, or strong EMA signal
    has_buy_signal = (
        (trend == 'UPTREND' and sweep_signal in ['BUY_SWEEP', 'EMA_BULLISH']) or
        (trend != 'DOWNTREND' and sweep_signal == 'BUY_SWEEP') or
        (fast_ema > slow_ema and rsi < 60 and rsi > 35)
    )
    
    if not has_buy_signal:
        return None
    
    if rsi > 70:
        return None
    
    # Probability calculation
    bb_pos = (current_price - bb['middle']) / (bb['upper'] - bb['middle']) if bb['upper'] != bb['middle'] else 0
    momentum = (fast_ema - slow_ema) / current_price * 100
    z = 0.3 * momentum + 0.2 * (1 if trend == 'UPTREND' else 0.5) - 0.05 * (atr / current_price * 100) + 0.15 * (50 - abs(rsi - 50)) / 50 + 0.1 * max(-1, min(1, bb_pos)) + 0.1 * (1 if sweep_signal == 'BUY_SWEEP' else 0.5)
    z = max(-5, min(5, z))
    prob = 1 / (1 + math.exp(-z))
    
    sl_distance = atr * 1.2
    tp_distance = atr * 2.4
    sl = current_price - sl_distance
    tp = current_price + tp_distance
    
    return {
        "symbol": symbol,
        "price": current_price,
        "probability": prob,
        "rsi": rsi,
        "macd": macd,
        "bb": bb,
        "atr": atr,
        "trend": trend,
        "sl": sl,
        "tp": tp,
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
            "atr": round(atr, 6)
        }
    }

# ====================================================================
# BOT BACKGROUND TASK
# ====================================================================

async def bot_scan_loop():
    """Main bot scan loop - runs as background task"""
    logger.info("Bot scan loop started")
    
    while bot_state["running"]:
        if bot_state["paused"]:
            await asyncio.sleep(5)
            continue
        
        try:
            config = await db.bot_config.find_one({"active": True}, {"_id": 0})
            if not config:
                config = await get_default_config()
            
            symbols = config.get("symbols", ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT'])
            min_prob = config.get("min_entry_probability", 0.65)
            base_usdt = config.get("base_usdt_per_trade", 50)
            
            # Update simulated prices
            for symbol in symbols:
                if symbol in SYMBOL_PRICES:
                    change = random.gauss(0, SYMBOL_PRICES[symbol] * 0.001)
                    SYMBOL_PRICES[symbol] = round(max(0.01, SYMBOL_PRICES[symbol] + change), 8)
            
            # Check existing positions
            positions = await db.positions.find({"status": "OPEN"}, {"_id": 0}).to_list(100)
            for pos in positions:
                symbol = pos["symbol"]
                current_price = SYMBOL_PRICES.get(symbol, pos["entry_price"])
                
                # Check SL/TP
                exit_reason = None
                exit_price = current_price
                
                if current_price <= pos["stop_loss"]:
                    exit_reason = "STOP_LOSS"
                    exit_price = pos["stop_loss"]
                elif current_price >= pos["take_profit"]:
                    exit_reason = "TAKE_PROFIT"
                    exit_price = pos["take_profit"]
                
                # Trailing stop check
                if not exit_reason and pos.get("trail_activated"):
                    trail_distance = pos["atr"] * config.get("trailing_stop_distance_pips", 1.2)
                    new_sl = current_price - trail_distance
                    if new_sl > pos["stop_loss"]:
                        await db.positions.update_one(
                            {"id": pos["id"]},
                            {"$set": {"stop_loss": round(new_sl, 8)}}
                        )
                    if current_price <= pos["stop_loss"]:
                        exit_reason = "TRAIL_STOP"
                        exit_price = pos["stop_loss"]
                
                # Activate trailing
                if not exit_reason and not pos.get("trail_activated"):
                    activation = pos["entry_price"] + pos["atr"] * config.get("trailing_stop_activate_pips", 2.4)
                    if current_price >= activation:
                        await db.positions.update_one(
                            {"id": pos["id"]},
                            {"$set": {"trail_activated": True}}
                        )
                
                # Close position
                if exit_reason:
                    pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
                    pnl_percent = ((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100
                    
                    now = datetime.now(timezone.utc).isoformat()
                    await db.positions.update_one(
                        {"id": pos["id"]},
                        {"$set": {"status": "CLOSED", "exit_price": round(exit_price, 8), "exit_reason": exit_reason, "pnl": round(pnl, 4), "pnl_percent": round(pnl_percent, 4), "closed_at": now}}
                    )
                    
                    trade_doc = {
                        "id": str(uuid.uuid4()),
                        "symbol": symbol,
                        "side": "LONG",
                        "entry_price": pos["entry_price"],
                        "exit_price": round(exit_price, 8),
                        "quantity": pos["quantity"],
                        "pnl": round(pnl, 4),
                        "pnl_percent": round(pnl_percent, 4),
                        "exit_reason": exit_reason,
                        "opened_at": pos["opened_at"],
                        "closed_at": now,
                        "mode": "DRY",
                        "stop_loss": pos["stop_loss"],
                        "take_profit": pos["take_profit"]
                    }
                    await db.trades.insert_one(trade_doc)
                    
                    # Update daily PnL
                    await db.bot_state.update_one(
                        {"key": "daily_pnl"},
                        {"$inc": {"value": round(pnl, 4)}},
                        upsert=True
                    )
                    
                    logger.info(f"Closed {symbol} via {exit_reason}: PnL {pnl:.4f} USDT")
                else:
                    # Update unrealized PnL
                    unrealized = (current_price - pos["entry_price"]) * pos["quantity"]
                    unrealized_pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
                    await db.positions.update_one(
                        {"id": pos["id"]},
                        {"$set": {"current_price": round(current_price, 8), "unrealized_pnl": round(unrealized, 4), "unrealized_pnl_percent": round(unrealized_pct, 4)}}
                    )
            
            # Look for new entries
            open_count = await db.positions.count_documents({"status": "OPEN"})
            if open_count < 4:
                for symbol in symbols:
                    if await db.positions.find_one({"symbol": symbol, "status": "OPEN"}):
                        continue
                    
                    signal = calculate_signal(symbol)
                    if signal and signal["probability"] >= min_prob:
                        quantity = round(base_usdt / signal["price"], 8)
                        
                        now = datetime.now(timezone.utc).isoformat()
                        position_doc = {
                            "id": str(uuid.uuid4()),
                            "symbol": symbol,
                            "side": "LONG",
                            "entry_price": round(signal["price"], 8),
                            "current_price": round(signal["price"], 8),
                            "stop_loss": round(signal["sl"], 8),
                            "take_profit": round(signal["tp"], 8),
                            "quantity": quantity,
                            "atr": round(signal["atr"], 8),
                            "probability": round(signal["probability"], 4),
                            "status": "OPEN",
                            "trail_activated": False,
                            "unrealized_pnl": 0.0,
                            "unrealized_pnl_percent": 0.0,
                            "opened_at": now,
                            "mode": "DRY",
                            "indicators": signal["indicators"]
                        }
                        await db.positions.insert_one(position_doc)
                        logger.info(f"Opened LONG {symbol} @ {signal['price']:.8f}, Prob: {signal['probability']:.2%}")
                        break
            
            bot_state["scan_count"] += 1
            bot_state["last_scan"] = datetime.now(timezone.utc).isoformat()
            
            # Save price snapshot for charts
            price_snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "prices": {s: SYMBOL_PRICES.get(s, 0) for s in symbols}
            }
            await db.price_history.insert_one(price_snapshot)
            
            # Trim old price history (keep last 1000)
            count = await db.price_history.count_documents({})
            if count > 1000:
                oldest = await db.price_history.find({}, {"_id": 1}).sort("_id", 1).limit(count - 1000).to_list(count - 1000)
                if oldest:
                    ids = [o["_id"] for o in oldest]
                    await db.price_history.delete_many({"_id": {"$in": ids}})
            
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

# ====================================================================
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
    # Ensure indexes
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.positions.create_index("id")
    await db.positions.create_index("status")
    await db.trades.create_index("closed_at")
    await db.bot_state.create_index("key", unique=True)
    
    # Initialize default config if not exists
    config = await db.bot_config.find_one({"active": True})
    if not config:
        await get_default_config()
    
    # Initialize balance
    bal = await db.bot_state.find_one({"key": "account_balance"})
    if not bal:
        await db.bot_state.update_one({"key": "account_balance"}, {"$set": {"value": 10000.0}}, upsert=True)
    
    # Auto-start bot
    await start_bot()
    logger.info("Application started, bot auto-started in DRY mode")

@app.on_event("shutdown")
async def shutdown_event():
    await stop_bot()
    client.close()
