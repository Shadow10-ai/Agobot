"""Market intelligence — order flow, funding rates, whale activity."""
import logging
import random
from datetime import datetime, timezone, timedelta
import state
from config import to_kraken_symbol

logger = logging.getLogger(__name__)


async def analyze_order_book(symbol, limit=100):
    """Analyze order book depth for bid/ask imbalance, support/resistance walls."""
    price = state.SYMBOL_PRICES.get(symbol, 0)
    if state.binance_client:
        try:
            book = await state.binance_client.fetch_order_book(to_kraken_symbol(symbol), limit)
            bids = [(float(b[0]), float(b[1])) for b in book["bids"]]
            asks = [(float(a[0]), float(a[1])) for a in book["asks"]]
        except Exception as e:
            logger.warning(f"Failed to fetch order book for {symbol}: {e}")
            bids, asks = _simulate_order_book(price, limit)
    else:
        bids, asks = _simulate_order_book(price, limit)
    total_bid_vol = sum(qty for _, qty in bids)
    total_ask_vol = sum(qty for _, qty in asks)
    imbalance = total_bid_vol / total_ask_vol if total_ask_vol > 0 else 1.0
    avg_bid_size = total_bid_vol / len(bids) if bids else 1
    avg_ask_size = total_ask_vol / len(asks) if asks else 1
    bid_walls = [{"price": p, "quantity": q, "usdt_value": round(p * q, 2)} for p, q in bids if q > avg_bid_size * 3][:5]
    ask_walls = [{"price": p, "quantity": q, "usdt_value": round(p * q, 2)} for p, q in asks if q > avg_ask_size * 3][:5]
    depth_levels = {}
    for pct in [0.5, 1.0, 2.0, 5.0]:
        bid_depth = sum(q for p, q in bids if p >= price * (1 - pct / 100))
        ask_depth = sum(q for p, q in asks if p <= price * (1 + pct / 100))
        depth_levels[f"{pct}%"] = {
            "bid_volume": round(bid_depth, 4),
            "ask_volume": round(ask_depth, 4),
            "bid_usdt": round(bid_depth * price, 2),
            "ask_usdt": round(ask_depth * price, 2),
            "ratio": round(bid_depth / ask_depth, 4) if ask_depth > 0 else 0,
        }
    pressure = "NEUTRAL"
    if imbalance > 1.5:
        pressure = "STRONG_BUY"
    elif imbalance > 1.1:
        pressure = "BUY"
    elif imbalance < 0.67:
        pressure = "STRONG_SELL"
    elif imbalance < 0.9:
        pressure = "SELL"
    else:
        pressure = "NEUTRAL"
    top_bids = [{"price": round(p, 8), "quantity": round(q, 8), "total": round(p * q, 2)} for p, q in bids[:20]]
    top_asks = [{"price": round(p, 8), "quantity": round(q, 8), "total": round(p * q, 2)} for p, q in asks[:20]]
    return {
        "symbol": symbol,
        "price": price,
        "total_bid_volume": round(total_bid_vol, 4),
        "total_ask_volume": round(total_ask_vol, 4),
        "imbalance_ratio": round(imbalance, 4),
        "pressure": pressure,
        "bid_walls": bid_walls,
        "ask_walls": ask_walls,
        "depth_levels": depth_levels,
        "top_bids": top_bids,
        "top_asks": top_asks,
        "source": "kraken" if state.binance_client else "simulated",
    }


def _simulate_order_book(price, limit=100):
    """Generate realistic simulated order book data."""
    if price <= 0:
        price = 100
    spread = price * 0.0005
    bids, asks = [], []
    for i in range(limit):
        bid_price = price - spread * (i + 1) * random.uniform(0.8, 1.2)
        ask_price = price + spread * (i + 1) * random.uniform(0.8, 1.2)
        base_qty = random.uniform(0.01, 1.0) * (50000 / price)
        wall_mult = random.choice([1, 1, 1, 1, 1, 3, 5]) if random.random() < 0.15 else 1
        bid_qty = base_qty * (1 + i * 0.05) * wall_mult
        ask_qty = base_qty * (1 + i * 0.05) * (random.choice([1, 1, 1, 1, 3, 5]) if random.random() < 0.15 else 1)
        bids.append((round(bid_price, 8), round(bid_qty, 8)))
        asks.append((round(ask_price, 8), round(ask_qty, 8)))
    return bids, asks


