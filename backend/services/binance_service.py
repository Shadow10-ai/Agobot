"""Binance client management and data fetching (with simulation fallback)."""
import logging
import random
from datetime import datetime, timezone, timedelta
import state
from config import BINANCE_API_KEY, BINANCE_API_SECRET
from binance import AsyncClient as BinanceAsyncClient

logger = logging.getLogger(__name__)


async def init_binance_client():
    """Initialize the Binance async client if API keys are available."""
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        logger.warning("Binance API keys not configured — LIVE mode unavailable")
        return
    try:
        state.binance_client = await BinanceAsyncClient.create(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET
        )
        logger.info("Binance async client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Binance client: {e}")
        state.binance_client = None


async def close_binance_client():
    """Close the Binance async client."""
    if state.binance_client:
        await state.binance_client.close_connection()
        state.binance_client = None
        logger.info("Binance client connection closed")


async def fetch_live_price(symbol: str) -> float:
    """Fetch real-time price from Binance."""
    if not state.binance_client:
        raise RuntimeError("Binance client not initialized")
    ticker = await state.binance_client.get_symbol_ticker(symbol=symbol)
    return float(ticker["price"])


async def fetch_live_candles(symbol: str, interval: str = "3m", limit: int = 60):
    """Fetch real kline candles from Binance and return in our internal format."""
    if not state.binance_client:
        raise RuntimeError("Binance client not initialized")
    raw = await state.binance_client.get_klines(symbol=symbol, interval=interval, limit=limit)
    candles = []
    for k in raw:
        candles.append({
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "time": int(k[0])
        })
    return candles


async def place_live_market_order(symbol: str, side: str, quote_qty: float):
    """Place a real market order on Binance. Returns order result dict."""
    if not state.binance_client:
        raise RuntimeError("Binance client not initialized")
    order = await state.binance_client.create_order(
        symbol=symbol,
        side=side,
        type="MARKET",
        quoteOrderQty=quote_qty
    )
    return {
        "order_id": order["orderId"],
        "status": order["status"],
        "executed_qty": float(order["executedQty"]),
        "cummulative_quote_qty": float(order["cummulativeQuoteQty"]),
        "avg_price": float(order["cummulativeQuoteQty"]) / float(order["executedQty"]) if float(order["executedQty"]) > 0 else 0,
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
