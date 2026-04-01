"""Trading routes — dashboard, positions, trades, performance, leaderboard."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from auth import get_current_user
from database import db
import state

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(user=Depends(get_current_user)):
    balance_doc = await db.bot_state.find_one({"key": "account_balance"}, {"_id": 0})
    if not balance_doc:
        await db.bot_state.update_one({"key": "account_balance"}, {"$set": {"value": 10000.0}}, upsert=True)
        balance = 10000.0
    else:
        balance = balance_doc["value"]
    daily_pnl_doc = await db.bot_state.find_one({"key": "daily_pnl"}, {"_id": 0})
    daily_pnl = daily_pnl_doc["value"] if daily_pnl_doc else 0.0
    positions = await db.positions.find(
        {"status": "OPEN"},
        {"_id": 0, "id": 1, "symbol": 1, "side": 1, "entry_price": 1, "current_price": 1,
         "stop_loss": 1, "take_profit": 1, "quantity": 1, "unrealized_pnl": 1,
         "unrealized_pnl_percent": 1, "opened_at": 1, "mode": 1, "confidence_score": 1,
         "probability": 1, "ml_win_probability": 1, "market_regime": 1}
    ).to_list(20)
    trades = await db.trades.find({}, {"_id": 0}).sort("closed_at", -1).limit(10).to_list(10)
    total_trades = await db.trades.count_documents({})
    winning_trades = await db.trades.count_documents({"pnl": {"$gt": 0}})
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$pnl"}}}]
    total_pnl_result = await db.trades.aggregate(pipeline).to_list(1)
    total_pnl = total_pnl_result[0]["total"] if total_pnl_result else 0.0
    config = await db.bot_config.find_one({"active": True}, {"_id": 0})
    symbols = config.get("symbols", ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']) if config else ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']
    prices = {s: state.SYMBOL_PRICES.get(s, 0) for s in symbols}
    return {
        "balance": round(balance, 2),
        "daily_pnl": round(daily_pnl, 4),
        "total_pnl": round(total_pnl, 4),
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "open_positions_count": len(positions),
        "positions": positions,
        "recent_trades": trades,
        "prices": prices,
        "bot_status": {
            "running": state.bot_state["running"],
            "paused": state.bot_state["paused"],
            "mode": state.bot_state["mode"],
            "scan_count": state.bot_state["scan_count"],
            "last_scan": state.bot_state["last_scan"]
        }
    }


@router.get("/positions")
async def get_positions(status: str = "OPEN", user=Depends(get_current_user)):
    positions = await db.positions.find({"status": status}, {"_id": 0}).sort("opened_at", -1).to_list(100)
    return positions


@router.post("/positions/{position_id}/close")
async def close_position(position_id: str, user=Depends(get_current_user)):
    pos = await db.positions.find_one({"id": position_id, "status": "OPEN"}, {"_id": 0})
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    current_price = state.SYMBOL_PRICES.get(pos["symbol"], pos["entry_price"])
    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
    pnl_percent = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
    now = datetime.now(timezone.utc).isoformat()
    await db.positions.update_one(
        {"id": position_id},
        {"$set": {"status": "CLOSED", "exit_price": round(current_price, 8), "exit_reason": "MANUAL", "pnl": round(pnl, 4), "pnl_percent": round(pnl_percent, 4), "closed_at": now}}
    )
    trade_doc = {
        "id": str(uuid.uuid4()),
        "symbol": pos["symbol"],
        "side": pos.get("side", "LONG"),
        "entry_price": pos["entry_price"],
        "exit_price": round(current_price, 8),
        "quantity": pos["quantity"],
        "pnl": round(pnl, 4),
        "pnl_percent": round(pnl_percent, 4),
        "exit_reason": "MANUAL",
        "opened_at": pos["opened_at"],
        "closed_at": now,
        "mode": pos.get("mode", "DRY"),
        "stop_loss": pos["stop_loss"],
        "take_profit": pos["take_profit"]
    }
    await db.trades.insert_one(trade_doc)
    await db.bot_state.update_one({"key": "daily_pnl"}, {"$inc": {"value": round(pnl, 4)}}, upsert=True)
    return {"status": "closed", "pnl": round(pnl, 4)}


@router.get("/trades")
async def get_trades(limit: int = 50, skip: int = 0, symbol: Optional[str] = None, user=Depends(get_current_user)):
    query = {}
    if symbol:
        query["symbol"] = symbol
    trades = await db.trades.find(query, {"_id": 0}).sort("closed_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.trades.count_documents(query)
    return {"trades": trades, "total": total}


@router.get("/performance")
async def get_performance(user=Depends(get_current_user)):
    trades = await db.trades.find(
        {}, {"_id": 0, "symbol": 1, "pnl": 1, "pnl_percent": 1, "closed_at": 1, "opened_at": 1,
             "stop_loss": 1, "entry_price": 1, "quantity": 1}
    ).sort("closed_at", 1).limit(500).to_list(500)
    cumulative_pnl = []
    running_pnl = 0
    for t in trades:
        running_pnl += t.get("pnl", 0)
        cumulative_pnl.append({"date": t.get("closed_at", ""), "pnl": round(running_pnl, 4), "trade_pnl": t.get("pnl", 0)})
    total = len(trades)
    wins = len([t for t in trades if t.get("pnl", 0) > 0])
    losses = len([t for t in trades if t.get("pnl", 0) <= 0])
    by_symbol = {}
    for t in trades:
        s = t["symbol"]
        if s not in by_symbol:
            by_symbol[s] = {"symbol": s, "trades": 0, "pnl": 0, "wins": 0, "losses": 0}
        by_symbol[s]["trades"] += 1
        by_symbol[s]["pnl"] += t.get("pnl", 0)
        if t.get("pnl", 0) > 0:
            by_symbol[s]["wins"] += 1
        else:
            by_symbol[s]["losses"] += 1
    win_amounts = [t["pnl"] for t in trades if t.get("pnl", 0) > 0]
    loss_amounts = [t["pnl"] for t in trades if t.get("pnl", 0) <= 0]
    avg_win = sum(win_amounts) / len(win_amounts) if win_amounts else 0
    avg_loss = sum(loss_amounts) / len(loss_amounts) if loss_amounts else 0
    peak = 0
    max_dd = 0
    running = 0
    for t in trades:
        running += t.get("pnl", 0)
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    return {
        "cumulative_pnl": cumulative_pnl,
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 2) if total > 0 else 0,
        "total_pnl": round(running_pnl, 4) if trades else 0,
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "max_drawdown": round(max_dd, 4),
        "by_symbol": list(by_symbol.values()),
        "profit_factor": round(abs(sum(win_amounts)) / abs(sum(loss_amounts)), 2) if loss_amounts and sum(loss_amounts) != 0 else 0
    }


@router.get("/leaderboard")
async def get_leaderboard(user=Depends(get_current_user)):
    trades = await db.trades.find(
        {}, {"_id": 0, "symbol": 1, "pnl": 1, "pnl_percent": 1, "closed_at": 1, "opened_at": 1,
             "exit_reason": 1, "entry_price": 1, "exit_price": 1, "stop_loss": 1, "quantity": 1}
    ).sort("closed_at", 1).limit(1000).to_list(1000)
    if not trades:
        return {
            "symbol_rankings": [], "best_trades": [], "worst_trades": [],
            "streaks": {"current": 0, "current_type": "none", "best_win": 0, "worst_loss": 0},
            "time_analysis": {"best_hour": None, "worst_hour": None, "hourly_pnl": []},
            "exit_analysis": [], "weekly_pnl": [], "risk_reward_avg": 0,
            "total_fees_saved_dry": 0, "consistency_score": 0
        }
    by_symbol = {}
    for t in trades:
        s = t["symbol"]
        if s not in by_symbol:
            by_symbol[s] = {"symbol": s, "trades": 0, "pnl": 0, "wins": 0, "losses": 0, "best_trade": 0, "worst_trade": 0, "avg_pnl": 0, "avg_hold_time_min": 0, "total_hold_time": 0}
        by_symbol[s]["trades"] += 1
        pnl = t.get("pnl", 0)
        by_symbol[s]["pnl"] = round(by_symbol[s]["pnl"] + pnl, 4)
        if pnl > 0:
            by_symbol[s]["wins"] += 1
        else:
            by_symbol[s]["losses"] += 1
        if pnl > by_symbol[s]["best_trade"]:
            by_symbol[s]["best_trade"] = round(pnl, 4)
        if pnl < by_symbol[s]["worst_trade"]:
            by_symbol[s]["worst_trade"] = round(pnl, 4)
        if t.get("opened_at") and t.get("closed_at"):
            try:
                opened = datetime.fromisoformat(t["opened_at"].replace("Z", "+00:00"))
                closed = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
                by_symbol[s]["total_hold_time"] += (closed - opened).total_seconds() / 60
            except Exception:
                pass
    for s in by_symbol.values():
        s["win_rate"] = round(s["wins"] / s["trades"] * 100, 1) if s["trades"] > 0 else 0
        s["avg_pnl"] = round(s["pnl"] / s["trades"], 4) if s["trades"] > 0 else 0
        s["avg_hold_time_min"] = round(s["total_hold_time"] / s["trades"], 1) if s["trades"] > 0 else 0
        s.pop("total_hold_time", None)
    symbol_rankings = sorted(by_symbol.values(), key=lambda x: x["pnl"], reverse=True)
    for i, sr in enumerate(symbol_rankings):
        sr["rank"] = i + 1
    sorted_by_pnl = sorted(trades, key=lambda x: x.get("pnl", 0), reverse=True)
    best_trades = [{"symbol": t["symbol"], "pnl": round(t.get("pnl", 0), 4), "pnl_percent": round(t.get("pnl_percent", 0), 2), "entry_price": t.get("entry_price", 0), "exit_price": t.get("exit_price", 0), "exit_reason": t.get("exit_reason", ""), "closed_at": t.get("closed_at", "")} for t in sorted_by_pnl[:5]]
    worst_trades = [{"symbol": t["symbol"], "pnl": round(t.get("pnl", 0), 4), "pnl_percent": round(t.get("pnl_percent", 0), 2), "entry_price": t.get("entry_price", 0), "exit_price": t.get("exit_price", 0), "exit_reason": t.get("exit_reason", ""), "closed_at": t.get("closed_at", "")} for t in sorted_by_pnl[-5:][::-1]]
    current_streak = 0
    current_type = "none"
    best_win_streak = 0
    worst_loss_streak = 0
    temp_win = 0
    temp_loss = 0
    for t in trades:
        if t.get("pnl", 0) > 0:
            temp_win += 1
            temp_loss = 0
            if temp_win > best_win_streak:
                best_win_streak = temp_win
        else:
            temp_loss += 1
            temp_win = 0
            if temp_loss > worst_loss_streak:
                worst_loss_streak = temp_loss
    for t in reversed(trades):
        if current_type == "none":
            current_type = "win" if t.get("pnl", 0) > 0 else "loss"
            current_streak = 1
        elif (current_type == "win" and t.get("pnl", 0) > 0) or (current_type == "loss" and t.get("pnl", 0) <= 0):
            current_streak += 1
        else:
            break
    hourly = {}
    for t in trades:
        if t.get("closed_at"):
            try:
                closed = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
                hour = closed.hour
                if hour not in hourly:
                    hourly[hour] = {"hour": hour, "pnl": 0, "trades": 0, "wins": 0}
                hourly[hour]["pnl"] = round(hourly[hour]["pnl"] + t.get("pnl", 0), 4)
                hourly[hour]["trades"] += 1
                if t.get("pnl", 0) > 0:
                    hourly[hour]["wins"] += 1
            except Exception:
                pass
    hourly_list = sorted(hourly.values(), key=lambda x: x["hour"])
    best_hour = max(hourly.values(), key=lambda x: x["pnl"]) if hourly else None
    worst_hour = min(hourly.values(), key=lambda x: x["pnl"]) if hourly else None
    exit_stats = {}
    for t in trades:
        reason = t.get("exit_reason", "UNKNOWN")
        if reason not in exit_stats:
            exit_stats[reason] = {"reason": reason, "count": 0, "pnl": 0, "wins": 0}
        exit_stats[reason]["count"] += 1
        exit_stats[reason]["pnl"] = round(exit_stats[reason]["pnl"] + t.get("pnl", 0), 4)
        if t.get("pnl", 0) > 0:
            exit_stats[reason]["wins"] += 1
    for e in exit_stats.values():
        e["win_rate"] = round(e["wins"] / e["count"] * 100, 1) if e["count"] > 0 else 0
        e["avg_pnl"] = round(e["pnl"] / e["count"], 4) if e["count"] > 0 else 0
    weekly = {}
    for t in trades:
        if t.get("closed_at"):
            try:
                closed = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
                week_key = closed.strftime("%Y-W%W")
                if week_key not in weekly:
                    weekly[week_key] = {"week": week_key, "pnl": 0, "trades": 0, "wins": 0}
                weekly[week_key]["pnl"] = round(weekly[week_key]["pnl"] + t.get("pnl", 0), 4)
                weekly[week_key]["trades"] += 1
                if t.get("pnl", 0) > 0:
                    weekly[week_key]["wins"] += 1
            except Exception:
                pass
    weekly_list = sorted(weekly.values(), key=lambda x: x["week"])
    rr_ratios = []
    for t in trades:
        if t.get("pnl", 0) > 0 and t.get("stop_loss") and t.get("entry_price"):
            risk = abs(t["entry_price"] - t["stop_loss"]) * t.get("quantity", 0)
            if risk > 0:
                rr_ratios.append(t["pnl"] / risk)
    avg_rr = round(sum(rr_ratios) / len(rr_ratios), 2) if rr_ratios else 0
    profitable_weeks = len([w for w in weekly.values() if w["pnl"] > 0])
    total_weeks = len(weekly)
    consistency = round(profitable_weeks / total_weeks * 100, 1) if total_weeks > 0 else 0
    return {
        "symbol_rankings": symbol_rankings,
        "best_trades": best_trades,
        "worst_trades": worst_trades,
        "streaks": {"current": current_streak, "current_type": current_type, "best_win": best_win_streak, "worst_loss": worst_loss_streak},
        "time_analysis": {"best_hour": best_hour, "worst_hour": worst_hour, "hourly_pnl": hourly_list},
        "exit_analysis": list(exit_stats.values()),
        "weekly_pnl": weekly_list,
        "risk_reward_avg": avg_rr,
        "consistency_score": consistency
    }
