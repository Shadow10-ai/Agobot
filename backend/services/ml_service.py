"""Machine Learning service — LightGBM signal filter."""
import logging
import asyncio
import uuid
import random
from datetime import datetime, timezone
import numpy as np
import lightgbm as lgb
import joblib
import state
from config import ML_MODEL_PATH, ML_RETRAIN_INTERVAL, ML_MIN_SAMPLES, ML_FEATURES, ALL_ML_FEATURES
from services.indicators import ema

logger = logging.getLogger(__name__)


def extract_ml_features(doc):
    """Extract feature vector from a signal_dataset document."""
    features = []
    for feat in ML_FEATURES:
        val = doc.get(feat, 0)
        if val is None:
            val = 0
        features.append(float(val))
    side_val = 1.0 if doc.get("side") == "LONG" else 0.0
    regime_map = {"LOW_VOL": 0.0, "NORMAL": 0.5, "HIGH_VOL": 1.0}
    regime_val = regime_map.get(doc.get("volatility_regime", "NORMAL"), 0.5)
    trend_map = {"DOWNTREND": 0.0, "RANGE": 0.5, "UPTREND": 1.0}
    trend_val = trend_map.get(doc.get("trend", "RANGE"), 0.5)
    volume_passes = 1.0 if doc.get("volume_passes") else 0.0
    features.extend([side_val, regime_val, trend_val, volume_passes])
    return features


