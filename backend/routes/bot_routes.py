"""Bot control routes — start, stop, pause, config, mode."""
import logging
from fastapi import APIRouter, HTTPException, Depends
from auth import get_current_user
from database import db
from models import BotConfigUpdate, TelegramConfig, ModeToggle, BinanceKeysUpdate
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


@router.put("/bot/binance-keys")
async def update_binance_keys(data: BinanceKeysUpdate, user=Depends(get_current_user)):
    """Save Binance API keys to DB and attempt immediate reconnect."""
    await db.bot_config.update_one(
        {"active": True},
        {"$set": {"binance_api_key": data.api_key, "binance_api_secret": data.api_secret}},
        upsert=True
    )
    state.binance_keys["api_key"] = data.api_key
    state.binance_keys["api_secret"] = data.api_secret
    from services.binance_service import init_binance_client
    error = await init_binance_client(data.api_key, data.api_secret)
    connected = state.binance_client is not None
    key_preview = f"****{data.api_key[-4:]}" if len(data.api_key) > 4 else "****"

    # Translate raw Binance error into a human-readable hint
    hint = None
    if error:
        e = error.lower()
        if "restricted location" in e or "eligibility" in e:
            hint = "IP still blocked by Binance — make sure you saved 'Unrestricted' on Binance and waited ~30s for it to take effect."
        elif "invalid api" in e or "-2014" in e or "-2015" in e or "invalid key" in e:
            hint = "Invalid API key — double-check you copied the full key correctly."
        elif "signature" in e or "-1022" in e:
            hint = "Invalid signature — your API Secret is wrong. Copy it again from Binance exactly."
        elif "timestamp" in e or "-1021" in e:
            hint = "Clock skew — server time mismatch with Binance."
        elif "timed out" in e:
            hint = "Connection timed out — Binance unreachable from server."
        elif "permission" in e or "-2010" in e:
            hint = "Permission denied — enable 'Spot & Margin Trading' on the key."
        else:
            hint = error

    return {
        "connected": connected,
        "api_key_preview": key_preview,
        "message": "Binance client connected successfully!" if connected else f"Connection failed: {hint or error}",
        "error": hint or error if not connected else None,
    }


@router.put("/bot/mode")
async def toggle_bot_mode(data: ModeToggle, user=Depends(get_current_user)):
    mode = data.mode.upper()
    if mode not in ("DRY", "LIVE"):
        raise HTTPException(status_code=400, detail="Mode must be DRY or LIVE")
    config = await db.bot_config.find_one({"active": True}, {"_id": 0}) or {}
    db_key = config.get("binance_api_key", "")
    db_secret = config.get("binance_api_secret", "")
    # DB keys (set via UI) take priority over env vars
    effective_key = db_key or BINANCE_API_KEY
    effective_secret = db_secret or BINANCE_API_SECRET
    if mode == "LIVE":
        if not effective_key or not effective_secret:
            raise HTTPException(
                status_code=400,
                detail="Cannot switch to LIVE mode: Binance API keys are not configured. Add them in Settings."
            )
        # Re-attempt Binance client initialization if not connected
        if not state.binance_client:
            from services.binance_service import init_binance_client
            await init_binance_client(effective_key or None, effective_secret or None)
            binance_connected = state.binance_client is not None
            logger.info(f"Binance reconnect on mode switch: {'connected' if binance_connected else 'failed'}")
        else:
            binance_connected = True
    else:
        binance_connected = state.binance_client is not None
    await db.bot_config.update_one({"active": True}, {"$set": {"mode": mode}}, upsert=True)
    state.bot_state["mode"] = mode
    logger.info(f"Bot mode switched to {mode} by user {user.get('email', 'unknown')}")
    warning = None
    if mode == "LIVE" and not binance_connected:
        warning = "Binance connection unavailable. The bot is set to LIVE — real orders will execute once connected."
    return {
        "mode": mode,
        "binance_connected": binance_connected,
        "message": f"Bot is now in {mode} mode" + (" — real trades will be executed!" if mode == "LIVE" else " — trades are simulated."),
        "warning": warning,
    }


@router.get("/bot/mode")
async def get_bot_mode(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    current_mode = config.get("mode", "DRY") if config else "DRY"
    db_key = config.get("binance_api_key", "") if config else ""
    db_secret = config.get("binance_api_secret", "") if config else ""
    # Load DB keys into runtime state if not already loaded (e.g., after restart)
    if db_key and db_secret and not state.binance_keys.get("api_key"):
        state.binance_keys["api_key"] = db_key
        state.binance_keys["api_secret"] = db_secret
    keys_configured = bool(db_key and db_secret) or bool(BINANCE_API_KEY and BINANCE_API_SECRET)
    # Show DB key preview first (it's what's actively used)
    key_preview = ""
    if db_key:
        key_preview = f"****{db_key[-4:]}"
    elif BINANCE_API_KEY:
        key_preview = f"****{BINANCE_API_KEY[-4:]}"
    return {
        "mode": current_mode,
        "binance_connected": state.binance_client is not None,
        "binance_keys_configured": keys_configured,
        "api_key_preview": key_preview,
    }


@router.get("/bot/binance-test")
async def test_binance_connection(user=Depends(get_current_user)):
    """Attempt a live Binance connection and return exact error detail for diagnosis."""
    import asyncio
    config = await db.bot_config.find_one({"active": True}, {"_id": 0}) or {}
    key = BINANCE_API_KEY or config.get("binance_api_key", "") or state.binance_keys.get("api_key", "")
    secret = BINANCE_API_SECRET or config.get("binance_api_secret", "") or state.binance_keys.get("api_secret", "")
    if not key or not secret:
        return {"connected": False, "error": "No API keys configured. Add them below and click Save & Connect."}
    from binance import AsyncClient as BinanceAsyncClient
    try:
        client = await asyncio.wait_for(
            BinanceAsyncClient.create(api_key=key, api_secret=secret),
            timeout=15.0
        )
        # Ping account to verify permissions
        account = await asyncio.wait_for(client.get_account(), timeout=10.0)
        await client.close_connection()
        can_trade = account.get("canTrade", False)
        return {
            "connected": True,
            "can_trade": can_trade,
            "message": "Connected successfully!" + ("" if can_trade else " But Spot Trading permission is disabled on this key.")
        }
    except asyncio.TimeoutError:
        return {"connected": False, "error": "Connection timed out (15s). Binance may be unreachable from this server."}
    except Exception as e:
        err = str(e)
        if "IP" in err or "restricted" in err.lower() or "-1003" in err or "WAF" in err:
            hint = "IP restriction — go to Binance API settings and set IP access to 'Unrestricted'."
        elif "Invalid API" in err or "-2014" in err or "-2015" in err:
            hint = "Invalid API key or secret — double-check you copied both correctly."
        elif "Timestamp" in err or "-1021" in err:
            hint = "Clock skew error — server time mismatch with Binance."
        elif "permission" in err.lower() or "-2010" in err:
            hint = "Permission error — enable 'Spot & Margin Trading' on the key."
        else:
            hint = err
        return {"connected": False, "error": hint, "raw": err}



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
