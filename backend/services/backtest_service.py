"""Backtest engine — historical candle generation and strategy simulation."""
import logging
import math
import random
from datetime import datetime, timezone, timedelta
import state
from services.indicators import ema, rsi_calc, macd_calc, bollinger_bands, atr_calc
from services.filters import volume_filter, volatility_regime, structure_stop_loss

logger = logging.getLogger(__name__)


def generate_historical_candles(symbol, period_days, interval_minutes=15):
    """Generate realistic historical OHLCV candles with trends, mean reversion, and volatility clustering."""
    base_price = state.SYMBOL_PRICES.get(symbol, 1000.0)
    candles_per_day = int(24 * 60 / interval_minutes)
    total_candles = period_days * candles_per_day
    candles = []
    price = base_price * random.uniform(0.85, 1.15)
    trend_direction = random.choice([-1, 1])
    trend_strength = random.uniform(0.0001, 0.0005)
    trend_duration = random.randint(50, 200)
    trend_counter = 0
    vol_base = base_price * 0.002
    vol_current = vol_base
    start_time = datetime.now(timezone.utc) - timedelta(days=period_days)
    for i in range(total_candles):
        trend_counter += 1
        if trend_counter >= trend_duration:
            trend_direction = random.choice([-1, 1])
            trend_strength = random.uniform(0.0001, 0.0008)
            trend_duration = random.randint(30, 250)
            trend_counter = 0
            vol_current = vol_base * random.uniform(0.5, 2.5)
        vol_current = vol_current * 0.95 + vol_base * 0.05 + abs(random.gauss(0, vol_base * 0.1))
        drift = trend_direction * trend_strength * price
        noise = random.gauss(0, vol_current)
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
        if vol_regime_enabled and len(candles[:i+1]) > 120:
            regime, vol_pctl, _ = volatility_regime(candles[:i+1])
            if regime != prev_regime:
                regime_changes.append({"time": current_time, "from": prev_regime, "to": regime, "percentile": vol_pctl})
                prev_regime = regime
        else:
            regime, vol_pctl = "NORMAL", 50.0
        if i % 4 == 0:
            equity_curve.append({
                "time": current_time,
                "equity": round(current_equity, 2),
                "balance": round(balance, 2),
                "drawdown": round(dd_pct, 2),
                "regime": regime
            })
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
                slip = exit_price * slippage_pct
                exit_price -= slip
                total_slippage += abs(slip * position['qty'])
                raw_pnl = (exit_price - position['entry']) * position['qty']
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
        if len(closes) < lookback:
            continue
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
        vol_passes, vol_ratio = volume_filter(window, vol_filter_mult)
        if not vol_passes:
            signals_rejected_volume += 1
            continue
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
        if vol_regime_enabled and regime == 'HIGH_VOL':
            signals_rejected_regime += 1
            effective_mult = vol_reduce_factor
        else:
            effective_mult = 1.0
        struct_sl = structure_stop_loss(window, 'LONG', atr)
        sl_price = current_price - atr * params.atr_sl_multiplier
        if struct_sl:
            sl_price = max(struct_sl, sl_price)
        tp_price = current_price + atr * params.atr_tp_multiplier
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
        balance -= entry_fee
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
    if total > 1:
        pnl_list = [t['pnl'] for t in trades]
        mean_pnl = sum(pnl_list) / len(pnl_list)
        var_pnl = sum((p - mean_pnl) ** 2 for p in pnl_list) / (len(pnl_list) - 1)
        std_pnl = math.sqrt(var_pnl) if var_pnl > 0 else 0
        sharpe = round(mean_pnl / std_pnl * math.sqrt(252) if std_pnl > 0 else 0, 2)
    else:
        sharpe = 0
    expectancy = (win_rate / 100 * avg_win + (1 - win_rate / 100) * avg_loss) if total > 0 else 0
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
