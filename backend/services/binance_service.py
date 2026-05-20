"""Exchange client management using Kraken via ccxt. Function names kept for compatibility."""
import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta
import state
from config import KRAKEN_API_KEY, KRAKEN_API_SECRET, to_kraken_symbol

logger = logging.getLogger(__name__)

# Kraken-supported timeframe mapping (3m not available → 5m)
_TF_MAP = {
    "1m": "1m", "3m": "5m", "5m": "5m",
    "15m": "15m", "30m": "30m", "1h": "1h",
    "2h": "2h", "4h": "4h", "1d": "1d",
}


async def init_binance_client(api_key: str = None, api_secret: str = None):
    """Initialize the Kraken ccxt client. Returns error string on failure, None on success."""
    import ccxt.async_support as ccxt

    key = api_key or state.binance_keys.get("api_key") or KRAKEN_API_KEY
    secret = api_secret or state.binance_keys.get("api_secret") or KRAKEN_API_SECRET
    if not key or not secret:
        logger.warning("Kraken API keys not configured — LIVE mode unavailable")
        return "No API keys configured."

    # Close existing client if any
    await close_binance_client()

    try:
        exchange = ccxt.kraken({
            "apiKey": key,
            "secret": secret,
            "enableRateLimit": True,
        })
        # Lightweight auth test — fetch balance
        await asyncio.wait_for(exchange.fetch_balance(), timeout=20.0)
        state.binance_client = exchange
        state.binance_keys["api_key"] = key
        state.binance_keys["api_secret"] = secret
        logger.info("Kraken client initialized successfully")
        return None  # success
    except asyncio.TimeoutError:
        logger.warning("Kraken client init timed out (20s)")
        try:
            await exchange.close()
        except Exception:
            pass
        state.binance_client = None
        return "Connection timed out. Kraken may be unreachable from this server."
    except Exception as e:
        err = str(e)
        logger.error(f"Failed to initialize Kraken client: {err}")
        try:
            await exchange.close()
        except Exception:
            pass
        state.binance_client = None
        err_lower = err.lower()
        if "invalid key" in err_lower or "apikey" in err_lower or "api key" in err_lower:
            return "Invalid API key — double-check you copied the full key correctly."
        if "invalid signature" in err_lower or "signature" in err_lower:
            return "Invalid signature — your API Secret is wrong. Copy it again exactly."
        if "permission" in err_lower or "nonce" in err_lower:
            return "Permission denied — ensure 'Create & Modify Orders' is enabled on the key."
        if "ip" in err_lower and ("restrict" in err_lower or "not allow" in err_lower):
            return "IP restriction — leave IP whitelist blank on Kraken API Management."
        return f"Kraken error: {err}"


async def close_binance_client():
    """Close the Kraken ccxt client and release the HTTP session."""
    if state.binance_client is not None:
        try:
            await state.binance_client.close()
        except Exception:
            pass
        state.binance_client = None
    logger.info("Kraken client closed")


async def fetch_live_price(symbol: str) -> float:
    """Fetch real-time price from Kraken."""
    exchange = state.binance_client
    if not exchange:
        raise RuntimeError("Kraken client not initialized")
    ticker = await exchange.fetch_ticker(to_kraken_symbol(symbol))
    return float(ticker["last"])


async def fetch_live_candles(symbol: str, interval: str = "5m", limit: int = 60):
    """Fetch real OHLCV candles from Kraken and return in internal format."""
    exchange = state.binance_client
    if not exchange:
        raise RuntimeError("Kraken client not initialized")
    tf = _TF_MAP.get(interval, "5m")
    ohlcv = await exchange.fetch_ohlcv(to_kraken_symbol(symbol), tf, limit=limit)
    # ccxt returns oldest-first: [[timestamp_ms, open, high, low, close, volume], ...]
    return [
        {
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
            "time": int(c[0]),
        }
        for c in ohlcv
    ]


