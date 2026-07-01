"""Signal calculation — three specific entry patterns, not a broad persistent state.

Previous weakness: `fast_ema > slow_ema and 35 < rsi < 60` fires constantly in any
uptrend — it describes a market state, not an entry trigger. Replaced with three
time-limited, high-conviction patterns:

  Pattern A — EMA13 Pullback
    EMA stack bullish (EMA5 > EMA13 > EMA26) confirms trend.
    Price pulls back within 0.5 ATR of EMA13 (the mean).
    RSI 38–55: healthy dip zone, not oversold panic.
    Entry = buying support in a confirmed trend, not chasing a breakout.

  Pattern B — Fresh EMA5/13 Cross + MACD Acceleration
    EMA5 crossed EMA13 on THIS candle (event, not persistent state).
    MACD histogram is positive AND greater than the previous bar (momentum building).
    RSI < 65: not overbought at the moment of cross.
    Entry = early in a trend shift, confirmed by momentum.

  Pattern C — Liquidity Sweep Reversal
    Price swept BELOW the previous candle low and closed BACK above it (pin bar).
    EMA stack must still be bullish (sweep in a trend, not random noise).
    RSI < 60: not already overbought.
    Entry = institutional stop-hunt reversal, highest short-term conviction pattern.

All three require:
  - EMA5 > EMA13 > EMA26 structural stack (no trading against trend)
  - 2 of last 3 candles green (momentum confirmation)
  - Price within 1.5 ATR of EMA5 (no chasing extended moves)
  - Candle body > 25% of range (no indecision candles)
  - TP > 1.56% from entry (3x Kraken round-trip fee for positive EV)
  - Per-symbol ATR multipliers so alts get wider stops than BTC
"""
from services.indicators import ema, rsi_calc, macd_calc, bollinger_bands, atr_calc
from services.filters import volume_filter, volatility_regime, structure_stop_loss
from services.binance_service import generate_candles

SYMBOL_ATR_PROFILE = {
    "BTCUSDT":  {"sl": 1.8, "tp": 5.4},
    "ETHUSDT":  {"sl": 2.0, "tp": 6.0},
    "SOLUSDT":  {"sl": 2.8, "tp": 8.4},
    "XRPUSDT":  {"sl": 2.8, "tp": 8.4},
    "DOGEUSDT": {"sl": 3.5, "tp": 10.5},
}
_DEFAULT_ATR_PROFILE = {"sl": 2.0, "tp": 6.0}

KRAKEN_ROUNDTRIP_FEE_PCT = 0.0052   # 0.26% entry + 0.26% exit
MIN_TP_PCT = KRAKEN_ROUNDTRIP_FEE_PCT * 3.0   # 1.56% — minimum positive EV


