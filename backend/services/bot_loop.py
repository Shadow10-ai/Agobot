"""Bot background scan loop — main trading engine."""
import logging
import asyncio
import uuid
import random
from datetime import datetime, timezone
import state
from database import db
from services.binance_service import fetch_live_price, fetch_live_candles, generate_candles, place_live_market_order
from services.signal_service import calculate_signal
from services.filters import (
    check_correlation_exposure, check_spread, estimate_slippage,
    check_min_liquidity, check_risk_reward, multi_timeframe_trend,
    check_cooldown, check_overtrade_limits, calculate_confidence_score,
    update_cooldown, increment_cooldown
)
from services.ml_service import ml_predict, log_signal_to_dataset, update_dataset_outcome
from services.risk_service import check_circuit_breaker, check_trading_session, detect_market_regime_advanced

logger = logging.getLogger(__name__)


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
        "allow_short": False,
        "max_trades_per_hour": 5,
        "max_trades_per_day": 15,
        "min_risk_reward_ratio": 2.5,
        "cooldown_after_loss_scans": 6,
        "min_confidence_score": 0.60,
        "spread_max_percent": 0.15,
        "min_24h_volume_usdt": 1000000,
        "max_slippage_percent": 0.1,
        "require_trend_alignment": True,
        "ml_min_win_probability": 0.55,
        "allowed_sessions": ["ASIA", "LONDON", "NYC"],
        "telegram_token": "",
        "telegram_chat_id": ""
    }
    await db.bot_config.update_one({"active": True}, {"$set": config}, upsert=True)
    return config


