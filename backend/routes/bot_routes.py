"""Bot control routes — start, stop, pause, config, mode."""
import logging
from fastapi import APIRouter, HTTPException, Depends
from auth import get_current_user
from database import db
from models import BotConfigUpdate, TelegramConfig, ModeToggle
import state
from services.bot_loop import get_default_config, start_bot, stop_bot
from config import BINANCE_API_KEY, BINANCE_API_SECRET

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/bot/status")
async def get_bot_status(user=Depends(get_current_user)):
    open_positions = await db.positions.count_documents({"status": "OPEN"})
    total_trades = await db.trades.count_documents({})
    daily_pnl_doc = await db.bot_state.find_one({"key": "daily_pnl"}, {"_id": 0})
    daily_pnl = daily_pnl_doc["value"] if daily_pnl_doc else 0.0
    return {
        "running": state.bot_state["running"],
        "paused": state.bot_state["paused"],
        "mode": state.bot_state["mode"],
        "started_at": state.bot_state["started_at"],
        "scan_count": state.bot_state["scan_count"],
        "last_scan": state.bot_state["last_scan"],
        "open_positions": open_positions,
        "total_trades": total_trades,
        "daily_pnl": daily_pnl
    }


@router.post("/bot/start")
async def start_bot_route(user=Depends(get_current_user)):
    await start_bot()
    return {"status": "started"}


@router.post("/bot/stop")
async def stop_bot_route(user=Depends(get_current_user)):
    await stop_bot()
    return {"status": "stopped"}


@router.post("/bot/pause")
async def pause_bot(user=Depends(get_current_user)):
    state.bot_state["paused"] = True
    return {"status": "paused"}


@router.post("/bot/resume")
async def resume_bot(user=Depends(get_current_user)):
    state.bot_state["paused"] = False
    return {"status": "resumed"}


@router.get("/bot/config")
async def get_bot_config(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    if not config:
        config = await get_default_config()
    config.pop("active", None)
    return config


@router.put("/bot/config")
async def update_bot_config(data: BotConfigUpdate, user=Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if update_data:
        await db.bot_config.update_one({"active": True}, {"$set": update_data}, upsert=True)
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    config.pop("active", None)
    return config


@router.put("/bot/telegram")
async def update_telegram_config(data: TelegramConfig, user=Depends(get_current_user)):
    await db.bot_config.update_one(
        {"active": True},
        {"$set": {"telegram_token": data.telegram_token, "telegram_chat_id": data.telegram_chat_id}},
        upsert=True
    )
    return {"status": "updated"}


@router.put("/bot/mode")
async def toggle_bot_mode(data: ModeToggle, user=Depends(get_current_user)):
    mode = data.mode.upper()
    if mode not in ("DRY", "LIVE"):
        raise HTTPException(status_code=400, detail="Mode must be DRY or LIVE")
    if mode == "LIVE" and not state.binance_client:
        raise HTTPException(
            status_code=400,
            detail="Cannot switch to LIVE mode: Binance API keys not configured or client failed to initialize"
        )
    await db.bot_config.update_one({"active": True}, {"$set": {"mode": mode}}, upsert=True)
    state.bot_state["mode"] = mode
    logger.info(f"Bot mode switched to {mode} by user {user.get('email', 'unknown')}")
    return {
        "mode": mode,
        "binance_connected": state.binance_client is not None,
        "message": f"Bot is now in {mode} mode" + (" — real trades will be executed!" if mode == "LIVE" else " — trades are simulated.")
    }


@router.get("/bot/mode")
async def get_bot_mode(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    current_mode = config.get("mode", "DRY") if config else "DRY"
    return {
        "mode": current_mode,
        "binance_connected": state.binance_client is not None,
        "binance_keys_configured": bool(BINANCE_API_KEY and BINANCE_API_SECRET)
    }


@router.get("/bot/filters")
async def get_filter_status(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    if not config:
        config = await get_default_config()
    return {
        "filters": {
            "max_trades_per_hour": config.get("max_trades_per_hour", 2),
            "max_trades_per_day": config.get("max_trades_per_day", 8),
            "min_risk_reward_ratio": config.get("min_risk_reward_ratio", 2.5),
            "cooldown_after_loss_scans": config.get("cooldown_after_loss_scans", 6),
            "min_confidence_score": config.get("min_confidence_score", 0.60),
            "spread_max_percent": config.get("spread_max_percent", 0.15),
            "min_24h_volume_usdt": config.get("min_24h_volume_usdt", 1000000),
            "max_slippage_percent": config.get("max_slippage_percent", 0.1),
            "require_trend_alignment": config.get("require_trend_alignment", True),
        },
        "cooldown_state": {
            "scans_since_loss": state._cooldown_state["scans_since_loss"],
            "consecutive_losses": state._cooldown_state["consecutive_losses"]
        }
    }
