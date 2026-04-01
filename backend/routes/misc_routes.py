"""Misc routes — prices, dataset stats, health check."""
from fastapi import APIRouter, Depends
from auth import get_current_user
from database import db
import state

router = APIRouter()


@router.get("/prices")
async def get_prices(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    symbols = config.get("symbols", ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']) if config else ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']
    return {s: state.SYMBOL_PRICES.get(s, 0) for s in symbols}


@router.get("/prices/history/{symbol}")
async def get_price_history(symbol: str, user=Depends(get_current_user)):
    history = await db.price_history.find({}, {"_id": 0}).sort("timestamp", -1).limit(200).to_list(200)
    history.reverse()
    data = []
    for h in history:
        if symbol in h.get("prices", {}):
            data.append({"timestamp": h["timestamp"], "price": h["prices"][symbol]})
    return data


@router.get("/dataset/stats")
async def get_dataset_stats(user=Depends(get_current_user)):
    total = await db.signal_dataset.count_documents({})
    taken = await db.signal_dataset.count_documents({"trade_taken": True})
    rejected = await db.signal_dataset.count_documents({"trade_taken": False})
    wins = await db.signal_dataset.count_documents({"outcome": "WIN"})
    losses = await db.signal_dataset.count_documents({"outcome": "LOSS"})
    pending = await db.signal_dataset.count_documents({"trade_taken": True, "outcome": None})
    pipeline = [{"$match": {"trade_taken": False}}, {"$sort": {"timestamp": -1}}, {"$limit": 100}]
    recent_rejected = await db.signal_dataset.aggregate(pipeline).to_list(100)
    rejection_reasons = {}
    for r in recent_rejected:
        for k, v in r.get("filters_passed", {}).items():
            if not v:
                rejection_reasons[k] = rejection_reasons.get(k, 0) + 1
    taken_conf = await db.signal_dataset.aggregate([{"$match": {"trade_taken": True}}, {"$group": {"_id": None, "avg_conf": {"$avg": "$confidence_score"}}}]).to_list(1)
    rejected_conf = await db.signal_dataset.aggregate([{"$match": {"trade_taken": False}}, {"$group": {"_id": None, "avg_conf": {"$avg": "$confidence_score"}}}]).to_list(1)
    return {
        "total_signals": total,
        "trades_taken": taken,
        "trades_rejected": rejected,
        "outcomes": {"wins": wins, "losses": losses, "pending": pending},
        "win_rate": round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
        "rejection_reasons": dict(sorted(rejection_reasons.items(), key=lambda x: -x[1])),
        "avg_confidence_taken": round(taken_conf[0]["avg_conf"], 4) if taken_conf else 0,
        "avg_confidence_rejected": round(rejected_conf[0]["avg_conf"], 4) if rejected_conf else 0,
        "cooldown_state": {
            "scans_since_loss": state._cooldown_state["scans_since_loss"],
            "consecutive_losses": state._cooldown_state["consecutive_losses"]
        }
    }


@router.get("/health")
async def health_check():
    try:
        await db.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "degraded", "database": "disconnected", "error": str(e)}


@router.get("/backtests")
async def get_saved_backtests(user=Depends(get_current_user)):
    """Return list of saved backtest configs/results placeholder."""
    return {"backtests": [], "message": "Backtest history not persisted in this version"}