async def bot_scan_loop():
    """Main bot scan loop - runs as background task. Supports DRY and LIVE modes."""
    logger.info("Bot scan loop started")
    while state.bot_state["running"]:
        if state.bot_state["paused"]:
            await asyncio.sleep(5)
            continue
        try:
            config = await db.bot_config.find_one({"active": True}, {"_id": 0})
            if not config:
                config = await get_default_config()
            current_mode = config.get("mode", "DRY")
            state.bot_state["mode"] = current_mode
            is_live = current_mode == "LIVE" and state.binance_client is not None
            symbols = config.get("symbols", ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT'])
            min_prob = config.get("min_entry_probability", 0.65)
            base_usdt = config.get("base_usdt_per_trade", 50)
            allow_short = config.get("allow_short", False)
            if is_live:
                for symbol in symbols:
                    try:
                        live_price = await fetch_live_price(symbol)
                        state.SYMBOL_PRICES[symbol] = live_price
                    except Exception as e:
                        logger.warning(f"Failed to fetch live price for {symbol}: {e}")
            else:
                for symbol in symbols:
                    if symbol in state.SYMBOL_PRICES:
                        change = random.gauss(0, state.SYMBOL_PRICES[symbol] * 0.001)
                        state.SYMBOL_PRICES[symbol] = round(max(0.01, state.SYMBOL_PRICES[symbol] + change), 8)
            positions = await db.positions.find({"status": "OPEN"}, {"_id": 0}).to_list(100)
            for pos in positions:
                symbol = pos["symbol"]
                pos_side = pos.get("side", "LONG")
                current_price = state.SYMBOL_PRICES.get(symbol, pos["entry_price"])
                exit_reason = None
                exit_price = current_price
                if pos_side == "LONG":
                    if current_price <= pos["stop_loss"]:
                        exit_reason = "STOP_LOSS"
                        exit_price = pos["stop_loss"]
                    elif current_price >= pos["take_profit"]:
                        exit_reason = "TAKE_PROFIT"
                        exit_price = pos["take_profit"]
                else:
                    if current_price >= pos["stop_loss"]:
                        exit_reason = "STOP_LOSS"
                        exit_price = pos["stop_loss"]
                    elif current_price <= pos["take_profit"]:
                        exit_reason = "TAKE_PROFIT"
                        exit_price = pos["take_profit"]
                if not exit_reason and pos.get("trail_activated"):
                    trail_distance = pos["atr"] * config.get("trailing_stop_distance_pips", 1.2)
                    if pos_side == "LONG":
                        new_sl = current_price - trail_distance
                        if new_sl > pos["stop_loss"]:
                            await db.positions.update_one({"id": pos["id"]}, {"$set": {"stop_loss": round(new_sl, 8)}})
                        if current_price <= pos["stop_loss"]:
                            exit_reason = "TRAIL_STOP"
                            exit_price = pos["stop_loss"]
                    else:
                        new_sl = current_price + trail_distance
                        if new_sl < pos["stop_loss"]:
                            await db.positions.update_one({"id": pos["id"]}, {"$set": {"stop_loss": round(new_sl, 8)}})
                        if current_price >= pos["stop_loss"]:
                            exit_reason = "TRAIL_STOP"
                            exit_price = pos["stop_loss"]
                if not exit_reason and not pos.get("trail_activated"):
                    activation_atr = pos["atr"] * config.get("trailing_stop_activate_pips", 2.4)
                    if pos_side == "LONG":
                        if current_price >= pos["entry_price"] + activation_atr:
                            await db.positions.update_one({"id": pos["id"]}, {"$set": {"trail_activated": True}})
                    else:
                        if current_price <= pos["entry_price"] - activation_atr:
                            await db.positions.update_one({"id": pos["id"]}, {"$set": {"trail_activated": True}})
                if exit_reason:
                    if is_live and pos.get("mode") == "LIVE":
                        try:
                            close_side = "SELL" if pos_side == "LONG" else "BUY"
                            close_result = await place_live_market_order(symbol, close_side, pos["quantity"] * exit_price)
                            exit_price = close_result.get("avg_price", exit_price)
                            logger.info(f"LIVE {close_side} {symbol}: order {close_result['order_id']}, filled {close_result['executed_qty']}")
                        except Exception as e:
                            logger.error(f"LIVE close failed for {symbol}, using market price: {e}")
                    if pos_side == "LONG":
                        pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
                        pnl_percent = ((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100
                    else:
                        pnl = (pos["entry_price"] - exit_price) * pos["quantity"]
                        pnl_percent = ((pos["entry_price"] - exit_price) / pos["entry_price"]) * 100
                    now = datetime.now(timezone.utc).isoformat()
                    await db.positions.update_one(
                        {"id": pos["id"]},
                        {"$set": {"status": "CLOSED", "exit_price": round(exit_price, 8), "exit_reason": exit_reason, "pnl": round(pnl, 4), "pnl_percent": round(pnl_percent, 4), "closed_at": now}}
                    )
                    trade_doc = {
                        "id": str(uuid.uuid4()),
                        "symbol": symbol,
                        "side": pos_side,
                        "entry_price": pos["entry_price"],
                        "exit_price": round(exit_price, 8),
                        "quantity": pos["quantity"],
                        "pnl": round(pnl, 4),
                        "pnl_percent": round(pnl_percent, 4),
                        "exit_reason": exit_reason,
                        "opened_at": pos["opened_at"],
                        "closed_at": now,
                        "mode": pos.get("mode", "DRY"),
                        "stop_loss": pos["stop_loss"],
                        "take_profit": pos["take_profit"]
                    }
                    await db.trades.insert_one(trade_doc)
                    await db.bot_state.update_one(
                        {"key": "daily_pnl"},
                        {"$inc": {"value": round(pnl, 4)}},
                        upsert=True
                    )
                    logger.info(f"[{pos.get('mode','DRY')}] Closed {symbol} via {exit_reason}: PnL {pnl:.4f} USDT")
                    update_cooldown(pnl < 0)
                    await update_dataset_outcome(db, symbol, pos_side, pos["entry_price"], round(pnl, 4), round(pnl_percent, 4), exit_reason, pos["opened_at"])
                else:
                    if pos_side == "LONG":
                        unrealized = (current_price - pos["entry_price"]) * pos["quantity"]
                        unrealized_pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
                    else:
                        unrealized = (pos["entry_price"] - current_price) * pos["quantity"]
                        unrealized_pct = ((pos["entry_price"] - current_price) / pos["entry_price"]) * 100
                    await db.positions.update_one(
                        {"id": pos["id"]},
                        {"$set": {"current_price": round(current_price, 8), "unrealized_pnl": round(unrealized, 4), "unrealized_pnl_percent": round(unrealized_pct, 4)}}
                    )
            increment_cooldown()
            cb_ok, current_dd = await check_circuit_breaker(db, config)
            if not cb_ok:
                if state.bot_state["scan_count"] % 30 == 0:
                    logger.warning(f"Circuit breaker active: {current_dd}% drawdown. Bot paused.")
                await asyncio.sleep(10)
                continue
            open_count = await db.positions.count_documents({"status": "OPEN"})
            if open_count < 3:
                session_ok, active_session = check_trading_session(config)
                if not session_ok:
                    if state.bot_state["scan_count"] % 30 == 0:
                        logger.info(f"Outside trading session (current: {active_session})")
                elif True:
                    sample_symbol = symbols[0] if symbols else "BTCUSDT"
                    sample_candles = generate_candles(sample_symbol, 60) if not is_live else None
                    if is_live:
                        try:
                            sample_candles = await fetch_live_candles(sample_symbol, interval="3m", limit=60)
                        except Exception:
                            sample_candles = generate_candles(sample_symbol, 60)
                    adv_regime, regime_strength, regime_details = detect_market_regime_advanced(sample_candles)
                    if adv_regime == "VOLATILE" and regime_strength > 0.8:
                        if state.bot_state["scan_count"] % 10 == 0:
                            logger.info(f"Market too volatile ({regime_strength:.2f}). Waiting for calmer conditions.")
                    else:
                        ot_ok, trades_hr, max_hr, trades_day, max_day = await check_overtrade_limits(db, config)
                        if not ot_ok:
                            if state.bot_state["scan_count"] % 30 == 0:
                                logger.info(f"Overtrade limit: {trades_hr}/{max_hr} per hour, {trades_day}/{max_day} per day")
                else:
                    cd_ok, cd_scans, cd_required = check_cooldown(config)
                    if not cd_ok:
                        if state.bot_state["scan_count"] % 10 == 0:
                            logger.info(f"Cooldown active: {cd_scans}/{cd_required} scans since last loss")
                    else:
                        for symbol in symbols:
                            if await db.positions.find_one({"symbol": symbol, "status": "OPEN"}):
                                continue
                            can_open, corr_info = await check_correlation_exposure(symbol, db)
                            if not can_open:
                                continue
                            candles_for_signal = None
                            if is_live:
                                try:
                                    candles_for_signal = await fetch_live_candles(symbol, interval="3m", limit=60)
                                except Exception as e:
                                    logger.warning(f"Failed to fetch live candles for {symbol}: {e}")
                            signal = calculate_signal(symbol, candles_for_signal, allow_short=allow_short)
                            if not signal:
                                continue
                            candles_used = candles_for_signal if candles_for_signal else generate_candles(symbol, 60)
                            signal_side = signal.get("side", "LONG")
                            filters_passed = {}
                            all_pass = True
                            if signal["probability"] < min_prob:
                                filters_passed["min_probability"] = False
                                all_pass = False
                            else:
                                filters_passed["min_probability"] = True
                            if not signal.get("volume_passes", True):
                                filters_passed["volume"] = False
                                all_pass = False
                            else:
                                filters_passed["volume"] = True
                            spread_ok, spread_pct = check_spread(candles_used, config.get("spread_max_percent", 0.15))
                            filters_passed["spread"] = spread_ok
                            if not spread_ok:
                                all_pass = False
                            regime_mult = signal.get("regime_size_multiplier", 1.0)
                            adjusted_usdt = base_usdt * regime_mult
                            slip_ok, slip_pct = estimate_slippage(candles_used, adjusted_usdt, config.get("max_slippage_percent", 0.1))
                            filters_passed["slippage"] = slip_ok
                            if not slip_ok:
                                all_pass = False
                            liq_ok, est_vol = check_min_liquidity(candles_used, config.get("min_24h_volume_usdt", 1_000_000))
                            filters_passed["liquidity"] = liq_ok
                            if not liq_ok:
                                all_pass = False
                            rr_ok, rr_ratio = check_risk_reward(
                                signal["price"], signal["sl"], signal["tp"], signal_side,
                                config.get("min_risk_reward_ratio", 2.5)
                            )
                            filters_passed["risk_reward"] = rr_ok
                            if not rr_ok:
                                all_pass = False
                            if config.get("require_trend_alignment", True):
                                trend_ok, htf_trend = multi_timeframe_trend(candles_used, signal_side)
                                filters_passed["trend_alignment"] = trend_ok
                                if not trend_ok:
                                    all_pass = False
                            else:
                                filters_passed["trend_alignment"] = True
                            confidence, conf_breakdown = calculate_confidence_score(signal, candles_used, config)
                            min_conf = config.get("min_confidence_score", 0.60)
                            filters_passed["confidence"] = confidence >= min_conf
                            if confidence < min_conf:
                                all_pass = False
                            ml_win_prob, ml_prediction = None, None
                            if state.ml_model_state["status"] == "ACTIVE":
                                ml_doc = {
                                    "rsi": signal["indicators"]["rsi"],
                                    "macd_value": signal["indicators"]["macd_value"],
                                    "macd_signal": signal["indicators"]["macd_signal"],
                                    "macd_histogram": signal["indicators"]["macd_histogram"],
                                    "ema_slope": round(((signal["indicators"]["ema_fast"] - signal["indicators"]["ema_slow"]) / signal["price"] * 100), 6) if signal["price"] > 0 else 0,
                                    "atr_percent": round(signal["atr"] / signal["price"] * 100, 4) if signal["price"] > 0 else 0,
                                    "volume_ratio": signal.get("volume_ratio", 0),
                                    "volatility_percentile": signal.get("volatility_percentile", 0),
                                    "body_ratio": abs(candles_used[-1]["close"] - candles_used[-1]["open"]) / max(candles_used[-1]["high"] - candles_used[-1]["low"], 0.0001),
                                    "upper_wick_ratio": (candles_used[-1]["high"] - max(candles_used[-1]["close"], candles_used[-1]["open"])) / max(candles_used[-1]["high"] - candles_used[-1]["low"], 0.0001),
                                    "lower_wick_ratio": (min(candles_used[-1]["close"], candles_used[-1]["open"]) - candles_used[-1]["low"]) / max(candles_used[-1]["high"] - candles_used[-1]["low"], 0.0001),
                                    "pct_change_5": round(([c["close"] for c in candles_used][-1] - [c["close"] for c in candles_used][-5]) / [c["close"] for c in candles_used][-5] * 100, 4) if len(candles_used) >= 5 else 0,
                                    "pct_change_20": round(([c["close"] for c in candles_used][-1] - [c["close"] for c in candles_used][-20]) / [c["close"] for c in candles_used][-20] * 100, 4) if len(candles_used) >= 20 else 0,
                                    "technical_probability": signal["probability"],
                                    "confidence_score": confidence,
                                    "rr_ratio": conf_breakdown.get("rr_ratio", 0),
                                    "side": signal_side,
                                    "volatility_regime": signal.get("volatility_regime", "NORMAL"),
                                    "trend": signal.get("trend", "RANGE"),
                                    "volume_passes": signal.get("volume_passes", False),
                                }
                                ml_win_prob, ml_prediction = ml_predict(ml_doc)
                                if ml_win_prob is not None:
                                    ml_threshold = config.get("ml_min_win_probability", 0.55)
                                    filters_passed["ml_filter"] = ml_win_prob >= ml_threshold
                                    if ml_win_prob < ml_threshold:
                                        all_pass = False
                                else:
                                    filters_passed["ml_filter"] = True
                            else:
                                filters_passed["ml_filter"] = True
                            await log_signal_to_dataset(db, signal, candles_used, confidence, conf_breakdown, filters_passed, all_pass, config)
                            if not all_pass:
                                failed = [k for k, v in filters_passed.items() if not v]
                                if state.bot_state["scan_count"] % 5 == 0:
                                    ml_info = f" ml={ml_win_prob:.3f}" if ml_win_prob else ""
                                    logger.info(f"Signal rejected {symbol} {signal_side}: failed [{', '.join(failed)}] conf={confidence:.3f}{ml_info}")
                                continue
                            quantity = round(adjusted_usdt / signal["price"], 8)
                            entry_price = signal["price"]
                            if is_live:
                                try:
                                    order_side = "BUY" if signal_side == "LONG" else "SELL"
                                    result = await place_live_market_order(symbol, order_side, adjusted_usdt)
                                    quantity = result["executed_qty"]
                                    entry_price = result["avg_price"]
                                    logger.info(f"LIVE {order_side} {symbol}: order {result['order_id']}, filled {quantity} @ {entry_price}")
                                except Exception as e:
                                    logger.error(f"LIVE {signal_side} order failed for {symbol}: {e}")
                                    continue
                            now = datetime.now(timezone.utc).isoformat()
                            position_doc = {
                                "id": str(uuid.uuid4()),
                                "symbol": symbol,
                                "side": signal_side,
                                "entry_price": round(entry_price, 8),
                                "current_price": round(entry_price, 8),
                                "stop_loss": round(signal["sl"], 8),
                                "take_profit": round(signal["tp"], 8),
                                "quantity": quantity,
                                "atr": round(signal["atr"], 8),
                                "probability": round(signal["probability"], 4),
                                "confidence_score": confidence,
                                "status": "OPEN",
                                "trail_activated": False,
                                "unrealized_pnl": 0.0,
                                "unrealized_pnl_percent": 0.0,
                                "opened_at": now,
                                "mode": current_mode,
                                "indicators": signal["indicators"],
                                "volume_ratio": signal.get("volume_ratio", 0),
                                "volatility_regime": signal.get("volatility_regime", "NORMAL"),
                                "correlation_group": corr_info["group"],
                                "filters_passed": filters_passed,
                                "confidence_breakdown": conf_breakdown,
                                "ml_win_probability": ml_win_prob,
                                "ml_prediction": ml_prediction,
                                "market_regime": adv_regime,
                                "regime_strength": regime_strength,
                                "session": active_session,
                            }
                            await db.positions.insert_one(position_doc)
                            logger.info(f"[{current_mode}] Opened {signal_side} {symbol} @ {entry_price:.8f}, Conf: {confidence:.3f}, R:R: {conf_breakdown['rr_ratio']}")
                            break
            state.bot_state["scan_count"] += 1
            state.bot_state["last_scan"] = datetime.now(timezone.utc).isoformat()
            if state.bot_state["scan_count"] % 3 == 0:
                price_snapshot = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "prices": {s: state.SYMBOL_PRICES.get(s, 0) for s in symbols}
                }
                await db.price_history.insert_one(price_snapshot)
                from datetime import timedelta
                cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                await db.price_history.delete_many({"timestamp": {"$lt": cutoff}})
        except Exception as e:
            logger.error(f"Bot scan error: {e}")
        await asyncio.sleep(10)
    logger.info("Bot scan loop stopped")


async def start_bot():
    if state.bot_state["running"]:
        return
    state.bot_state["running"] = True
    state.bot_state["paused"] = False
    state.bot_state["started_at"] = datetime.now(timezone.utc).isoformat()
    state.bot_task = asyncio.create_task(bot_scan_loop())
    logger.info("Bot started")


async def stop_bot():
    state.bot_state["running"] = False
    if state.bot_task:
        state.bot_task.cancel()
        state.bot_task = None
    logger.info("Bot stopped")
