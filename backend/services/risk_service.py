"""Professional risk management — circuit breaker, sessions, regime detection, Monte Carlo."""
import logging
from datetime import datetime, timezone
import numpy as np
import state
from config import TRADING_SESSIONS

logger = logging.getLogger(__name__)


async def check_circuit_breaker(db_ref, config):
    """Check if drawdown exceeds threshold, auto-pause bot if so."""
    max_dd = config.get("max_total_drawdown_percent", 5.0)
    bal_doc = await db_ref.bot_state.find_one({"key": "account_balance"})
    current_balance = bal_doc["value"] if bal_doc else 10000.0
    if current_balance > state._circuit_breaker["peak_balance"]:
        state._circuit_breaker["peak_balance"] = current_balance
    peak = state._circuit_breaker["peak_balance"]
    drawdown_pct = ((peak - current_balance) / peak) * 100 if peak > 0 else 0
    if drawdown_pct >= max_dd and not state._circuit_breaker["tripped"]:
        state._circuit_breaker["tripped"] = True
        state._circuit_breaker["tripped_at"] = datetime.now(timezone.utc).isoformat()
        state._circuit_breaker["drawdown_at_trip"] = round(drawdown_pct, 2)
        state.bot_state["paused"] = True
        logger.warning(f"CIRCUIT BREAKER TRIPPED: Drawdown {drawdown_pct:.2f}% >= {max_dd}%. Bot paused.")
        return False, round(drawdown_pct, 2)
    return True, round(drawdown_pct, 2)


def reset_circuit_breaker():
    """Manually reset the circuit breaker."""
    state._circuit_breaker["tripped"] = False
    state._circuit_breaker["tripped_at"] = None
    state._circuit_breaker["drawdown_at_trip"] = 0.0


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
        else:
            if current_hour >= start or current_hour < end:
                return True, session_name
    return False, "OUTSIDE_SESSION"


def detect_market_regime_advanced(candles):
    """Advanced market regime detection using multiple signals."""
    if not candles or len(candles) < 30:
        return "UNKNOWN", 0.5, {}
    closes = np.array([c['close'] for c in candles])
    highs = np.array([c['high'] for c in candles])
    lows = np.array([c['low'] for c in candles])
    volumes = np.array([c['volume'] for c in candles])
    x = np.arange(len(closes))
    slope = np.polyfit(x, closes, 1)[0]
    price_mean = np.mean(closes)
    trend_strength = abs(slope / price_mean * 1000) if price_mean > 0 else 0
    ranges = highs - lows
    atr = np.mean(ranges[-14:])
    atr_pct = (atr / closes[-1] * 100) if closes[-1] > 0 else 0
    up_moves = np.diff(highs)
    down_moves = -np.diff(lows)
    plus_dm = np.where((up_moves > down_moves) & (up_moves > 0), up_moves, 0)
    minus_dm = np.where((down_moves > up_moves) & (down_moves > 0), down_moves, 0)
    adx_proxy = abs(np.mean(plus_dm[-14:]) - np.mean(minus_dm[-14:])) / max(atr, 0.0001)
    vol_recent = np.mean(volumes[-5:])
    vol_avg = np.mean(volumes[-20:])
    vol_expansion = vol_recent / vol_avg if vol_avg > 0 else 1.0
    bb_std = np.std(closes[-20:])
    bb_bandwidth = (bb_std / price_mean * 100) if price_mean > 0 else 0
    regime = "RANGING"
    strength = 0.5
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
