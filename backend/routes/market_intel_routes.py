"""Market intelligence routes — order flow, funding rates, whale activity."""
from fastapi import APIRouter, Depends
from auth import get_current_user
from config import VALID_SYMBOLS
import state
from services.market_intel import analyze_order_book, fetch_funding_rates, track_whale_activity

router = APIRouter()


@router.get("/orderflow")
async def get_order_flow_summary(user=Depends(get_current_user)):
    results = []
    for symbol in VALID_SYMBOLS[:6]:
        data = await analyze_order_book(symbol, limit=50)
        results.append({
            "symbol": symbol,
            "price": state.SYMBOL_PRICES.get(symbol, 0),
            "pressure": data["pressure"],
            "imbalance_ratio": data["imbalance_ratio"],
            "bid_walls": len(data.get("bid_walls", [])),
            "ask_walls": len(data.get("ask_walls", [])),
            "source": data["source"]
        })
    return {"symbols": results}


@router.get("/orderflow/{symbol}")
async def get_symbol_order_flow(symbol: str, user=Depends(get_current_user)):
    return await analyze_order_book(symbol, limit=100)


@router.get("/funding-rates")
async def get_funding_rates(user=Depends(get_current_user)):
    rates = await fetch_funding_rates(VALID_SYMBOLS)
    arb_count = sum(1 for v in rates.values() if v.get("arb_opportunity"))
    return {"rates": rates, "arb_opportunities": arb_count, "symbols_analyzed": len(rates)}


@router.get("/whale-activity")
async def get_whale_activity(user=Depends(get_current_user)):
    return await track_whale_activity(VALID_SYMBOLS)