def calculate_signal(symbol, candles=None, allow_short=False):
    if candles is None:
        candles = generate_candles(symbol, 60)

    closes        = [c["close"] for c in candles]
    current_price = closes[-1]

    fast_ema = ema(closes, 5)
    slow_ema = ema(closes, 13)
    ema_26   = ema(closes, 26)
    rsi      = rsi_calc(closes)
    macd     = macd_calc(closes)
    bb       = bollinger_bands(closes)
    atr      = atr_calc(candles)

    if not all([fast_ema, slow_ema, ema_26, rsi, macd, bb, atr]):
        return None

    # ── Pre-signal gates (cheap, exit early) ─────────────────────────────────

    # Gate 1: Don't chase — price must be within 1.5 ATR of EMA5
    if abs(current_price - fast_ema) / atr > 1.5:
        return None

    # Gate 2: Candle body must be real — reject indecision / wick-heavy candles
    last       = candles[-1]
    c_range    = last["high"] - last["low"]
    body       = abs(last["close"] - last["open"])
    if c_range > 0 and body / c_range < 0.25:
        return None

    vol_passes, vol_ratio                    = volume_filter(candles, multiplier=1.5)
    regime, vol_percentile, regime_size_mult = volatility_regime(candles)

    # ── EMA stack — structural requirement for ALL entries ────────────────────
    ema_stack_bullish = fast_ema > slow_ema > ema_26
    ema_stack_bearish = fast_ema < slow_ema < ema_26

    # ── Previous-bar values for crossover and MACD acceleration checks ────────
    prev_fast      = ema(closes[:-1], 5)
    prev_slow      = ema(closes[:-1], 13)
    prev_macd_data = macd_calc(closes[:-1])

    # ── Liquidity sweep detector ──────────────────────────────────────────────
    sweep = None
    if candles[-1]["low"] < candles[-2]["low"] and candles[-1]["close"] > candles[-2]["low"]:
        sweep = "BUY_SWEEP"
    elif candles[-1]["high"] > candles[-2]["high"] and candles[-1]["close"] < candles[-2]["high"]:
        sweep = "SELL_SWEEP"

    # ── Momentum confirmation: 2 of last 3 candles must support direction ─────
    recent      = candles[-3:]
    green_count = sum(1 for c in recent if c["close"] > c["open"])
    red_count   = sum(1 for c in recent if c["close"] < c["open"])

    # ── Trend from higher-structure candles (excludes last 2 to avoid look-ahead)
    sc = candles[-10:-2]
    if len(sc) >= 2:
        trend = ("UPTREND"   if sc[-1]["high"] > sc[-2]["high"] and sc[-1]["low"] > sc[-2]["low"]
                 else "DOWNTREND" if sc[-1]["high"] < sc[-2]["high"] and sc[-1]["low"] < sc[-2]["low"]
                 else "RANGE")
    else:
        trend = "RANGE"

    # ═══════════════════════════════════════════════════════════════════════════
    # LONG — three specific patterns, all require bullish EMA stack
    # ═══════════════════════════════════════════════════════════════════════════
    side = None

    if ema_stack_bullish and green_count >= 2:

        # Pattern A: Pullback to EMA13 in a confirmed uptrend
        # Rationale: EMA13 acts as dynamic support; enter when price returns to the mean
        # NOT when it's already extended above it.
        price_near_ema13 = abs(current_price - slow_ema) <= atr * 0.5
        rsi_dip_zone     = 38 <= rsi <= 55   # pulled back but not panic-sold

        # Pattern B: Fresh EMA5/EMA13 crossover this candle + MACD histogram rising
        # Rationale: the exact candle of the cross is the lowest-risk entry.
        # Requiring histogram > prev histogram ensures momentum is genuinely building.
        fresh_cross_up = (
            prev_fast is not None and prev_slow is not None
            and prev_fast <= prev_slow   # was below or equal last bar
        )
        macd_accelerating_up = (
            macd["histogram"] > 0
            and prev_macd_data is not None
            and macd["histogram"] > prev_macd_data["histogram"]
        )

        # Pattern C: Liquidity sweep reversal — pin-bar trap in an uptrend
        # Rationale: price sweeps below previous low (stop hunt), then closes above.
        # Only valid when trend structure is still bullish.
        valid_sweep_up = sweep == "BUY_SWEEP" and rsi < 60

        if (price_near_ema13 and rsi_dip_zone) or \
           (fresh_cross_up and macd_accelerating_up and rsi < 65) or \
           valid_sweep_up:
            side = "LONG"

    # ═══════════════════════════════════════════════════════════════════════════
    # SHORT — mirror logic, requires bearish EMA stack
    # ═══════════════════════════════════════════════════════════════════════════
    if side is None and allow_short and ema_stack_bearish and red_count >= 2:

        price_near_ema13_short = abs(current_price - slow_ema) <= atr * 0.5
        rsi_rally_zone         = 45 <= rsi <= 62   # rallied back to mean, not overbought

        fresh_cross_down = (
            prev_fast is not None and prev_slow is not None
            and prev_fast >= prev_slow
        )
        macd_accelerating_down = (
            macd["histogram"] < 0
            and prev_macd_data is not None
            and macd["histogram"] < prev_macd_data["histogram"]
        )

        valid_sweep_down = sweep == "SELL_SWEEP" and rsi > 40

        if (price_near_ema13_short and rsi_rally_zone) or \
           (fresh_cross_down and macd_accelerating_down and rsi > 35) or \
           valid_sweep_down:
            side = "SHORT"

    if side is None:
        return None

    # ── SL / TP: per-symbol ATR multipliers ──────────────────────────────────
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

    # Gate 4: TP must clear fees with a 3x buffer
    if abs(tp - current_price) / current_price < MIN_TP_PCT:
        return None

    # ── Confidence scoring ────────────────────────────────────────────────────
    bb_pos         = (current_price - bb["middle"]) / (bb["upper"] - bb["middle"]) if bb["upper"] != bb["middle"] else 0
    momentum       = (fast_ema - slow_ema) / current_price * 100
    vol_bonus      = min(0.15, (vol_ratio - 1) * 0.1) if vol_passes else -0.1
    regime_penalty = -0.1 if regime == "HIGH_VOL" else (0.05 if regime == "NORMAL" else -0.05)

    if side == "LONG":
        scores = [
            1.0 if trend == "UPTREND" else (0.5 if trend == "RANGE" else 0.0),
            max(0, min(1, 0.5 + momentum * 5)),
            max(0, min(1, (60 - rsi) / 30)) if rsi < 60 else 0,
            1.0 if sweep == "BUY_SWEEP" else (0.6 if fast_ema > slow_ema else 0.0),
            max(0, min(1, 0.5 - bb_pos * 0.5)),
        ]
    else:
        scores = [
            1.0 if trend == "DOWNTREND" else (0.5 if trend == "RANGE" else 0.0),
            max(0, min(1, 0.5 - momentum * 5)),
            max(0, min(1, (rsi - 40) / 30)) if rsi > 40 else 0,
            1.0 if sweep == "SELL_SWEEP" else (0.6 if fast_ema < slow_ema else 0.0),
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
            "ema_26":         ema_26,
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
