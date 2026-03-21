# AgoBot - Crypto Trading Dashboard PRD

## Original Problem Statement
Build a crypto trading bot with autonomous execution. Enhanced with ML-powered smart filters and professional-grade risk management for institutional-quality trading.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + shadcn/ui + Recharts + lucide-react
- **Backend**: FastAPI (Python) + python-binance + LightGBM ML + NumPy
- **Database**: MongoDB (motor async driver)
- **Auth**: JWT-based authentication
- **Trading**: DRY/LIVE mode + 12-gate smart filter + ML model + Risk management

## Features Implemented

### Core (Phase 0)
1. Auth (register, login, JWT), Dashboard, Trading bot engine (DRY/LIVE)
2. Trade history, Performance leaderboard, Strategy backtester, Strategy comparison
3. DRY/LIVE mode toggle, LONG/SHORT toggle, Binance API integration

### Phase 1: Smart Filters & Dataset Builder
4. 12-Gate Signal Filter Chain (overtrade, cooldown, correlation, probability, volume, spread, slippage, liquidity, R:R, trend alignment, confidence, ML)
5. Trade Dataset Builder (30+ features per signal)
6. Confidence Scoring (composite weighted score)

### Phase 2: ML Signal Filter
7. LightGBM classifier (WIN/LOSS) — 20 features, auto-retrain every 5 trades
8. ML Intelligence page (model metrics, feature importance, dataset stats, manual train/seed)
9. Gate 12: ML probability threshold

### Phase 3: Professional-Grade Risk Management
10. **Drawdown Circuit Breaker**: Auto-pauses bot at configurable drawdown threshold. Manual reset to resume.
11. **Session-Aware Trading**: Configurable trading windows (Asia/London/NYC/Overlap). Blocks trades outside sessions.
12. **Advanced Market Regime Detection**: Classifies each symbol into TRENDING_UP/DOWN, RANGING, VOLATILE, CALM using trend slope, ADX proxy, ATR%, volume expansion, BB bandwidth.
13. **Monte Carlo Risk Simulation**: 1000 randomized simulations producing probability of ruin, max drawdowns, balance distribution percentiles, profit probability.
14. **Risk Management Page**: Full dashboard with circuit breaker status + drawdown bar, trading sessions with active indicator, regime grid for all symbols, Monte Carlo simulation with distribution charts.

### Production Readiness
- `/api/health`, graceful indexes, `load_dotenv(override=False)`, 30s polling, defensive startup

## Key API Endpoints
- Auth: `POST /api/auth/register|login`, `GET /api/auth/me`
- Health: `GET /api/health`
- Dashboard: `GET /api/dashboard`
- Bot: `GET /api/bot/status|mode|filters`, `POST /api/bot/start|stop|pause|resume`, `PUT /api/bot/config|mode|telegram`
- Positions: `GET /api/positions`, `POST /api/positions/{id}/close`
- Trades: `GET /api/trades`
- Analytics: `GET /api/performance|leaderboard`
- Backtester: `POST /api/backtest|compare`
- ML: `GET /api/ml/status`, `POST /api/ml/train|seed`
- Dataset: `GET /api/dataset/stats`
- Risk: `GET /api/risk/circuit-breaker|regime|sessions`, `POST /api/risk/monte-carlo|circuit-breaker/reset`

## Pages (9 total)
Dashboard, Trade History, Leaderboard, Backtester, Compare, ML Intelligence, Risk Management, Configuration

## Bot IP: `35.184.53.215`
## Test Credentials: user@example.com / password

## Backlog
- P1: Order flow analysis (Binance order book depth)
- P1: Funding rate arbitrage, Whale wallet tracking
- P2: Fear & Greed index, News sentiment filter
- P2: WebSocket real-time updates, Multi-exchange support
- P3: Refactor server.py into modular files
