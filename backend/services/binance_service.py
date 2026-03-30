"""Exchange client management using Bybit (pybit). Keeps original function names for compatibility."""
import asyncio
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from functools import partial
import state
from config import BYBIT_API_KEY, BYBIT_API_SECRET

logger = logging.getLogger(__name__)

# Bybit interval mapping: our internal format → Bybit V5 format
_INTERVAL_MAP = {"1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
                 "1h": "60", "2h": "120", "4h": "240", "1d": "D"}


def _get_bybit_client():
    """Return the cached Bybit HTTP client from state."""
    return state.binance_client  # variable kept as-is for minimal code changes


async def _run_sync(func, *args, **kwargs):
    """Run a synchronous Bybit call in the default thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


def _init_bybit_sync(key: str, secret: str):
    """Synchronous Bybit client init — called from thread pool."""
    from pybit.unified_trading import HTTP
    client = HTTP(testnet=False, api_key=key, api_secret=secret)
    # Verify keys with a lightweight authenticated call
    resp = client.get_wallet_balance(accountType="UNIFIED")
    if resp.get("retCode") != 0:
        raise Exception(resp.get("retMsg", "Unknown Bybit error"))
    return client


async def init_binance_client(api_key: str = None, api_secret: str = None):
    """Initialize the Bybit HTTP client. Returns error string on failure, None on success."""
    key = api_key or state.binance_keys.get("api_key") or BYBIT_API_KEY
    secret = api_secret or state.binance_keys.get("api_secret") or BYBIT_API_SECRET
    if not key or not secret:
        logger.warning("Bybit API keys not configured — LIVE mode unavailable")
        return "No API keys configured."
    # Close existing client
    state.binance_client = None
    try:
        client = await asyncio.wait_for(
            _run_sync(_init_bybit_sync, key, secret),
            timeout=20.0
        )
        state.binance_client = client
        state.binance_keys["api_key"] = key
        state.binance_keys["api_secret"] = secret
        logger.info("Bybit client initialized successfully")
        return None  # success
    except asyncio.TimeoutError:
        logger.warning("Bybit client init timed out (20s) — DRY mode only")
        state.binance_client = None
        return "Connection timed out. Bybit may be unreachable from this server."
    except Exception as e:
        err = str(e)
        logger.error(f"Failed to initialize Bybit client: {err}")
        state.binance_client = None
        # Translate common Bybit errors
        if "invalid api_key" in err.lower() or "10003" in err:
            return "Invalid API key — double-check you copied the full key correctly."
        if "invalid sign" in err.lower() or "signature" in err.lower() or "10004" in err:
            return "Invalid signature — your API Secret is wrong. Copy it again exactly."
        if "ip" in err.lower() and ("restrict" in err.lower() or "not allow" in err.lower()):
            return "IP restriction — set IP access to 'No Restriction' on Bybit API Management."
        if "permission" in err.lower() or "10005" in err:
            return "Permission denied — enable 'Unified Trading' permissions on the key."
        return err


async def close_binance_client():
    """Close the Bybit client (no persistent connection needed for HTTP)."""
    state.binance_client = None
    logger.info("Bybit client cleared")


async def fetch_live_price(symbol: str) -> float:
    """Fetch real-time price from Bybit."""
    client = _get_bybit_client()
    if not client:
        raise RuntimeError("Bybit client not initialized")

    def _get_price():
        resp = client.get_tickers(category="spot", symbol=symbol)
        if resp.get("retCode") != 0:
            raise Exception(resp.get("retMsg"))
        return float(resp["result"]["list"][0]["lastPrice"])

    return await _run_sync(_get_price)


async def fetch_live_candles(symbol: str, interval: str = "3m", limit: int = 60):
    """Fetch real kline candles from Bybit and return in internal format."""
    client = _get_bybit_client()
    if not client:
        raise RuntimeError("Bybit client not initialized")
    bybit_interval = _INTERVAL_MAP.get(interval, interval.replace("m", "").replace("h", "0"))

    def _get_klines():
        resp = client.get_kline(category="spot", symbol=symbol, interval=bybit_interval, limit=limit)
        if resp.get("retCode") != 0:
            raise Exception(resp.get("retMsg"))
        # Bybit returns newest-first — reverse to oldest-first
        raw = list(reversed(resp["result"]["list"]))
        return [
            {
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "time": int(k[0])
            }
            for k in raw
        ]

    return await _run_sync(_get_klines)


async def place_live_market_order(symbol: str, side: str, quote_qty: float):
    """Place a real market order on Bybit spot. Returns order result dict."""
    client = _get_bybit_client()
    if not client:
        raise RuntimeError("Bybit client not initialized")
    bybit_side = "Buy" if side.upper() in ("BUY", "LONG") else "Sell"

    def _place_and_confirm():
        # Place market order with USDT quantity
        resp = client.place_order(
            category="spot",
            symbol=symbol,
            side=bybit_side,
            orderType="Market",
            qty=str(round(quote_qty, 2)),
            marketUnit="quoteCoin"
        )
        if resp.get("retCode") != 0:
            raise Exception(f"Order rejected: {resp.get('retMsg')}")
        order_id = resp["result"]["orderId"]
        # Brief wait for fill then fetch details
        time.sleep(0.8)
        history = client.get_order_history(category="spot", symbol=symbol, orderId=order_id)
        if history.get("retCode") == 0 and history["result"]["list"]:
            o = history["result"]["list"][0]
            exec_qty = float(o.get("cumExecQty") or 0)
            avg_price = float(o.get("avgPrice") or 0)
            return {
                "order_id": order_id,
                "status": o.get("orderStatus", "Filled"),
                "executed_qty": exec_qty,
                "avg_price": avg_price,
            }
        return {"order_id": order_id, "status": "placed", "executed_qty": 0, "avg_price": 0}

    return await _run_sync(_place_and_confirm)


def generate_candles(symbol, count=60):
    """Generate simulated OHLCV candles for DRY mode."""
    base_price = state.SYMBOL_PRICES.get(symbol, 100.0)
    candles = []
    price = base_price * (1 + random.uniform(-0.02, 0.02))
    for i in range(count):
        volatility = base_price * 0.003
        open_p = price
        change = random.gauss(0, volatility)
        close_p = open_p + change
        high_p = max(open_p, close_p) + abs(random.gauss(0, volatility * 0.5))
        low_p = min(open_p, close_p) - abs(random.gauss(0, volatility * 0.5))
        candles.append({
            "open": round(open_p, 8),
            "high": round(high_p, 8),
            "low": round(low_p, 8),
            "close": round(close_p, 8),
            "volume": round(random.uniform(100, 10000), 2),
            "time": int((datetime.now(timezone.utc) - timedelta(minutes=(count - i) * 3)).timestamp() * 1000)
        })
        price = close_p
    state.SYMBOL_PRICES[symbol] = round(candles[-1]['close'], 8)
    return candles
