"""
Integration test: DRY trade close → signal_dataset outcome labeling.

Opens a synthetic DRY signal entry in signal_dataset, simulates a position
close by calling update_dataset_outcome(), then asserts the record is labeled
WIN or LOSS.  Requires a live MongoDB connection (MONGO_URL / DB_NAME env vars).
"""
import asyncio
import os
import uuid
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Ensure backend package root is on the path when running from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    """Return a fresh Motor database handle (one per test for a clean event loop)."""
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(
        mongo_url,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
    )
    return client[db_name]


def _signal_entry(symbol: str, side: str, opened_at: str, trade_taken: bool = True) -> dict:
    """Return a minimal signal_dataset document suitable for outcome matching."""
    return {
        "id": str(uuid.uuid4()),
        "timestamp": opened_at,
        "symbol": symbol,
        "side": side,
        "price": 50_000.0,
        "rsi": 45.0,
        "macd_value": 0.0,
        "macd_signal": 0.0,
        "macd_histogram": 0.0,
        "ema_fast": 50_000.0,
        "ema_slow": 49_900.0,
        "ema_slope": 0.2,
        "bb_upper": 51_000.0,
        "bb_middle": 50_000.0,
        "bb_lower": 49_000.0,
        "atr": 500.0,
        "atr_percent": 1.0,
        "volume_ratio": 1.2,
        "volume_passes": True,
        "volatility_regime": "NORMAL",
        "volatility_percentile": 50.0,
        "trend": "UPTREND",
        "body_ratio": 0.6,
        "upper_wick_ratio": 0.2,
        "lower_wick_ratio": 0.2,
        "pct_change_5": 0.5,
        "pct_change_20": 1.0,
        "technical_probability": 0.72,
        "confidence_score": 0.75,
        "confidence_breakdown": {"rr_ratio": 2.5},
        "filters_passed": {},
        "trade_taken": trade_taken,
        "sl": 49_500.0,
        "tp": 51_000.0,
        "rr_ratio": 2.5,
        "mode": "DRY",
        "outcome": None,
        "pnl": None,
        "pnl_percent": None,
    }


# ---------------------------------------------------------------------------
# Helper: run an async test body on its own event loop
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine to completion on a fresh event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests (plain synchronous — each creates its own Motor client so no
# event-loop sharing problem between tests)
# ---------------------------------------------------------------------------

def test_win_outcome_labeled():
    """Closing a DRY position with positive PnL labels the dataset entry as WIN."""
    from services.ml_service import update_dataset_outcome

    db = _make_db()
    symbol = "BTCUSDT"
    side = "LONG"
    opened_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    entry = _signal_entry(symbol, side, opened_at)

    async def _run():
        await db.signal_dataset.insert_one(entry)
        try:
            await update_dataset_outcome(
                db_ref=db,
                symbol=symbol,
                side=side,
                entry_price=50_000.0,
                pnl=20.0,
                pnl_pct=0.4,
                exit_reason="TAKE_PROFIT",
                opened_at=opened_at,
            )
            doc = await db.signal_dataset.find_one({"id": entry["id"]})
            assert doc is not None, "signal_dataset entry not found after insert"
            assert doc["outcome"] == "WIN", (
                f"Expected outcome=WIN for positive PnL, got outcome={doc['outcome']!r}"
            )
            assert doc["pnl"] == 20.0
            assert doc["exit_reason"] == "TAKE_PROFIT"
            print("✓ WIN outcome labeled correctly")
        finally:
            await db.signal_dataset.delete_one({"id": entry["id"]})

    run(_run())


def test_loss_outcome_labeled():
    """Closing a DRY position with negative PnL labels the dataset entry as LOSS."""
    from services.ml_service import update_dataset_outcome

    db = _make_db()
    symbol = "ETHUSDT"
    side = "LONG"
    opened_at = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    entry = _signal_entry(symbol, side, opened_at)

    async def _run():
        await db.signal_dataset.insert_one(entry)
        try:
            await update_dataset_outcome(
                db_ref=db,
                symbol=symbol,
                side=side,
                entry_price=50_000.0,
                pnl=-15.0,
                pnl_pct=-0.3,
                exit_reason="STOP_LOSS",
                opened_at=opened_at,
            )
            doc = await db.signal_dataset.find_one({"id": entry["id"]})
            assert doc is not None
            assert doc["outcome"] == "LOSS", (
                f"Expected outcome=LOSS for negative PnL, got outcome={doc['outcome']!r}"
            )
            assert doc["pnl"] == -15.0
            assert doc["exit_reason"] == "STOP_LOSS"
            print("✓ LOSS outcome labeled correctly")
        finally:
            await db.signal_dataset.delete_one({"id": entry["id"]})

    run(_run())


def test_no_match_outside_time_window():
    """A signal logged >10 min before opened_at must NOT be matched."""
    from services.ml_service import update_dataset_outcome

    db = _make_db()
    symbol = "SOLUSDT"
    side = "LONG"
    # Signal was logged 20 minutes ago — outside the 10-minute look-back window.
    signal_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    # opened_at is 1 minute ago → window [opened_at-10min, opened_at] misses signal_time.
    opened_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    entry = _signal_entry(symbol, side, signal_time)

    async def _run():
        await db.signal_dataset.insert_one(entry)
        try:
            await update_dataset_outcome(
                db_ref=db,
                symbol=symbol,
                side=side,
                entry_price=50_000.0,
                pnl=10.0,
                pnl_pct=0.2,
                exit_reason="TAKE_PROFIT",
                opened_at=opened_at,
            )
            doc = await db.signal_dataset.find_one({"id": entry["id"]})
            assert doc is not None
            assert doc["outcome"] is None, (
                f"Expected outcome=None for out-of-window signal, got {doc['outcome']!r}"
            )
            print("✓ Out-of-window signal correctly left unlabeled")
        finally:
            await db.signal_dataset.delete_one({"id": entry["id"]})

    run(_run())


def test_trade_not_taken_is_not_matched():
    """Signals with trade_taken=False must never be labeled by update_dataset_outcome."""
    from services.ml_service import update_dataset_outcome

    db = _make_db()
    symbol = "XRPUSDT"
    side = "LONG"
    opened_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    entry = _signal_entry(symbol, side, opened_at, trade_taken=False)

    async def _run():
        await db.signal_dataset.insert_one(entry)
        try:
            await update_dataset_outcome(
                db_ref=db,
                symbol=symbol,
                side=side,
                entry_price=50_000.0,
                pnl=5.0,
                pnl_pct=0.1,
                exit_reason="TAKE_PROFIT",
                opened_at=opened_at,
            )
            doc = await db.signal_dataset.find_one({"id": entry["id"]})
            assert doc is not None
            assert doc["outcome"] is None, (
                f"Expected trade_taken=False signal to remain unlabeled, got {doc['outcome']!r}"
            )
            print("✓ trade_taken=False signal correctly left unlabeled")
        finally:
            await db.signal_dataset.delete_one({"id": entry["id"]})

    run(_run())


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
