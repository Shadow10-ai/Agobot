"""Risk management routes — circuit breaker, sessions, Monte Carlo, market regime."""
from fastapi import APIRouter, Depends
from auth import get_current_user
from database import db
from services.risk_service import check_circuit_breaker, reset_circuit_breaker, check_trading_session, detect_market_regime_advanced, run_monte_carlo
from services.binance_service import generate_candles
import state
from config import VALID_SYMBOLS

router = APIRouter()


@router.get("/risk/circuit-breaker")
async def get_circuit_breaker(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    if not config:
        config = {"max_total_drawdown_percent": 5.0}
    _, drawdown = await check_circuit_breaker(db, config)
    return {
        "tripped": state._circuit_breaker["tripped"],
        "tripped_at": state._circuit_breaker["tripped_at"],
        "drawdown_at_trip": state._circuit_breaker["drawdown_at_trip"],
        "current_drawdown_pct": drawdown,
        "peak_balance": state._circuit_breaker["peak_balance"],
        "max_drawdown_limit": config.get("max_total_drawdown_percent", 5.0),
    }


@router.post("/risk/circuit-breaker/reset")
async def reset_cb(user=Depends(get_current_user)):
    reset_circuit_breaker()
    if state.bot_state.get("paused"):
        state.bot_state["paused"] = False
    return {"message": "Circuit breaker reset", "tripped": False}


@router.get("/risk/sessions")
async def get_trading_sessions(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0}) or {}
    session_ok, active_session = check_trading_session(config)
    from config import TRADING_SESSIONS
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    return {
        "current_session": active_session,
        "session_ok": session_ok,
        "current_hour_utc": now_utc.hour,
        "allowed_sessions": config.get("allowed_sessions", ["ASIA", "LONDON", "NYC"]),
        "all_sessions": TRADING_SESSIONS,
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
async def get_market_regime(symbol: str = "BTCUSDT", user=Depends(get_current_user)):
    candles = generate_candles(symbol, 100)
    regime, strength, details = detect_market_regime_advanced(candles)
    return {
        "symbol": symbol,
        "regime": regime,
        "strength": strength,
        "details": details,
        "all_symbols": {
            s: detect_market_regime_advanced(generate_candles(s, 100))[0]
            for s in VALID_SYMBOLS[:4]
        }
    }
