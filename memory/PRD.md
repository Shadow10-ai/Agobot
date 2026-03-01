# AgoBot - Crypto Trading Dashboard PRD

## Original Problem Statement
Build a trading app focused on crypto trading with autonomous execution. Ported from Node.js to Python/FastAPI. Includes Binance API keys, Performance Leaderboard, Strategy Backtester, and 5 robustness improvements.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + shadcn/ui + Recharts
- **Backend**: FastAPI (Python) with async trading bot engine
- **Database**: MongoDB (motor async driver)
- **Auth**: JWT-based authentication
- **Trading**: DRY mode simulation with technical indicators

## What's Been Implemented (Mar 2026)
1. **Auth system**: Register, login, JWT token management
2. **Dashboard**: Account balance, daily/total PnL, win rate, positions, price ticker, recent trades
3. **Trading Bot Engine**: DRY mode with RSI, MACD, BB, ATR, EMA signals, SL/TP/trailing stops
4. **Trade History**: Paginated table with symbol filter, CSV export
5. **Configuration**: Trading params, indicator settings, Telegram config, symbol toggles
6. **Performance Leaderboard**: Symbol rankings, best/worst trades, streaks, time/exit analysis
7. **Strategy Backtester**: Historical replay with slippage, fees, volume filter, volatility regime
8. **Robustness Improvements** (Latest):
   - Volume filter: rejects low-volume signals (configurable multiplier)
   - Volatility regime detection: auto-reduces position size in high volatility
   - Correlation-aware sizing: prevents overexposure to correlated pairs
   - Slippage & fee modeling: realistic P&L in backtester
   - Structure-based stop loss: places SL below swing lows instead of arbitrary ATR
9. **Strategy Comparison**: Side-by-side comparison on identical price data with preset strategies
10. **Binance API keys**: Stored in backend .env
11. **Branding**: AgoBot

## Prioritized Backlog
- P0: Switch from DRY to LIVE mode
- P1: WebSocket real-time price updates, candlestick charts, walk-forward optimization
- P2: Multi-exchange support, Monte Carlo simulation, news/event filter
