"""Bot control routes — start, stop, pause, config, mode."""
import logging
from fastapi import APIRouter, HTTPException, Depends
from auth import get_current_user
from database import db
from models import BotConfigUpdate, TelegramConfig, ModeToggle, ExchangeKeysUpdate
import state
from services.bot_loop import get_default_config, start_bot, stop_bot
from config import KRAKEN_API_KEY, KRAKEN_API_SECRET

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
async def update_exchange_keys(data: ExchangeKeysUpdate, user=Depends(get_current_user)):
    """Save Kraken API keys to DB and attempt immediate reconnect."""
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
    return {
        "connected": connected,
        "api_key_preview": key_preview,
        "message": "Kraken client connected successfully!" if connected else f"Connection failed: {error}",
        "error": error if not connected else None,
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
    effective_key = db_key or KRAKEN_API_KEY
    effective_secret = db_secret or KRAKEN_API_SECRET
    if mode == "LIVE":
        if not effective_key or not effective_secret:
            raise HTTPException(
                status_code=400,
                detail="Cannot switch to LIVE mode: Kraken API keys are not configured. Add them in Settings."
            )
        # Re-attempt Kraken client initialization if not connected
        if not state.binance_client:
            from services.binance_service import init_binance_client
            await init_binance_client(effective_key or None, effective_secret or None)
            kraken_connected = state.binance_client is not None
            logger.info(f"Kraken reconnect on mode switch: {'connected' if kraken_connected else 'failed'}")
        else:
            kraken_connected = True
    else:
        kraken_connected = state.binance_client is not None
    await db.bot_config.update_one({"active": True}, {"$set": {"mode": mode}}, upsert=True)
    state.bot_state["mode"] = mode
    logger.info(f"Bot mode switched to {mode} by user {user.get('email', 'unknown')}")
    warning = None
    if mode == "LIVE" and not kraken_connected:
        warning = "Kraken connection unavailable. The bot is set to LIVE — real orders will execute once connected."
    return {
        "mode": mode,
        "binance_connected": kraken_connected,
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
    keys_configured = bool(db_key and db_secret) or bool(KRAKEN_API_KEY and KRAKEN_API_SECRET)
    # Show DB key preview first (it's what's actively used)
    key_preview = ""
    if db_key:
        key_preview = f"****{db_key[-4:]}"
    elif KRAKEN_API_KEY:
        key_preview = f"****{KRAKEN_API_KEY[-4:]}"
    return {
        "mode": current_mode,
        "binance_connected": state.binance_client is not None,
        "binance_keys_configured": keys_configured,
        "api_key_preview": key_preview,
    }


@router.get("/bot/binance-test")
async def test_exchange_connection(user=Depends(get_current_user)):
    """Attempt a live Kraken connection and return exact error detail for diagnosis."""
    import asyncio
    config = await db.bot_config.find_one({"active": True}, {"_id": 0}) or {}
    key = (config.get("binance_api_key") or KRAKEN_API_KEY or state.binance_keys.get("api_key", ""))
    secret = (config.get("binance_api_secret") or KRAKEN_API_SECRET or state.binance_keys.get("api_secret", ""))
    if not key or not secret:
        return {"connected": False, "error": "No API keys configured. Add them in Settings."}
    from services.binance_service import init_binance_client
    error = await init_binance_client(key, secret)
    connected = state.binance_client is not None
    return {
        "connected": connected,
        "can_trade": connected,
        "message": "Connected to Kraken successfully!" if connected else None,
        "error": error if not connected else None,
    }



async def get_filter_status(user=Depends(get_current_user)):
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    if not config:
        config = await get_default_config()
    return {
        "filters": {
            "max_trades_per_hour": config.get("max_trades_per_hour", 5),
            "max_trades_per_day": config.get("max_trades_per_day", 20),
            "min_risk_reward_ratio": config.get("min_risk_reward_ratio", 2.5),
            "cooldown_after_loss_scans": config.get("cooldown_after_loss_scans", 6),
            "min_confidence_score": config.get("min_confidence_score", 0.60),
            "spread_max_percent": config.get("spread_max_percent", 0.15),
            "min_24h_volume_usdt": config.get("min_24h_volume_usdt", 1000000),
            "max_slippage_percent": config.get("max_slippage_percent", 1.0),
            "require_trend_alignment": config.get("require_trend_alignment", True),
        },
        "cooldown_state": {
            "scans_since_loss": state._cooldown_state["scans_since_loss"],
            "consecutive_losses": state._cooldown_state["consecutive_losses"]
        }
    }


@router.get("/bot/diagnose")
async def diagnose_bot(user=Depends(get_current_user)):
    """Real-time diagnostic: shows exactly which gate is blocking the bot right now."""
    from datetime import datetime, timezone, timedelta
    from services.filters import check_overtrade_limits
    from services.risk_service import check_circuit_breaker, check_trading_session

    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    if not config:
        config = await get_default_config()

    now = datetime.now(timezone.utc)
    hour_ago = (now - timedelta(hours=1)).isoformat()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Count LIVE and DRY trades separately for visibility
    live_hour = await db.trades.count_documents({"closed_at": {"$gte": hour_ago}, "mode": "LIVE"})
    dry_hour  = await db.trades.count_documents({"closed_at": {"$gte": hour_ago}, "mode": "DRY"})
    live_day  = await db.trades.count_documents({"closed_at": {"$gte": day_start}, "mode": "LIVE"})
    dry_day   = await db.trades.count_documents({"closed_at": {"$gte": day_start}, "mode": "DRY"})
    open_pos  = await db.positions.count_documents({"status": "OPEN"})

    max_per_hour = config.get("max_trades_per_hour", 5)
    max_per_day  = config.get("max_trades_per_day", 20)
    ot_ok = (live_hour < max_per_hour) and (live_day < max_per_day)

    cb_ok, current_dd = await check_circuit_breaker(db, config)
    session_ok, active_session = check_trading_session(config)

    cd_required = config.get("cooldown_after_loss_scans", 6)
    cd_scans    = state._cooldown_state["scans_since_loss"]
    cd_ok       = cd_scans >= cd_required

    gates = {
        "circuit_breaker":  {"pass": cb_ok,      "detail": f"drawdown {current_dd:.2f}% vs max {config.get('max_total_drawdown_percent', 5)}%"},
        "trading_session":  {"pass": session_ok,  "detail": f"current session: {active_session}"},
        "overtrade_limit":  {"pass": ot_ok,       "detail": f"LIVE {live_hour}/{max_per_hour} /hr  |  {live_day}/{max_per_day} /day  (DRY ignored: {dry_hour}/hr, {dry_day}/day)"},
        "cooldown":         {"pass": cd_ok,       "detail": f"{cd_scans}/{cd_required} scans since last loss"},
        "open_positions":   {"pass": open_pos < 3, "detail": f"{open_pos} open (max 3)"},
    }

    blocked_by = [k for k, v in gates.items() if not v["pass"]]
    return {
        "bot_running":   state.bot_state["running"],
        "mode":          state.bot_state["mode"],
        "kraken_connected": state.binance_client is not None,
        "scan_count":    state.bot_state["scan_count"],
        "gates":         gates,
        "blocked_by":    blocked_by,
        "can_trade_now": len(blocked_by) == 0,
        "config_snapshot": {
            "max_trades_per_hour":    max_per_hour,
            "max_trades_per_day":     max_per_day,
            "max_slippage_percent":   config.get("max_slippage_percent", 1.0),
            "min_confidence_score":   config.get("min_confidence_score", 0.60),
            "min_entry_probability":  config.get("min_entry_probability", 0.65),
            "base_usdt_per_trade":    config.get("base_usdt_per_trade", 8.0),
            "ml_min_win_probability": config.get("ml_min_win_probability", 0.0),
        }
    }
