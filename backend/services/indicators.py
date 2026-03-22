"""Pure technical indicator calculations (no external dependencies)."""
import math


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