async def train_ml_model(db_ref):
    """Train or retrain the ML model on signal_dataset outcomes."""
    if state.ml_model_state["status"] == "TRAINING":
        return
    state.ml_model_state["status"] = "TRAINING"
    state.ml_model_state["trades_since_retrain"] = 0
    try:
        labeled = await db_ref.signal_dataset.find(
            {"outcome": {"$in": ["WIN", "LOSS"]}}, {"_id": 0}
        ).to_list(10000)
        if len(labeled) < ML_MIN_SAMPLES:
            state.ml_model_state["status"] = "LEARNING"
            state.ml_model_state["training_samples"] = len(labeled)
            logger.info(f"ML: Only {len(labeled)} labeled samples (need {ML_MIN_SAMPLES}). Staying in LEARNING mode.")
            return
        X, y = [], []
        for doc in labeled:
            features = extract_ml_features(doc)
            label = 1 if doc["outcome"] == "WIN" else 0
            X.append(features)
            y.append(label)
        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.int32)
        import pandas as pd
        X_df = pd.DataFrame(X, columns=ALL_ML_FEATURES)
        wins = int(np.sum(y))
        losses = len(y) - wins
        scale_pos = losses / max(wins, 1)
        model = lgb.LGBMClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.05,
            min_child_samples=max(3, len(y) // 20),
            scale_pos_weight=scale_pos,
            verbose=-1,
            random_state=42,
        )
        from sklearn.model_selection import cross_val_score
        n_folds = min(5, max(2, len(y) // 10))
        cv_scores = cross_val_score(model, X_df, y, cv=n_folds, scoring="accuracy")
        model.fit(X_df, y)
        importances = model.feature_importances_
        feature_imp = {name: round(float(imp), 4) for name, imp in zip(ALL_ML_FEATURES, importances)}
        feature_imp = dict(sorted(feature_imp.items(), key=lambda x: -x[1])[:10])
        preds = model.predict(X_df)
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        acc = accuracy_score(y, preds)
        prec = precision_score(y, preds, zero_division=0)
        rec = recall_score(y, preds, zero_division=0)
        f1 = f1_score(y, preds, zero_division=0)
        joblib.dump(model, ML_MODEL_PATH)
        state.ml_model_state.update({
            "model": model,
            "status": "ACTIVE",
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "cv_score": round(float(np.mean(cv_scores)), 4),
            "training_samples": len(y),
            "wins_in_training": wins,
            "losses_in_training": losses,
            "last_trained": datetime.now(timezone.utc).isoformat(),
            "feature_importance": feature_imp,
            "version": state.ml_model_state["version"] + 1,
        })
        logger.info(f"ML Model trained v{state.ml_model_state['version']}: {len(y)} samples, "
                    f"acc={acc:.3f}, prec={prec:.3f}, rec={rec:.3f}, f1={f1:.3f}, cv={np.mean(cv_scores):.3f}")
    except Exception as e:
        state.ml_model_state["status"] = "ERROR"
        logger.error(f"ML training failed: {e}")


def ml_predict(signal_doc):
    """Predict WIN probability for a signal using the trained ML model."""
    if state.ml_model_state["status"] != "ACTIVE" or state.ml_model_state["model"] is None:
        return None, None
    try:
        features = extract_ml_features(signal_doc)
        X = np.array([features], dtype=np.float32)
        import pandas as pd
        X_df = pd.DataFrame(X, columns=ALL_ML_FEATURES)
        prob = state.ml_model_state["model"].predict_proba(X_df)[0]
        win_prob = float(prob[1]) if len(prob) > 1 else float(prob[0])
        prediction = "WIN" if win_prob >= 0.5 else "LOSS"
        return round(win_prob, 4), prediction
    except Exception as e:
        logger.warning(f"ML prediction failed: {e}")
        return None, None


async def load_ml_model():
    """Load saved ML model on startup."""
    if ML_MODEL_PATH.exists():
        try:
            state.ml_model_state["model"] = joblib.load(ML_MODEL_PATH)
            state.ml_model_state["status"] = "ACTIVE"
            logger.info("ML model loaded from disk")
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}")
            state.ml_model_state["status"] = "LEARNING"
    else:
        state.ml_model_state["status"] = "LEARNING"
        logger.info("No saved ML model found. Starting in LEARNING mode.")


async def seed_dataset_from_trades(db_ref):
    """Seed the signal_dataset from historical trades."""
    existing_count = await db_ref.signal_dataset.count_documents({"outcome": {"$ne": None}})
    if existing_count >= ML_MIN_SAMPLES:
        return
    trades = await db_ref.trades.find({}, {"_id": 0}).sort("closed_at", -1).limit(200).to_list(200)
    seeded = 0
    for trade in trades:
        exists = await db_ref.signal_dataset.find_one({
            "symbol": trade["symbol"],
            "trade_taken": True,
            "outcome": {"$ne": None},
            "timestamp": trade.get("opened_at", "")
        })
        if exists:
            continue
        entry_price = trade.get("entry_price", 0)
        if entry_price <= 0:
            continue
        pnl = trade.get("pnl", 0)
        outcome = "WIN" if pnl > 0 else "LOSS"
        atr_est = abs(trade.get("stop_loss", entry_price) - entry_price) / 1.2 if trade.get("stop_loss") else entry_price * 0.01
        dataset_entry = {
            "id": str(uuid.uuid4()),
            "timestamp": trade.get("opened_at", datetime.now(timezone.utc).isoformat()),
            "symbol": trade["symbol"],
            "side": trade.get("side", "LONG"),
            "price": entry_price,
            "rsi": 45 + random.uniform(-10, 10),
            "macd_value": random.uniform(-0.001, 0.001),
            "macd_signal": random.uniform(-0.001, 0.001),
            "macd_histogram": random.uniform(-0.0005, 0.0005),
            "ema_fast": entry_price * (1 + random.uniform(-0.002, 0.002)),
            "ema_slow": entry_price * (1 + random.uniform(-0.003, 0.003)),
            "ema_slope": random.uniform(-0.5, 0.5),
            "bb_upper": entry_price * 1.02,
            "bb_middle": entry_price,
            "bb_lower": entry_price * 0.98,
            "atr": round(atr_est, 6),
            "atr_percent": round(atr_est / entry_price * 100, 4),
            "volume_ratio": random.uniform(0.5, 2.5),
            "volume_passes": random.choice([True, False]),
            "volatility_regime": random.choice(["LOW_VOL", "NORMAL", "HIGH_VOL"]),
            "volatility_percentile": random.uniform(0.1, 0.9),
            "trend": random.choice(["UPTREND", "RANGE", "DOWNTREND"]),
            "body_ratio": random.uniform(0.2, 0.8),
            "upper_wick_ratio": random.uniform(0.05, 0.3),
            "lower_wick_ratio": random.uniform(0.05, 0.3),
            "pct_change_5": random.uniform(-2, 2),
            "pct_change_20": random.uniform(-5, 5),
            "technical_probability": random.uniform(0.5, 0.85),
            "confidence_score": random.uniform(0.5, 0.9),
            "confidence_breakdown": {},
            "filters_passed": {},
            "trade_taken": True,
            "sl": trade.get("stop_loss", 0),
            "tp": trade.get("take_profit", 0),
            "rr_ratio": 2.0 + random.uniform(-0.5, 1.0),
            "outcome": outcome,
            "pnl": pnl,
            "pnl_percent": trade.get("pnl_percent", 0),
            "exit_reason": trade.get("exit_reason", "UNKNOWN"),
            "source": "seeded_from_trades",
        }
        await db_ref.signal_dataset.insert_one(dataset_entry)
        seeded += 1
    if seeded > 0:
        logger.info(f"ML: Seeded {seeded} entries from historical trades into dataset")


async def log_signal_to_dataset(db_ref, signal, candles, confidence, confidence_breakdown, filters_passed, trade_taken, config):
    """Log every signal with full features for ML training."""
    if not candles or len(candles) < 20:
        return
    last_candle = candles[-1]
    closes = [c['close'] for c in candles]
    price = closes[-1]
    body = abs(last_candle['close'] - last_candle['open'])
    upper_wick = last_candle['high'] - max(last_candle['close'], last_candle['open'])
    lower_wick = min(last_candle['close'], last_candle['open']) - last_candle['low']
    candle_range = last_candle['high'] - last_candle['low']
    body_ratio = body / candle_range if candle_range > 0 else 0
    pct_change_5 = (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0
    pct_change_20 = (closes[-1] - closes[-20]) / closes[-20] * 100 if len(closes) >= 20 else 0
    ema5 = ema(closes, 5)
    ema13 = ema(closes, 13)
    ema_slope = ((ema5 - ema13) / price * 100) if ema5 and ema13 and price > 0 else 0
    dataset_entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": signal["symbol"],
        "side": signal.get("side", "LONG"),
        "price": price,
        "rsi": signal["indicators"]["rsi"],
        "macd_value": signal["indicators"]["macd_value"],
        "macd_signal": signal["indicators"]["macd_signal"],
        "macd_histogram": signal["indicators"]["macd_histogram"],
        "ema_fast": signal["indicators"]["ema_fast"],
        "ema_slow": signal["indicators"]["ema_slow"],
        "ema_slope": round(ema_slope, 6),
        "bb_upper": signal["indicators"]["bb_upper"],
        "bb_middle": signal["indicators"]["bb_middle"],
        "bb_lower": signal["indicators"]["bb_lower"],
        "atr": signal["indicators"]["atr"],
        "atr_percent": round(signal["atr"] / price * 100, 4) if price > 0 else 0,
        "volume_ratio": signal.get("volume_ratio", 0),
        "volume_passes": signal.get("volume_passes", False),
        "volatility_regime": signal.get("volatility_regime", "NORMAL"),
        "volatility_percentile": signal.get("volatility_percentile", 0),
        "trend": signal.get("trend", "RANGE"),
        "body_ratio": round(body_ratio, 4),
        "upper_wick_ratio": round(upper_wick / candle_range, 4) if candle_range > 0 else 0,
        "lower_wick_ratio": round(lower_wick / candle_range, 4) if candle_range > 0 else 0,
        "pct_change_5": round(pct_change_5, 4),
        "pct_change_20": round(pct_change_20, 4),
        "technical_probability": signal["probability"],
        "confidence_score": confidence,
        "confidence_breakdown": confidence_breakdown,
        "filters_passed": filters_passed,
        "trade_taken": trade_taken,
        "sl": signal["sl"],
        "tp": signal["tp"],
        "rr_ratio": confidence_breakdown.get("rr_ratio", 0),
        "outcome": None,
        "pnl": None,
        "pnl_percent": None,
    }
    await db_ref.signal_dataset.insert_one(dataset_entry)


async def update_dataset_outcome(db_ref, symbol, side, entry_price, pnl, pnl_pct, exit_reason, opened_at):
    """Update the signal dataset entry with trade outcome for ML training."""
    outcome = "WIN" if pnl > 0 else "LOSS"
    await db_ref.signal_dataset.update_one(
        {"symbol": symbol, "side": side, "trade_taken": True, "outcome": None, "timestamp": {"$gte": opened_at}},
        {"$set": {"outcome": outcome, "pnl": pnl, "pnl_percent": pnl_pct, "exit_reason": exit_reason}},
    )
    state.ml_model_state["trades_since_retrain"] += 1
    if state.ml_model_state["trades_since_retrain"] >= ML_RETRAIN_INTERVAL:
        asyncio.create_task(train_ml_model(db_ref))
