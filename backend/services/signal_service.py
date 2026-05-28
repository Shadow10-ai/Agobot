"""Signal calculation — combines indicators and filters to generate trade signals.

Key design decisions vs previous version:
- Per-symbol ATR multipliers: alts get wider stops so normal noise doesn't hit the SL
- "Don't chase" filter: reject if price > 1.5x ATR from fast EMA (entering tops of moves)
- Candle body quality: reject shadow-dominant (indecision) candles
- Momentum confirmation: 2 of last 3 candles must support direction
- Fee-adjusted minimum TP: TP must be > 3x round-trip fee (1.56%) to have positive EV
"""
from services.indicators import ema, rsi_calc, macd_calc, bollinger_bands, atr_calc
from services.filters import volume_filter, volatility_regime, structure_stop_loss
from services.binance_service import generate_candles

# Per-symbol ATR multipliers — all maintain exactly 3.0 R:R.
# Wider for high-vol alts so spread + normal price noise doesn't immediately hit the SL.
SYMBOL_ATR_PROFILE = {
    "BTCUSDT":  {"sl": 1.8, "tp": 5.4},
    "ETHUSDT":  {"sl": 2.0, "tp": 6.0},
    "SOLUSDT":  {"sl": 2.8, "tp": 8.4},
    "XRPUSDT":  {"sl": 2.8, "tp": 8.4},
    "DOGEUSDT": {"sl": 3.5, "tp": 10.5},
}
_DEFAULT_ATR_PROFILE = {"sl": 2.0, "tp": 6.0}

# Must cover 0.52% round-trip Kraken fee × 3 = 1.56% minimum profit target
KRAKEN_ROUNDTRIP_FEE_PCT = 0.0052
MIN_TP_PCT = KRAKEN_ROUNDTRIP_FEE_PCT * 3.0  # 1.56%