async def place_live_market_order(symbol: str, side: str, quote_qty: float):
    """Place a real market order on Kraken spot. Returns order result dict.

    `quote_qty` is in USDT. Kraken needs base-currency amount, so we fetch
    the current price and convert.
    """
    exchange = state.binance_client
    if not exchange:
        raise RuntimeError("Kraken client not initialized")
    kraken_symbol = to_kraken_symbol(symbol)
    # Get current price to convert USDT → base currency amount
    ticker = await exchange.fetch_ticker(kraken_symbol)
    price = float(ticker["last"])
    if price <= 0:
        raise ValueError(f"Invalid price ({price}) for {symbol}")
    amount_base = quote_qty / price
    if side.upper() in ("BUY", "LONG"):
        order = await exchange.create_market_buy_order(kraken_symbol, amount_base)
    else:
        order = await exchange.create_market_sell_order(kraken_symbol, amount_base)
    return {
        "order_id": str(order.get("id", "")),
        "status": order.get("status", "closed"),
        "executed_qty": float(order.get("filled") or amount_base),
        "avg_price": float(order.get("average") or price),
    }


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



async def fetch_backtest_candles(symbol: str, period_days: int, interval_minutes: int = 15):
    """Fetch real historical OHLCV from Kraken for backtesting.

    Returns (candles, data_source) where data_source is 'kraken' or 'simulated'.
    Falls back to simulation transparently if the client is unavailable or returns
    insufficient data, so the backtester never crashes.

    Pagination: Kraken allows ~720 candles per request. We paginate using `since`
    until we cover the full period or receive fewer candles than the page size.
    """
    from services.backtest_service import generate_historical_candles

    exchange = state.binance_client
    if not exchange:
        logger.info(f"Backtest [{symbol}]: Kraken not connected — using simulation")
        return generate_historical_candles(symbol, period_days, interval_minutes), "simulated"

    # Kraken does not support 3m; fall back to 5m
    if interval_minutes == 3:
        interval_minutes = 5
    tf_map = {1: "1m", 5: "5m", 15: "15m", 30: "30m", 60: "1h", 240: "4h", 1440: "1d"}
    tf = tf_map.get(interval_minutes, "15m")

    since_ms = int(
        (datetime.now(timezone.utc) - timedelta(days=period_days)).timestamp() * 1000
    )
    kraken_symbol = to_kraken_symbol(symbol)
    all_ohlcv = []
    page_limit = 720

    try:
        while True:
            ohlcv = await exchange.fetch_ohlcv(
                kraken_symbol, tf, since=since_ms, limit=page_limit
            )
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            if len(ohlcv) < page_limit:
                break  # Last page
            last_ts = ohlcv[-1][0]
            since_ms = last_ts + interval_minutes * 60 * 1000
            # Stop once we've reached near-present
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            if since_ms >= now_ms - interval_minutes * 60 * 1000:
                break
            await asyncio.sleep(0.4)  # Respect Kraken rate limits
    except Exception as e:
        logger.warning(f"Backtest [{symbol}]: Kraken OHLCV fetch failed ({e}) — using simulation")
        return generate_historical_candles(symbol, period_days, interval_minutes), "simulated"

    # Filter out malformed candles (zero close price sometimes returned at boundaries)
    valid = [c for c in all_ohlcv if c[4] > 0]
    if len(valid) < 50:
        logger.warning(
            f"Backtest [{symbol}]: Only {len(valid)} valid candles returned — using simulation"
        )
        return generate_historical_candles(symbol, period_days, interval_minutes), "simulated"

    candles = [
        {
            "open":      float(c[1]),
            "high":      float(c[2]),
            "low":       float(c[3]),
            "close":     float(c[4]),
            "volume":    float(c[5]),
            "time":      datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).isoformat(),
            "timestamp": int(c[0]),
        }
        for c in valid
    ]
    logger.info(
        f"Backtest [{symbol}]: fetched {len(candles)} real {tf} candles from Kraken"
    )
    return candles, "kraken"

