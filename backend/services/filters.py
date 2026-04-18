"""Smart entry filters and confidence scoring."""
import logging
from datetime import datetime, timezone, timedelta
from services.indicators import ema, atr_calc
import state
from config import CORRELATION_GROUPS

logger = logging.getLogger(__name__)


def volume_filter(candles, multiplier=1.5):
    """Check if recent volume exceeds average by multiplier."""
    if not candles or len(candles) < 20:
        return True, 1.0
    volumes = [c['volume'] for c in candles[-20:]]
    avg_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 1
    current_vol = volumes[-1]
    if avg_vol <= 0:
        return True, 1.0
    vol_ratio = current_vol / avg_vol
    return vol_ratio >= multiplier, round(vol_ratio, 2)


def volatility_regime(candles, period=14, lookback=100):
    """Detect if market is in high/low volatility regime using ATR percentile."""
    if not candles or len(candles) < lookback + period:
        return "NORMAL", 50.0, 1.0
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
        size_mult = 0.5
    elif percentile <= 20:
        regime = "LOW_VOL"
        size_mult = 0.7
    else:
        regime = "NORMAL"
        size_mult = 1.0
    return regime, round(percentile, 1), round(size_mult, 2)


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
    lows = [c['low'] for c in candles[-10:]]
    swing_low = min(lows)
    if atr and atr > 0:
        sl = swing_low - (atr * buffer_atr_mult)
    else:
        sl = swing_low * 0.998
    return max(sl, 0)


def check_spread(candles, max_spread_pct=0.15):
    """Check if the bid-ask spread is acceptable."""
    if not candles or len(candles) < 2:
        return True, 0.0
    last = candles[-1]
    candle_range = last['high'] - last['low']
    mid = (last['high'] + last['low']) / 2
    estimated_spread_pct = (candle_range / mid * 100) * 0.1 if mid > 0 else 0
    return estimated_spread_pct <= max_spread_pct, round(estimated_spread_pct, 4)


def estimate_slippage(candles, trade_usdt, max_slippage_pct=0.1):
    """Estimate slippage based on recent volume."""
    if not candles or len(candles) < 5:
        return True, 0.0
    recent_vols = [c['volume'] for c in candles[-5:]]
    avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 1
    price = candles[-1]['close']
    avg_vol_usdt = avg_vol * price
    if avg_vol_usdt <= 0:
        return False, 999.0
    impact = (trade_usdt / avg_vol_usdt) * 100 * 2
    return impact <= max_slippage_pct, round(impact, 4)


def check_min_liquidity(candles, min_volume_usdt=1_000_000):
    """Check if 24h volume meets minimum."""
    if not candles or len(candles) < 10:
        return True, 0
    price = candles[-1]['close']
    total_vol = sum(c['volume'] for c in candles[-20:])
    estimated_24h = total_vol * 24 * price
    return estimated_24h >= min_volume_usdt, round(estimated_24h, 0)


def check_cooldown(config):
    """Check if we're in a cooldown period after consecutive losses."""
    required = config.get("cooldown_after_loss_scans", 6)
    if state._cooldown_state["scans_since_loss"] < required:
        return False, state._cooldown_state["scans_since_loss"], required
    return True, state._cooldown_state["scans_since_loss"], required


def update_cooldown(is_loss):
    """Update cooldown state after a trade closes."""
    if is_loss:
        state._cooldown_state["scans_since_loss"] = 0
        state._cooldown_state["consecutive_losses"] += 1
    else:
        state._cooldown_state["consecutive_losses"] = 0


def increment_cooldown():
    """Called each scan to count up from last loss."""
    state._cooldown_state["scans_since_loss"] += 1


def multi_timeframe_trend(candles, side):
    """Check if trade direction aligns with higher timeframe trend."""
    if not candles or len(candles) < 30:
        return True, "INSUFFICIENT_DATA"
    short_closes = [c['close'] for c in candles[-10:]]
    short_ema = ema(short_closes, 5) or short_closes[-1]
    med_closes = [c['close'] for c in candles[-30:]]
    med_ema = ema(med_closes, 13) or med_closes[-1]
    long_ema = ema([c['close'] for c in candles], 26) or candles[-1]['close']
    if short_ema > med_ema > long_ema:
        htf_trend = "BULLISH"
    elif short_ema < med_ema < long_ema:
        htf_trend = "BEARISH"
    else:
        htf_trend = "MIXED"
    if side == "LONG":
        aligned = htf_trend in ("BULLISH", "MIXED")
    else:
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
    """Check if we've exceeded max trades per hour or per day.
    Only counts LIVE mode trades — DRY simulation trades are excluded."""
    max_per_hour = config.get("max_trades_per_hour", 5)
    max_per_day = config.get("max_trades_per_day", 20)
    now = datetime.now(timezone.utc)
    hour_ago = (now - timedelta(hours=1)).isoformat()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    live_filter = {"mode": "LIVE"}
    trades_last_hour = await db_ref.trades.count_documents({"closed_at": {"$gte": hour_ago}, **live_filter})
    trades_today = await db_ref.trades.count_documents({"closed_at": {"$gte": day_start}, **live_filter})
    hour_ok = trades_last_hour < max_per_hour
    day_ok = trades_today < max_per_day
    return hour_ok and day_ok, trades_last_hour, max_per_hour, trades_today, max_per_day


def calculate_confidence_score(signal, candles, config):
    """Composite confidence score combining technical probability, volume, regime, and trend."""
    tech_prob = signal["probability"]
    vol_score = min(1.0, signal.get("volume_ratio", 0.5) / 2.0) if signal.get("volume_passes") else 0.2
    regime = signal.get("volatility_regime", "NORMAL")
    regime_score = {"LOW_VOL": 0.6, "NORMAL": 0.85, "HIGH_VOL": 0.4}.get(regime, 0.5)
    side = signal.get("side", "LONG")
    aligned, htf = multi_timeframe_trend(candles, side)
    trend_score = 1.0 if aligned and htf != "MIXED" else (0.7 if aligned else 0.3)
    entry, sl, tp = signal["price"], signal["sl"], signal["tp"]
    if side == "LONG":
        risk = abs(entry - sl)
        reward = abs(tp - entry)
    else:
        risk = abs(sl - entry)
        reward = abs(entry - tp)
    rr = reward / risk if risk > 0 else 0
    rr_score = min(1.0, rr / 3.0)
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
