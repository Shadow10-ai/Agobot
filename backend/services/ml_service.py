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
            {
                "outcome": {"$in": ["WIN", "LOSS"]},
                "source": {"$ne": "seeded_from_trades"},  # exclude fabricated training data
            },
            {"_id": 0},
        ).to_list(10000)
        if len(labeled) < ML_MIN_SAMPLES:
            state.ml_model_state["status"] = "LEARNING"
            state.ml_model_state["training_samples"] = len(labeled)
            logger.info(f"ML: Only {len(labeled)} labeled samples (need {ML_MIN_SAMPLES}). Staying in LEARNING mode.")
            return
        # ── Symbol concentration warning ──────────────────────────────────────
        symbol_counts = {}
        for doc in labeled:
            sym = doc.get("symbol", "UNKNOWN")
            symbol_counts[sym] = symbol_counts.get(sym, 0) + 1
        total_labeled = len(labeled)
        dominant_symbol, dominant_count = max(symbol_counts.items(), key=lambda x: x[1])
        dominant_pct = dominant_count / total_labeled
        if dominant_pct > 0.5:
            logger.warning(
                f"ML SYMBOL CONCENTRATION: {dominant_symbol} accounts for "
                f"{dominant_count}/{total_labeled} ({dominant_pct:.0%}) of training samples — "
                f"model may be learning symbol-specific patterns rather than generalising"
            )

        # ── Deduplicate near-identical rows ───────────────────────────────────
        # Rows that share symbol + RSI bucket (±5) + trading session are near-duplicates
        # that can inflate CV accuracy without adding real information.
        def _session(doc):
            """Map UTC hour to a coarse trading session label."""
            try:
                hour = datetime.fromisoformat(doc.get("timestamp", "")).hour
            except Exception:
                hour = 12
            if hour < 8:
                return "ASIAN"
            elif hour < 13:
                return "LONDON"
            elif hour < 18:
                return "NEWYORK"
            else:
                return "OFFHOURS"

        seen_keys = set()
        deduped = []
        for doc in labeled:
            rsi = doc.get("rsi", 50)
            rsi_bucket = int(round(rsi / 5.0)) * 5  # round to nearest 5
            key = (doc.get("symbol", ""), rsi_bucket, _session(doc), doc.get("side", "LONG"))
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(doc)
        removed = total_labeled - len(deduped)
        if removed > 0:
            logger.info(f"ML dedup: removed {removed} near-duplicate rows ({total_labeled} → {len(deduped)})")
        labeled = deduped

        if len(labeled) < ML_MIN_SAMPLES:
            state.ml_model_state["status"] = "LEARNING"
            state.ml_model_state["training_samples"] = len(labeled)
            logger.info(f"ML: After dedup only {len(labeled)} samples (need {ML_MIN_SAMPLES}). Staying in LEARNING mode.")
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
        from sklearn.model_selection import TimeSeriesSplit, train_test_split
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

        X_df = pd.DataFrame(X, columns=ALL_ML_FEATURES)

        # ── Train/test split first — before any class-weight calculations ─────
        # Stratified split requires at least 2 samples per class; fall back to
        # a sequential split when the dataset is too small or too imbalanced.
        test_size = 0.2
        unique_classes, class_counts = np.unique(y, return_counts=True)
        can_stratify = len(unique_classes) >= 2 and np.all(class_counts >= 2)
        if can_stratify and len(y) >= ML_MIN_SAMPLES * 2:
            X_train, X_test, y_train, y_test = train_test_split(
                X_df, y, test_size=test_size, random_state=42, stratify=y
            )
        else:
            split_idx = max(1, int(len(y) * (1 - test_size)))
            X_train = X_df.iloc[:split_idx]
            X_test = X_df.iloc[split_idx:]
            y_train = y[:split_idx]
            y_test = y[split_idx:]

        # Class weights derived independently per partition so no label leakage
        train_wins = int(np.sum(y_train))
        train_losses = len(y_train) - train_wins
        train_scale_pos = train_losses / max(train_wins, 1)

        full_wins = int(np.sum(y))
        full_losses = len(y) - full_wins
        full_scale_pos = full_losses / max(full_wins, 1)

        base_params = dict(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            min_child_samples=max(5, len(y) // 15),
            reg_alpha=0.1,
            reg_lambda=0.1,
            verbose=-1,
            random_state=42,
        )

        # ── Step 1: Evaluation model — trained on X_train only ──────────────
        # scale_pos_weight from y_train; X_test rows never touch this fit.
        eval_model = lgb.LGBMClassifier(**base_params, scale_pos_weight=train_scale_pos)
        eval_model.fit(X_train, y_train)

        train_preds = eval_model.predict(X_train)
        acc = accuracy_score(y_train, train_preds)   # in-sample on training partition

        test_preds_eval = eval_model.predict(X_test)
        test_acc = accuracy_score(y_test, test_preds_eval)  # genuinely held-out

        overfit_gap = acc - test_acc
        overfit_warning = overfit_gap > 0.15
        if overfit_warning:
            logger.warning(
                f"ML OVERFIT WARNING: train_acc={acc:.3f} test_acc={test_acc:.3f} "
                f"gap={overfit_gap:.3f} — model may be memorising training data"
            )

        # ── Step 2: Cross-validation on full dataset (temporal order) ────────
        # TimeSeriesSplit ensures each fold trains on the past and validates on
        # the future — preventing the model from "peeking" at later data, which
        # inflates accuracy with random k-fold on time-ordered financial data.
        n_folds = min(5, max(2, len(y) // 10))
        tscv = TimeSeriesSplit(n_splits=n_folds)
        cv_model = lgb.LGBMClassifier(**base_params, scale_pos_weight=full_scale_pos)
        cv_scores = []
        for train_idx, val_idx in tscv.split(X_df):
            X_cv_train, X_cv_val = X_df.iloc[train_idx], X_df.iloc[val_idx]
            y_cv_train, y_cv_val = y[train_idx], y[val_idx]
            cv_model.fit(X_cv_train, y_cv_train)
            fold_preds = cv_model.predict(X_cv_val)
            cv_scores.append(accuracy_score(y_cv_val, fold_preds))
        cv_scores = np.array(cv_scores)

        # ── Step 3: Deployment model — refit on full dataset for best coverage ──
        # Metrics (acc, test_acc, overfit_warning) already captured from eval model.
        model = lgb.LGBMClassifier(**base_params, scale_pos_weight=full_scale_pos)
        model.fit(X_df, y)

        importances = model.feature_importances_
        feature_imp = {name: round(float(imp), 4) for name, imp in zip(ALL_ML_FEATURES, importances)}
        feature_imp = dict(sorted(feature_imp.items(), key=lambda x: -x[1])[:10])

        # Precision/recall/F1 from the deployment model on full data (informational)
        full_preds = model.predict(X_df)
        wins = full_wins
        losses = full_losses
        prec = precision_score(y, full_preds, zero_division=0)
        rec = recall_score(y, full_preds, zero_division=0)
        f1 = f1_score(y, full_preds, zero_division=0)

        joblib.dump(model, ML_MODEL_PATH)
        state.ml_model_state.update({
            "model": model,
            "status": "ACTIVE",
            "accuracy": round(acc, 4),
            "test_accuracy": round(test_acc, 4),
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
            "overfit_warning": overfit_warning,
        })
        logger.info(
            f"ML Model trained v{state.ml_model_state['version']}: {len(y)} samples, "
            f"train_acc={acc:.3f}, test_acc={test_acc:.3f}, gap={overfit_gap:.3f}, "
            f"prec={prec:.3f}, rec={rec:.3f}, f1={f1:.3f}, cv={np.mean(cv_scores):.3f}"
        )
        # Notify connected WebSocket clients that ML model just updated
        try:
            from services.websocket_manager import ws_manager
            asyncio.create_task(ws_manager.broadcast({
                "type": "ml_update",
                "status": "ACTIVE",
                "accuracy": round(acc, 4),
                "training_samples": len(y),
                "version": state.ml_model_state["version"],
            }))
        except Exception:
            pass
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
    """No-op.

    This function previously seeded the signal_dataset with fabricated indicator values
    (random RSI, MACD, EMA, volume etc.) paired with real WIN/LOSS outcomes.
    That poisoned the ML model — it was literally learning that random feature vectors
    predict trade outcomes, which means it learned nothing except noise.

    The ML model now trains exclusively on signals recorded by `log_signal_to_dataset`
    during live bot scans, which captures the *actual* indicator state at the time
    of entry. Do not re-enable the fabrication logic.
    """
    return


async def log_signal_to_dataset(db_ref, signal, candles, confidence, confidence_breakdown, filters_passed, trade_taken, config, mode="DRY"):
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
        "mode": mode,
        "outcome": None,
        "pnl": None,
        "pnl_percent": None,
    }
    await db_ref.signal_dataset.insert_one(dataset_entry)


async def update_dataset_outcome(db_ref, symbol, side, entry_price, pnl, pnl_pct, exit_reason, opened_at):
    """Update the signal dataset entry with trade outcome for ML training.

    The signal is logged *before* the position opens, so its timestamp is always
    earlier than `opened_at`. We match within a 10-minute look-back window.
    """
    from datetime import timedelta
    outcome = "WIN" if pnl > 0 else "LOSS"
    try:
        opened_dt = datetime.fromisoformat(opened_at)
    except Exception:
        opened_dt = datetime.now(timezone.utc)
    window_start = (opened_dt - timedelta(minutes=10)).isoformat()
    result = await db_ref.signal_dataset.update_one(
        {
            "symbol": symbol,
            "side": side,
            "trade_taken": True,
            "outcome": None,
            "timestamp": {"$gte": window_start, "$lte": opened_at},
        },
        {"$set": {"outcome": outcome, "pnl": pnl, "pnl_percent": pnl_pct, "exit_reason": exit_reason}},
    )
    if result.matched_count == 0:
        logger.warning(f"update_dataset_outcome: no signal_dataset match for {symbol} {side} opened_at={opened_at}")
    state.ml_model_state["trades_since_retrain"] += 1
    if state.ml_model_state["trades_since_retrain"] >= ML_RETRAIN_INTERVAL:
        asyncio.create_task(train_ml_model(db_ref))
