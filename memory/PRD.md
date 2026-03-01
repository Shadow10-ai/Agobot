# AgoBot - Crypto Trading Dashboard PRD

## Original Problem Statement
Build a trading app focused on crypto trading. The app should execute trades autonomously using a Node.js trading bot (ported to Python/FastAPI). User provided Binance API keys and requested a Performance Leaderboard.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + shadcn/ui + Recharts
- **Backend**: FastAPI (Python) with async trading bot engine
- **Database**: MongoDB (motor async driver)
- **Auth**: JWT-based authentication
- **Trading**: DRY mode simulation with technical indicators (RSI, MACD, BB, ATR, EMA)

## User Personas
- Crypto trader wanting automated trading with monitoring dashboard
- Needs real-time position tracking, PnL analytics, and bot controls

## Core Requirements (Static)
- JWT authentication (register/login)
- Dashboard with KPI cards, positions, price ticker, PnL chart
- Trading bot with technical analysis signals
- Trade history with filtering and CSV export
- Bot configuration panel
- Telegram notification settings
- Performance Leaderboard with symbol rankings

## What's Been Implemented (Jan 2026)
1. **Auth system**: Register, login, JWT token management
2. **Dashboard**: Account balance, daily/total PnL, win rate, positions, price ticker, recent trades
3. **Trading Bot Engine**: DRY mode with RSI, MACD, BB, ATR, EMA-based signals, SL/TP/trailing stops
4. **Trade History**: Paginated table with symbol filter, CSV export
5. **Configuration**: Trading parameters, indicator settings, Telegram config, symbol toggles
6. **Performance Leaderboard**: Symbol rankings, best/worst trades, win/loss streaks, time analysis, exit strategy breakdown, weekly PnL, risk-reward ratio, consistency score
7. **Binance API keys**: Stored in backend .env
8. **Branding**: Renamed to AgoBot

## Prioritized Backlog
### P0 (Critical)
- Switch from DRY to LIVE mode (requires testing with real funds)

### P1 (High)
- WebSocket real-time price updates
- Candlestick chart visualization
- Real Binance API integration for live trading

### P2 (Medium)
- Multi-exchange support
- Advanced strategy configuration
- Email notifications
- Mobile-responsive improvements

## Next Tasks
- Test with real Binance API in LIVE mode
- Add Telegram bot token and chat ID for notifications
- Implement real-time WebSocket price feeds
