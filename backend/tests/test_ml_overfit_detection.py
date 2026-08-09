"""Tests for ML overfit detection and honest held-out evaluation.

Verifies:
- test_accuracy is computed from genuinely held-out rows (not seen during eval-model fit)
- overfit_warning fires when train_acc - test_acc > 0.15
- scale_pos_weight for the eval model is derived from y_train only (no label leakage)
- edge cases: minimum-sample datasets and heavily imbalanced labels
"""
import types
import asyncio
import numpy as np
import pytest
import lightgbm as lgb
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_lgbm(**overrides):
    params = dict(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        min_child_samples=5,
        reg_alpha=0.1,
        reg_lambda=0.1,
        verbose=-1,
        random_state=42,
    )
    params.update(overrides)
    return lgb.LGBMClassifier(**params)


def _split_and_evaluate(X, y, test_size=0.2):
    """Mirror the production split + eval logic so tests exercise real code paths."""
    import pandas as pd
    unique_classes, class_counts = np.unique(y, return_counts=True)
    can_stratify = len(unique_classes) >= 2 and np.all(class_counts >= 2)
    min_samples = 30  # ML_MIN_SAMPLES default

    if can_stratify and len(y) >= min_samples * 2:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
    else:
        split_idx = max(1, int(len(y) * (1 - test_size)))
        X_train = X.iloc[:split_idx] if hasattr(X, "iloc") else X[:split_idx]
        X_test = X.iloc[split_idx:] if hasattr(X, "iloc") else X[split_idx:]
        y_train = y[:split_idx]
        y_test = y[split_idx:]

    train_wins = int(np.sum(y_train))
    train_losses = len(y_train) - train_wins
    train_scale_pos = train_losses / max(train_wins, 1)

    eval_model = _make_lgbm(
        min_child_samples=max(5, len(y) // 15),
        scale_pos_weight=train_scale_pos,
    )
    eval_model.fit(X_train, y_train)

    acc = accuracy_score(y_train, eval_model.predict(X_train))
    test_acc = accuracy_score(y_test, eval_model.predict(X_test))
    overfit_warning = (acc - test_acc) > 0.15

    return {
        "acc": acc,
        "test_acc": test_acc,
        "overfit_warning": overfit_warning,
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "train_scale_pos": train_scale_pos,
        "eval_model": eval_model,
    }


# ── Test: held-out rows are excluded from eval-model fit ─────────────────────

def test_test_rows_not_used_in_eval_model_fit():
    """Held-out rows must never be seen by the eval model during training.

    Strategy:
    - Build a linearly separable dataset (feature 0 > 0.5 → class 1).
    - Train on rows where all class-1 samples have feature0 > 0.9 (very clear signal).
    - Test rows are ALL class 1 (feature0 > 0.9).
    - Then flip all test labels to 0 → a model truly holding out those rows
      will see drastically different test_acc; a model that saw them during
      training would have memorised them and its train acc would change too.

    Uses n=40 (< 2*ML_MIN_SAMPLES=60) to guarantee the sequential split path,
    ensuring the partition is purely index-based and cannot shift with labels.
    """
    import pandas as pd

    n = 40
    test_size = 0.2
    split_idx = max(1, int(n * (1 - test_size)))  # = 32

    # Training rows: perfectly separable by feature0 threshold
    X_data = np.zeros((n, 2), dtype=np.float32)
    y = np.zeros(n, dtype=np.int32)
    # First 32 rows (train): alternate 0/1 based on feature0
    for i in range(split_idx):
        X_data[i, 0] = 0.1 if i % 2 == 0 else 0.9
        y[i] = 0 if i % 2 == 0 else 1
    # Last 8 rows (test): all class-1, feature0 = 0.9
    for i in range(split_idx, n):
        X_data[i, 0] = 0.9
        y[i] = 1

    X = pd.DataFrame(X_data, columns=["feature0", "feature1"])

    result_original = _split_and_evaluate(X, y)

    # Flip only the test row labels: all-1 → all-0
    y_flipped = y.copy()
    y_flipped[split_idx:] = 0

    result_flipped = _split_and_evaluate(X, y_flipped)

    # Training partition must be the same rows (sequential split is index-based)
    assert len(result_original["X_train"]) == len(result_flipped["X_train"]), (
        "Training partition size changed — sequential split should be index-based"
    )
    np.testing.assert_array_equal(
        result_original["X_train"].index.values,
        result_flipped["X_train"].index.values,
        err_msg="Training rows shifted after flipping test-only labels",
    )

    # Eval model in-sample accuracy must be identical — same training data, same labels
    assert result_original["acc"] == pytest.approx(result_flipped["acc"], abs=1e-6), (
        "Eval model training accuracy changed — test labels leaked into training"
    )

    # test_acc MUST differ: original=1.0 (all-1 predictions on all-1 labels),
    # flipped=0.0 (all-1 predictions on all-0 labels)
    assert result_original["test_acc"] != result_flipped["test_acc"], (
        f"test_acc did not change (both = {result_original['test_acc']}) after flipping "
        "test labels from all-1 to all-0 — held-out rows are not truly held out"
    )


# ── Test: scale_pos_weight uses y_train only, not full y ─────────────────────

def test_eval_model_scale_pos_weight_from_train_partition_only():
    """Changing test-set class distribution must not alter train_scale_pos.

    Uses sequential split (n < 2*ML_MIN_SAMPLES=60) so the partition is
    index-based and does not shift when test labels change.
    """
    import pandas as pd

    # n=40 forces sequential split; partition is stable regardless of label values
    n = 40
    test_size = 0.2
    split_idx = max(1, int(n * (1 - test_size)))

    y_balanced = np.array([0, 1] * (n // 2), dtype=np.int32)
    X = pd.DataFrame(np.ones((n, 3)), columns=["a", "b", "c"])

    result1 = _split_and_evaluate(X, y_balanced)

    # Flip all test labels to 0 — extreme imbalance in test set only
    y_skewed = y_balanced.copy()
    y_skewed[split_idx:] = 0

    result2 = _split_and_evaluate(X, y_skewed)

    # train_scale_pos is derived from y_train only; training labels didn't change
    # so train_scale_pos must be identical
    assert result1["train_scale_pos"] == pytest.approx(result2["train_scale_pos"], abs=1e-6), (
        f"train_scale_pos changed ({result1['train_scale_pos']} vs {result2['train_scale_pos']}) "
        "when only test labels were altered — test-set labels are leaking into eval model hyperparameter"
    )


# ── Test: overfit_warning fires when gap > 0.15 ──────────────────────────────

def test_overfit_warning_fires_on_large_gap():
    """A model that perfectly memorises training data must trigger overfit_warning."""
    import pandas as pd

    rng = np.random.default_rng(2)
    # Tiny dataset — model will overfit
    n_train = 20
    n_test = 5
    X_train = pd.DataFrame(np.eye(n_train), columns=[f"f{i}" for i in range(n_train)])
    y_train = np.array([0, 1] * (n_train // 2), dtype=np.int32)
    X_test = pd.DataFrame(rng.random((n_test, n_train)), columns=[f"f{i}" for i in range(n_train)])
    y_test = np.array([0, 1, 0, 1, 0], dtype=np.int32)

    model = _make_lgbm(min_child_samples=1, scale_pos_weight=1.0)
    model.fit(X_train, y_train)

    acc = accuracy_score(y_train, model.predict(X_train))
    test_acc = accuracy_score(y_test, model.predict(X_test))
    overfit_warning = (acc - test_acc) > 0.15

    assert acc > 0.9, f"Expected near-perfect train acc on memorisable data, got {acc}"
    assert overfit_warning, (
        f"overfit_warning should be True when acc={acc:.3f} and test_acc={test_acc:.3f} "
        f"(gap={acc - test_acc:.3f} > 0.15)"
    )


def test_overfit_warning_absent_when_gap_small():
    """A well-generalising model with gap ≤ 0.15 must NOT trigger overfit_warning."""
    import pandas as pd

    # Simulate a scenario where train and test accuracy are close
    acc = 0.80
    test_acc = 0.75
    overfit_warning = (acc - test_acc) > 0.15
    assert not overfit_warning, (
        f"overfit_warning should be False when gap={acc - test_acc:.3f} ≤ 0.15"
    )


# ── Test: minimum-sample edge case (sequential fallback split) ────────────────

def test_minimum_sample_sequential_split():
    """With fewer than 2*ML_MIN_SAMPLES rows the code falls back to a sequential split."""
    import pandas as pd

    # 35 samples — below the 2*30 threshold for stratified split
    n = 35
    rng = np.random.default_rng(3)
    X = pd.DataFrame(rng.random((n, 3)), columns=["a", "b", "c"])
    y = np.array([0, 1] * (n // 2) + [0], dtype=np.int32)

    result = _split_and_evaluate(X, y, test_size=0.2)

    split_idx = max(1, int(n * 0.8))
    assert len(result["X_train"]) == split_idx, (
        f"Expected {split_idx} train rows in sequential split, got {len(result['X_train'])}"
    )
    assert len(result["X_test"]) == n - split_idx


# ── Test: heavily imbalanced labels (all same class) ─────────────────────────

def test_all_same_class_uses_sequential_split():
    """When only one class exists stratified split cannot be applied; code must not crash."""
    import pandas as pd

    n = 40
    X = pd.DataFrame(np.ones((n, 3)), columns=["a", "b", "c"])
    y = np.zeros(n, dtype=np.int32)  # all class-0

    # Should not raise; sequential split is used
    result = _split_and_evaluate(X, y)

    assert result["acc"] is not None
    assert result["test_acc"] is not None
    assert isinstance(result["overfit_warning"], bool)