def calculate_signal(symbol, candles=None, allow_short=False):
    if candles is None:
        candles = generate_candles(symbol, 60)

    closes = [c["close"] for c in candles]
    current_price = closes[-1]

    fast_ema = ema(closes, 5)
    slow_ema = ema(closes, 13)
    rsi      = rsi_calc(closes)
    macd     = macd_calc(closes)
    bb       = bollinger_bands(closes)
    atr      = atr_calc(candles)

    if not all([fast_ema, slow_ema, rsi, macd, bb, atr]):
        return None

    # --- Gate 1: Don't chase extended moves ---
    # Reject if price is more than 1.5x ATR away from the fast EMA.
    # If conditions are met but price is already far from EMA, the move is over — not starting.
    ema_distance_atr = abs(current_price - fast_ema) / atr
    if ema_distance_atr > 1.5:
        return None

    # --- Gate 2: Candle body quality ---
    # Reject candles where wicks dominate (indecision / reversal risk).
    last_candle  = candles[-1]
    candle_range = last_candle["high"] - last_candle["low"]
    body         = abs(last_candle["close"] - last_candle["open"])
    body_ratio   = body / candle_range if candle_range > 0 else 0
    if body_ratio < 0.25:
        return None

    vol_passes, vol_ratio           = volume_filter(candles, multiplier=1.5)
    regime, vol_percentile, regime_size_mult = volatility_regime(candles)

    # Trend from recent structure (excluding the last 2 candles to avoid look-ahead)
    structure_candles = candles[-10:-2]
    if len(structure_candles) >= 2:
        s0, s1 = structure_candles[-2], structure_candles[-1]
        if s1["high"] > s0["high"] and s1["low"] > s0["low"]:
            trend = "UPTREND"
        elif s1["high"] < s0["high"] and s1["low"] < s0["low"]:
            trend = "DOWNTREND"
        else:
            trend = "RANGE"
    else:
        trend = "RANGE"

    # Sweep / EMA bias (entry context, not entry trigger alone)
    sweep_signal = None
    if candles[-1]["low"] < candles[-2]["low"] and candles[-1]["close"] > candles[-2]["low"]:
        sweep_signal = "BUY_SWEEP"
    elif candles[-1]["high"] > candles[-2]["high"] and candles[-1]["close"] < candles[-2]["high"]:
        sweep_signal = "SELL_SWEEP"
    elif fast_ema > slow_ema:
        sweep_signal = "EMA_BULLISH"
    elif fast_ema < slow_ema:
        sweep_signal = "EMA_BEARISH"

    # --- Gate 3: Momentum confirmation ---
    # At least 2 of the last 3 candles must have a body supporting the direction.
    recent      = candles[-3:]
    green_count = sum(1 for c in recent if c["close"] > c["open"])
    red_count   = sum(1 for c in recent if c["close"] < c["open"])

    side = None
    has_buy = (
        (trend == "UPTREND"    and sweep_signal in ("BUY_SWEEP", "EMA_BULLISH")) or
        (trend != "DOWNTREND"  and sweep_signal == "BUY_SWEEP") or
        (fast_ema > slow_ema   and 35 < rsi < 60)
    )
    if has_buy and rsi <= 70 and green_count >= 2:
        side = "LONG"

    if side is None and allow_short:
        has_sell = (
            (trend == "DOWNTREND"  and sweep_signal in ("SELL_SWEEP", "EMA_BEARISH")) or
            (trend != "UPTREND"    and sweep_signal == "SELL_SWEEP") or
            (fast_ema < slow_ema   and 40 < rsi < 65)
        )
        if has_sell and rsi >= 30 and red_count >= 2:
            side = "SHORT"

    if side is None:
        return None

    # --- SL / TP: per-symbol ATR multipliers ---
    profile  = SYMBOL_ATR_PROFILE.get(symbol, _DEFAULT_ATR_PROFILE)
    sl_mult  = profile["sl"]
    tp_mult  = profile["tp"]

    if side == "LONG":
        struct_sl = structure_stop_loss(candles, "LONG", atr)
        sl = max(struct_sl, current_price - atr * sl_mult) if struct_sl else current_price - atr * sl_mult
        tp = current_price + atr * tp_mult
    else:
        highs      = [c["high"] for c in candles[-10:]]
        swing_high = max(highs)
        sl = max(swing_high + atr * 0.3, current_price + atr * sl_mult)
        tp = max(current_price - atr * tp_mult, current_price * 0.5)

    # --- Gate 4: Minimum fee-adjusted TP ---
    # TP must be > 1.56% from entry (3× round-trip Kraken fee) for positive expected value.
    tp_pct = abs(tp - current_price) / current_price
    if tp_pct < MIN_TP_PCT:
        return None

    # Confidence scoring
    bb_pos  = (current_price - bb["middle"]) / (bb["upper"] - bb["middle"]) if bb["upper"] != bb["middle"] else 0
    momentum   = (fast_ema - slow_ema) / current_price * 100
    vol_bonus  = min(0.15, (vol_ratio - 1) * 0.1) if vol_passes else -0.1
    regime_penalty = -0.1 if regime == "HIGH_VOL" else (0.05 if regime == "NORMAL" else -0.05)

    if side == "LONG":
        scores = [
            1.0 if trend == "UPTREND" else (0.5 if trend == "RANGE" else 0.0),
            max(0, min(1, 0.5 + momentum * 5)),
            max(0, min(1, (60 - rsi) / 30)) if rsi < 60 else 0,
            1.0 if sweep_signal == "BUY_SWEEP" else (0.6 if sweep_signal == "EMA_BULLISH" else 0.0),
            max(0, min(1, 0.5 - bb_pos * 0.5)),
        ]
    else:
        scores = [
            1.0 if trend == "DOWNTREND" else (0.5 if trend == "RANGE" else 0.0),
            max(0, min(1, 0.5 - momentum * 5)),
            max(0, min(1, (rsi - 40) / 30)) if rsi > 40 else 0,
            1.0 if sweep_signal == "SELL_SWEEP" else (0.6 if sweep_signal == "EMA_BEARISH" else 0.0),
            max(0, min(1, 0.5 + bb_pos * 0.5)),
        ]

    scores += [
        max(0, min(1, vol_bonus + 0.5)),
        max(0, min(1, 0.5 + regime_penalty)),
    ]
    weights   = [0.22, 0.18, 0.15, 0.15, 0.10, 0.10, 0.10]
    raw_score = sum(s * w for s, w in zip(scores, weights))
    prob      = 0.25 + raw_score * 0.67

    return {
        "symbol":   symbol,
        "side":     side,
        "price":    current_price,
        "probability": prob,
        "rsi":      rsi,
        "macd":     macd,
        "bb":       bb,
        "atr":      atr,
        "trend":    trend,
        "sl":       sl,
        "tp":       tp,
        "volume_ratio":          vol_ratio,
        "volume_passes":         vol_passes,
        "volatility_regime":     regime,
        "volatility_percentile": vol_percentile,
        "regime_size_multiplier": regime_size_mult,
        "indicators": {
            "ema_fast":       fast_ema,
            "ema_slow":       slow_ema,
            "rsi":            round(rsi, 2),
            "macd_value":     round(macd["macd"], 6),
            "macd_signal":    round(macd["signal"], 6),
            "macd_histogram": round(macd["histogram"], 6),
            "bb_upper":       round(bb["upper"], 6),
            "bb_middle":      round(bb["middle"], 6),
            "bb_lower":       round(bb["lower"], 6),
            "atr":            round(atr, 6),
            "volume_ratio":   vol_ratio,
            "vol_regime":     regime,
            "vol_percentile": vol_percentile,
        },
    }
