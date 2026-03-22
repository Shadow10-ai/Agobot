"""Backtest and strategy comparison routes."""
from fastapi import APIRouter, HTTPException, Depends
from auth import get_current_user
from config import VALID_SYMBOLS
from models import BacktestRequest, StrategyCompareRequest
from services.backtest_service import generate_historical_candles, run_backtest

router = APIRouter()


@router.post("/backtest")
async def run_backtest_api(params: BacktestRequest, user=Depends(get_current_user)):
    if params.symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Choose from: {VALID_SYMBOLS}")
    if params.period_days < 1 or params.period_days > 180:
        raise HTTPException(status_code=400, detail="period_days must be between 1 and 180")
    candles = generate_historical_candles(params.symbol, params.period_days)
    result = run_backtest(candles, params)
    result["params"] = params.model_dump()
    return result


@router.post("/backtest/compare")
async def compare_strategies(req: StrategyCompareRequest, user=Depends(get_current_user)):
    if req.symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Choose from: {VALID_SYMBOLS}")
    candles = generate_historical_candles(req.symbol, req.period_days)
    result_a = run_backtest(candles, req.strategy_a)
    result_b = run_backtest(candles, req.strategy_b)
    a_sum = result_a["summary"]
    b_sum = result_b["summary"]
    winner_fields = {}
    for field in ["win_rate", "total_pnl", "profit_factor", "sharpe_ratio"]:
        winner_fields[field] = "A" if a_sum.get(field, 0) >= b_sum.get(field, 0) else "B"
    for field in ["max_drawdown_pct", "worst_loss_streak"]:
        winner_fields[field] = "A" if a_sum.get(field, 0) <= b_sum.get(field, 0) else "B"
    a_wins = sum(1 for v in winner_fields.values() if v == "A")
    b_wins = sum(1 for v in winner_fields.values() if v == "B")
    overall_winner = "A" if a_wins >= b_wins else "B"
    return {
        "symbol": req.symbol,
        "period_days": req.period_days,
        "candle_count": len(candles),
        "strategy_a": {
            "label": req.strategy_a.label or "Strategy A",
            "summary": result_a["summary"],
            "equity_curve": result_a["equity_curve"],
            "monthly_pnl": result_a["monthly_pnl"],
        },
        "strategy_b": {
            "label": req.strategy_b.label or "Strategy B",
            "summary": result_b["summary"],
            "equity_curve": result_b["equity_curve"],
            "monthly_pnl": result_b["monthly_pnl"],
        },
        "comparison": {
            "winner": overall_winner,
            "winner_score": f"{a_wins}/{len(winner_fields)}",
            "field_winners": winner_fields,
        }
    }
