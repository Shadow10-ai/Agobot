"""Risk management routes — circuit breaker, sessions, Monte Carlo, market regime."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from auth import get_current_user
from database import db
from services.risk_service import check_circuit_breaker, reset_circuit_breaker, check_trading_session, detect_market_regime_advanced, run_monte_carlo
from services.binance_service import generate_candles
import state
from config import VALID_SYMBOLS, TRADING_SESSIONS

router = APIRouter()


@router.get("/risk/circuit-breaker")
async def get_circuit_breaker(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    if not config:
        config = {}
    bal_doc = await db.bot_state.find_one({"key": "account_balance"})
    current_balance = bal_doc["value"] if bal_doc else 10000.0
    peak = state._circuit_breaker["peak_balance"]
    dd_pct = ((peak - current_balance) / peak * 100) if peak > 0 else 0
    max_dd = config.get("max_total_drawdown_percent", 5.0)
    return {
        "tripped": state._circuit_breaker["tripped"],
        "tripped_at": state._circuit_breaker["tripped_at"],
        "drawdown_at_trip": state._circuit_breaker["drawdown_at_trip"],
        "current_drawdown": round(dd_pct, 2),
        "peak_balance": round(peak, 2),
        "current_balance": round(current_balance, 2),
        "max_drawdown_threshold": max_dd,
    }


@router.post("/risk/circuit-breaker/reset")
async def reset_cb(user=Depends(get_current_user)):
    reset_circuit_breaker()
    state.bot_state["paused"] = False
    return {"status": "reset", "bot_paused": False}


@router.get("/risk/sessions")
async def get_trading_sessions(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0}) or {}
    in_session, active_session = check_trading_session(config)
    now_utc = datetime.now(timezone.utc)
    return {
        "current_utc": now_utc.isoformat(),
        "current_hour": now_utc.hour,
        "in_session": in_session,
        "active_session": active_session,
        "sessions": TRADING_SESSIONS,
        "allowed": config.get("allowed_sessions", ["ASIA", "LONDON", "NYC"]),
    }


@router.post("/risk/monte-carlo")
async def get_monte_carlo(
    n_simulations: int = 1000,
    n_trades: int = 100,
    initial_balance: float = 10000,
    user=Depends(get_current_user)
):
    return await run_monte_carlo(db, n_simulations, n_trades, initial_balance)


@router.get("/risk/regime")
async def get_market_regime(user=Depends(get_current_user)):
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
            "price": state.SYMBOL_PRICES.get(symbol, 0),
        }
    in_session, active_session = check_trading_session(config or {})
    return {"regimes": regimes, "session": (in_session, active_session)}
