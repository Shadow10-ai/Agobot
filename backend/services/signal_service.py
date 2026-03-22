"""Signal calculation — combines indicators and filters to generate trade signals."""
from services.indicators import ema, rsi_calc, macd_calc, bollinger_bands, atr_calc
from services.filters import volume_filter, volatility_regime, structure_stop_loss
from services.binance_service import generate_candles


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

    vol_passes, vol_ratio = volume_filter(candles, multiplier=1.2)
    regime, vol_percentile, regime_size_mult = volatility_regime(candles)

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

    sweep_signal = None
    if candles[-1]['low'] < candles[-2]['low'] and candles[-1]['close'] > candles[-2]['low']:
        sweep_signal = 'BUY_SWEEP'
    elif candles[-1]['high'] > candles[-2]['high'] and candles[-1]['close'] < candles[-2]['high']:
        sweep_signal = 'SELL_SWEEP'
    elif fast_ema > slow_ema:
        sweep_signal = 'EMA_BULLISH'
    elif fast_ema < slow_ema:
        sweep_signal = 'EMA_BEARISH'

    side = None
    has_buy_signal = (
        (trend == 'UPTREND' and sweep_signal in ['BUY_SWEEP', 'EMA_BULLISH']) or
        (trend != 'DOWNTREND' and sweep_signal == 'BUY_SWEEP') or
        (fast_ema > slow_ema and rsi < 60 and rsi > 35)
    )
    if has_buy_signal and rsi <= 70:
        side = 'LONG'

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
    else:
        scores.append(1.0 if trend == 'DOWNTREND' else (0.5 if trend == 'RANGE' else 0.0))
        scores.append(max(0, min(1, 0.5 - momentum * 5)))
        scores.append(max(0, min(1, (rsi - 40) / 30)) if rsi > 40 else 0)
        scores.append(1.0 if sweep_signal == 'SELL_SWEEP' else (0.6 if sweep_signal == 'EMA_BEARISH' else 0.0))
        scores.append(max(0, min(1, 0.5 + bb_pos * 0.5)))

    scores.append(max(0, min(1, vol_bonus + 0.5)))
    scores.append(max(0, min(1, 0.5 + regime_penalty)))

    weights = [0.22, 0.18, 0.15, 0.15, 0.10, 0.10, 0.10]
    raw_score = sum(s * w for s, w in zip(scores, weights))
    prob = 0.25 + raw_score * 0.67

    if side == 'LONG':
        struct_sl = structure_stop_loss(candles, 'LONG', atr)
        sl_distance = atr * 1.2
        sl = max(struct_sl, current_price - sl_distance) if struct_sl else current_price - sl_distance
        tp = current_price + atr * 3.2
    else:
        highs = [c['high'] for c in candles[-10:]]
        swing_high = max(highs)
        sl = swing_high + (atr * 0.3) if atr else swing_high * 1.002
        sl = max(sl, current_price + atr * 1.2)
        tp = current_price - atr * 3.2
        tp = max(tp, current_price * 0.5)

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
