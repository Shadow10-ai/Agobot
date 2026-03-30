"""
AgoBot — Autonomous Crypto Trading Bot
FastAPI entry point. All business logic lives in services/ and routes/.
"""
import asyncio
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=False)

# Configure logging before importing anything else
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Import routes
from routes.auth_routes import router as auth_router
from routes.bot_routes import router as bot_router
from routes.trading_routes import router as trading_router
from routes.backtest_routes import router as backtest_router
from routes.ml_routes import router as ml_router
from routes.risk_routes import router as risk_router
from routes.market_intel_routes import router as market_intel_router
from routes.misc_routes import router as misc_router

# Import startup services
from database import db
import state
from config import BYBIT_API_KEY, BYBIT_API_SECRET
from services.binance_service import init_binance_client, close_binance_client
from services.ml_service import load_ml_model, seed_dataset_from_trades, train_ml_model
from services.bot_loop import start_bot, get_default_config

app = FastAPI(
    title="AgoBot Trading API",
    description="Autonomous ML-powered crypto trading bot",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers under /api prefix
api_prefix = "/api"
for router in [auth_router, bot_router, trading_router, backtest_router, ml_router, risk_router, market_intel_router, misc_router]:
    app.include_router(router, prefix=api_prefix)


@app.on_event("startup")
async def startup_event():
    logger.info("AgoBot starting up...")

    # Create MongoDB indexes
    try:
        await db.users.create_index("email", unique=True)
        await db.positions.create_index([("status", 1), ("symbol", 1)])
        await db.trades.create_index([("closed_at", -1)])
        await db.signal_dataset.create_index([("timestamp", -1)])
        await db.price_history.create_index("timestamp")
        logger.info("MongoDB indexes created")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")

    # Initialize Binance client in background — don't block startup health check
    async def init_binance_background():
        try:
            if not BYBIT_API_KEY or not BYBIT_API_SECRET:
                config_doc = await db.bot_config.find_one({"active": True}, {"_id": 0})
                if config_doc:
                    db_key = config_doc.get("binance_api_key", "")
                    db_secret = config_doc.get("binance_api_secret", "")
                    if db_key and db_secret:
                        state.binance_keys["api_key"] = db_key
                        state.binance_keys["api_secret"] = db_secret
                        logger.info("Loaded Bybit keys from database")
            await init_binance_client()
        except Exception as e:
            logger.warning(f"Bybit background init warning: {e}")

    asyncio.create_task(init_binance_background())

    # Ensure default bot config exists
    try:
        config = await db.bot_config.find_one({"active": True})
        if not config:
            await get_default_config()
            logger.info("Default bot config created")
    except Exception as e:
        logger.warning(f"Bot config init warning (MongoDB may be unreachable): {e}")

    # Load or prepare ML model
    try:
        await load_ml_model()
    except Exception as e:
        logger.warning(f"ML model load warning: {e}")

    try:
        await seed_dataset_from_trades(db)
    except Exception as e:
        logger.warning(f"Dataset seed warning: {e}")

    # If enough data, retrain
    try:
        labeled_count = await db.signal_dataset.count_documents({"outcome": {"$in": ["WIN", "LOSS"]}})
        from config import ML_MIN_SAMPLES
        if labeled_count >= ML_MIN_SAMPLES and state.ml_model_state["status"] != "ACTIVE":
            logger.info(f"Auto-training ML model on {labeled_count} labeled samples...")
            await train_ml_model(db)
    except Exception as e:
        logger.warning(f"ML training warning: {e}")

    # Auto-start the bot
    try:
        await start_bot()
    except Exception as e:
        logger.warning(f"Bot auto-start warning: {e}")

    logger.info("AgoBot startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("AgoBot shutting down...")
    state.bot_state["running"] = False
    if state.bot_task:
        state.bot_task.cancel()
    await close_binance_client()
    from database import _mongo_client
    _mongo_client.close()
    logger.info("AgoBot shutdown complete")