async def fetch_funding_rates(symbols):
    """Funding rates are perpetual-futures specific. Kraken spot has none — always simulate."""
    results = {}
    for symbol in symbols:
        rate = random.gauss(0.01, 0.02)
        results[symbol] = {
            "current_rate": round(rate, 6),
            "avg_rate_8h": round(rate + random.gauss(0, 0.005), 6),
            "source": "simulated",
        }
    for symbol, data in results.items():
        rate = data["current_rate"]
        if rate > 0.03:
            data["sentiment"] = "EXTREMELY_BULLISH"
            data["signal"] = "Longs are overleveraged — contrarian SHORT"
            data["arb_opportunity"] = True
        elif rate > 0.01:
            data["sentiment"] = "BULLISH"
            data["signal"] = "Moderate long bias"
            data["arb_opportunity"] = False
        elif rate < -0.03:
            data["sentiment"] = "EXTREMELY_BEARISH"
            data["signal"] = "Shorts are overleveraged — contrarian LONG"
            data["arb_opportunity"] = True
        elif rate < -0.01:
            data["sentiment"] = "BEARISH"
            data["signal"] = "Moderate short bias"
            data["arb_opportunity"] = False
        else:
            data["sentiment"] = "NEUTRAL"
            data["signal"] = "No strong directional bias"
            data["arb_opportunity"] = False
        data["annualized_yield"] = round(abs(rate) * 3 * 365, 4)
    return results


async def track_whale_activity(symbols, min_trade_usdt=50000):
    """Track large trades (whale activity) from recent aggregated trades."""
    whale_trades = []
    for symbol in symbols[:4]:
        price = state.SYMBOL_PRICES.get(symbol, 0)
        if state.binance_client and price > 0:
            try:
                trades = await state.binance_client.fetch_trades(to_kraken_symbol(symbol), limit=100)
                for t in trades:
                    qty = float(t["amount"])
                    trade_price = float(t["price"])
                    usdt_value = qty * trade_price
                    if usdt_value >= min_trade_usdt:
                        whale_trades.append({
                            "symbol": symbol,
                            "price": trade_price,
                            "quantity": qty,
                            "usdt_value": round(usdt_value, 2),
                            "side": "BUY" if t.get("side") == "buy" else "SELL",
                            "time": datetime.fromtimestamp(t["timestamp"] / 1000, tz=timezone.utc).isoformat(),
                            "source": "kraken",
                        })
                continue
            except Exception:
                pass
        for _ in range(random.randint(1, 4)):
            if price <= 0:
                price = 100
            qty = random.uniform(50000, 500000) / price
            whale_trades.append({
                "symbol": symbol,
                "price": round(price * random.uniform(0.998, 1.002), 8),
                "quantity": round(qty, 8),
                "usdt_value": round(qty * price, 2),
                "side": random.choice(["BUY", "SELL"]),
                "time": (datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 60))).isoformat(),
                "source": "simulated",
            })
    whale_trades.sort(key=lambda x: -x["usdt_value"])
    total_buy = sum(t["usdt_value"] for t in whale_trades if t["side"] == "BUY")
    total_sell = sum(t["usdt_value"] for t in whale_trades if t["side"] == "SELL")
    buy_count = sum(1 for t in whale_trades if t["side"] == "BUY")
    sell_count = sum(1 for t in whale_trades if t["side"] == "SELL")
    net_flow = total_buy - total_sell
    if net_flow > 100000:
        whale_signal = "ACCUMULATION"
    elif net_flow < -100000:
        whale_signal = "DISTRIBUTION"
    else:
        whale_signal = "NEUTRAL"
    symbol_breakdown = {}
    for t in whale_trades:
        s = t["symbol"]
        if s not in symbol_breakdown:
            symbol_breakdown[s] = {"buy_volume": 0, "sell_volume": 0, "count": 0}
        if t["side"] == "BUY":
            symbol_breakdown[s]["buy_volume"] += t["usdt_value"]
        else:
            symbol_breakdown[s]["sell_volume"] += t["usdt_value"]
        symbol_breakdown[s]["count"] += 1
    for s in symbol_breakdown:
        b = symbol_breakdown[s]
        b["buy_volume"] = round(b["buy_volume"], 2)
        b["sell_volume"] = round(b["sell_volume"], 2)
        b["net_flow"] = round(b["buy_volume"] - b["sell_volume"], 2)
        b["signal"] = "ACCUMULATION" if b["net_flow"] > 10000 else ("DISTRIBUTION" if b["net_flow"] < -10000 else "NEUTRAL")
    return {
        "whale_trades": whale_trades[:20],
        "total_whale_buys": round(total_buy, 2),
        "total_whale_sells": round(total_sell, 2),
        "net_flow": round(net_flow, 2),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "whale_signal": whale_signal,
        "min_trade_usdt": min_trade_usdt,
        "symbol_breakdown": symbol_breakdown,
    }
