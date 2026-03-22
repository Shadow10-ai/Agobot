"""ML routes — model status, training, dataset."""
from fastapi import APIRouter, Depends, HTTPException
from auth import get_current_user
from database import db
from services.ml_service import train_ml_model, load_ml_model
import state

router = APIRouter()


@router.get("/ml/status")
async def get_ml_status(user=Depends(get_current_user)):
    total = await db.signal_dataset.count_documents({})
    labeled = await db.signal_dataset.count_documents({"outcome": {"$in": ["WIN", "LOSS"]}})
    wins = await db.signal_dataset.count_documents({"outcome": "WIN"})
    losses = await db.signal_dataset.count_documents({"outcome": "LOSS"})
    return {
        "status": state.ml_model_state["status"],
        "accuracy": state.ml_model_state["accuracy"],
        "precision": state.ml_model_state["precision"],
        "recall": state.ml_model_state["recall"],
        "f1": state.ml_model_state["f1"],
        "cv_score": state.ml_model_state["cv_score"],
        "training_samples": state.ml_model_state["training_samples"],
        "wins_in_training": state.ml_model_state["wins_in_training"],
        "losses_in_training": state.ml_model_state["losses_in_training"],
        "last_trained": state.ml_model_state["last_trained"],
        "trades_since_retrain": state.ml_model_state["trades_since_retrain"],
        "feature_importance": state.ml_model_state["feature_importance"],
        "version": state.ml_model_state["version"],
        "total_signals_logged": total,
        "labeled_signals": labeled,
        "label_breakdown": {"WIN": wins, "LOSS": losses},
    }


@router.post("/ml/train")
async def trigger_ml_training(user=Depends(get_current_user)):
    if state.ml_model_state["status"] == "TRAINING":
        raise HTTPException(status_code=409, detail="Training already in progress")
    import asyncio
    asyncio.create_task(train_ml_model(db))
    return {"message": "ML model training started", "status": "TRAINING"}


@router.get("/ml/dataset")
async def get_dataset(limit: int = 100, user=Depends(get_current_user)):
    docs = await db.signal_dataset.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    total = await db.signal_dataset.count_documents({})
    return {"samples": docs, "total": total}
