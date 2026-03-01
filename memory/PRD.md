# AgoBot - Crypto Trading Dashboard PRD

## Original Problem Statement
Build a trading app focused on crypto trading. The app should execute trades autonomously using a Node.js trading bot (ported to Python/FastAPI). User provided Binance API keys and requested a Performance Leaderboard and Strategy Backtester.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + shadcn/ui + Recharts
- **Backend**: FastAPI (Python) with async trading bot engine
- **Database**: MongoDB (motor async driver)
- **Auth**: JWT-based authentication
- **Trading**: DRY mode simulation with technical indicators (RSI, MACD, BB, ATR, EMA)

## What's Been Implemented (Mar 2026)
1. **Auth system**: Register, login, JWT token management
2. **Dashboard**: Account balance, daily/total PnL, win rate, positions, price ticker, recent trades
3. **Trading Bot Engine**: DRY mode with RSI, MACD, BB, ATR, EMA-based signals, SL/TP/trailing stops
4. **Trade History**: Paginated table with symbol filter, CSV export
5. **Configuration**: Trading parameters, indicator settings, Telegram config, symbol toggles
6. **Performance Leaderboard**: Symbol rankings, best/worst trades, streaks, time analysis, exit breakdown, weekly PnL
7. **Strategy Backtester**: Historical data replay, equity curve, monthly PnL, exit breakdown, trade list, Sharpe ratio, expectancy, profit factor, max drawdown
8. **Binance API keys**: Stored in backend .env
9. **Branding**: AgoBot

## Prioritized Backlog
- P0: Switch from DRY to LIVE mode
- P1: WebSocket real-time price updates, candlestick charts
- P2: Multi-exchange support, strategy comparison, Monte Carlo simulation
