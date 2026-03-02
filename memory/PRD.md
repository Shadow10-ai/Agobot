# AgoBot - Crypto Trading Dashboard PRD

## Original Problem Statement
Build a trading app focused on crypto trading with autonomous execution. Ported from Node.js to Python/FastAPI. Includes Binance API keys, Performance Leaderboard, Strategy Backtester, and 5 robustness improvements.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + shadcn/ui + Recharts
- **Backend**: FastAPI (Python) with async trading bot engine + python-binance
- **Database**: MongoDB (motor async driver)
- **Auth**: JWT-based authentication
- **Trading**: DRY/LIVE mode with Binance API integration

## What's Been Implemented
1. **Auth system**: Register, login, JWT token management
2. **Dashboard**: Account balance, daily/total PnL, win rate, positions, price ticker, recent trades
3. **Trading Bot Engine**: DRY/LIVE mode with RSI, MACD, BB, ATR, EMA signals, SL/TP/trailing stops
4. **Trade History**: Paginated table with symbol filter, CSV export
5. **Configuration**: Trading params, indicator settings, Telegram config, symbol toggles, **DRY/LIVE mode toggle**
6. **Performance Leaderboard**: Symbol rankings, best/worst trades, streaks, time/exit analysis
7. **Strategy Backtester**: Historical replay with slippage, fees, volume filter, volatility regime
8. **Robustness Improvements**:
   - Volume filter, Volatility regime detection, Correlation-aware sizing
   - Slippage & fee modeling, Structure-based stop loss
9. **Strategy Comparison**: Side-by-side comparison with preset strategies
10. **Binance Integration**: python-binance AsyncClient for LIVE mode (real price fetching + order execution)
11. **DRY/LIVE Mode Toggle** (Mar 2026):
    - Toggle on Config page with DRY/LIVE buttons
    - Confirmation dialog with safety warnings when switching to LIVE
    - Backend validates Binance client is connected before allowing LIVE mode
    - Bot scan loop branches: simulated data in DRY, real Binance API in LIVE
    - Positions tagged with mode (DRY/LIVE) for tracking
12. **Production Readiness** (Mar 2026):
    - `/api/health` endpoint for Kubernetes probes
    - Graceful index creation, efficient cleanup
    - `load_dotenv(override=False)` for production env safety
    - Reduced frontend polling (30s), defensive bot auto-start

## Key API Endpoints
- Auth: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- Health: `GET /api/health` (no auth)
- Dashboard: `GET /api/dashboard`
- Bot: `GET /api/bot/status`, `POST /api/bot/start|stop|pause|resume`
- Config: `GET/PUT /api/bot/config`, `PUT /api/bot/telegram`
- **Mode**: `GET /api/bot/mode`, `PUT /api/bot/mode` (DRY/LIVE toggle)
- Positions: `GET /api/positions`, `POST /api/positions/{id}/close`
- Trades: `GET /api/trades`
- Analytics: `GET /api/performance`, `GET /api/leaderboard`
- Backtester: `POST /api/backtest`, `POST /api/compare`

## Test Credentials
- Email: user@example.com, Password: password

## Prioritized Backlog
- P1: WebSocket real-time price updates, candlestick charts
- P1: Walk-forward optimization
- P2: Multi-exchange support, Monte Carlo simulation, news/event filter
- P3: Refactor server.py into modular files
