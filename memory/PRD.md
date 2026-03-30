# AgoBot — ML-Powered Autonomous Crypto Trading Bot

## Original Problem Statement
Port a Node.js crypto trading bot ("AgoBot") to Python/React with institutional-grade upgrades:
- Machine Learning (LightGBM) to learn from past trades
- 11-gate smart entry filtering (R:R, trend, volume, liquidity)
- Professional Risk Management (Circuit breakers, Monte Carlo, Market Regime Detection, Sessions)
- Market Intelligence (Order book flow, Funding rate arbitrage, Whale tracking)
- Production deployment on Render with MongoDB Atlas

## Live Production URLs
- **Frontend**: https://agobot-frontend.onrender.com
- **Backend**: https://agobot-backend.onrender.com
- **Health**: https://agobot-backend.onrender.com/api/health

## Architecture
```
/app/
├── backend/
│   ├── routes/              # auth, bot, ml, risk, market-intel, misc, trading
│   ├── services/            # bot_loop, binance_service (15s timeout), ml_service
│   │                          risk_service, signal_service, backtest_service
│   ├── models.py
│   ├── database.py          # Motor AsyncIOMotorClient
│   ├── config.py
│   ├── state.py
│   ├── server.py            # FastAPI entry point (fully graceful startup)
│   ├── Dockerfile           # python:3.11-slim, uvicorn
│   ├── requirements.prod.txt
│   └── .env
└── frontend/
    ├── src/pages/
    │   ├── DashboardPage.js
    │   ├── ConfigPage.js
    │   ├── MLPage.js
    │   ├── RiskPage.js
    │   ├── MarketIntelPage.js
    │   ├── TradeHistoryPage.js
    │   ├── LeaderboardPage.js
    │   ├── BacktesterPage.js
    │   └── StrategyComparisonPage.js
    ├── .npmrc               # legacy-peer-deps=true
    ├── .nvmrc               # 18
    ├── package.json         # engines: node >=18
    └── .env                 # REACT_APP_BACKEND_URL
```

## Render Deployment Configuration
- **Frontend service** (srv-d74ps3qdbo4c7391oqf0):
  - Build: `npm install && npm run build` (Node 20.18.0 via NODE_VERSION env var)
  - Env vars: REACT_APP_BACKEND_URL, NODE_VERSION=20.18.0, CI=false, DISABLE_ESLINT_PLUGIN=true
- **Backend service** (srv-d74ps0lm5p6s73fbntt0):
  - Runtime: Docker (Dockerfile in backend/)
  - Health check path: /api/health
  - Env vars: MONGO_URL, DB_NAME, BINANCE_API_KEY, BINANCE_API_SECRET, JWT_SECRET, PYTHON_VERSION

## Key Technical Stack
- **Backend**: FastAPI, MongoDB Atlas (Motor async), asyncio background loops
- **ML**: LightGBM binary classifier (WIN/LOSS prediction), scikit-learn, pandas
- **Trading**: Binance API (python-binance), DRY/LIVE mode toggle
- **Risk**: Monte Carlo simulation, Circuit breakers, Market Regime Detection
- **Frontend**: React 19, TailwindCSS, Recharts

## DB Schema
- `users`: {id, email, hashed_password, created_at}
- `positions`: {id, symbol, side, entry_price, status, market_regime, session, ml_win_prob}
- `signal_dataset`: {symbol, side, confidence, filters_passed, trade_taken, outcome, <features>}
- `bot_config`: {user_id, mode, symbols, filters, ml_settings}
- `trades`: closed trade history

## Key API Endpoints
- `GET /api/health` — healthcheck (database status)
- `POST /api/auth/register` / `POST /api/auth/login` — JWT auth
- `GET/POST /api/bot/status` / `POST /api/bot/mode` — bot control
- `GET /api/ml/status` — LightGBM model metrics
- `POST /api/risk/monte-carlo` — Monte Carlo simulation
- `GET /api/market-intel/order-flow` — Order book analysis
- `GET /api/risk/circuit-breaker` — Drawdown status

## What's Been Implemented
- [2026-02] Initial port from Node.js to Python/React
- [2026-02] DRY/LIVE mode toggle + SHORT selling toggle
- [2026-02] Phase 1: 11-Gate Smart Filters + Signal Dataset Logger
- [2026-02] Phase 2: LightGBM ML integration + MLPage dashboard
- [2026-02] Phase 3: Professional Risk Management + RiskPage dashboard
- [2026-02] Phase 4: Market Intelligence (order flow, funding rate, whale tracking)
- [2026-03] Backend refactored from 3,500-line monolith → modular routes/services
- [2026-03] Production deployment on Render (frontend + backend LIVE)
- [2026-03] Binance client 15s timeout fix (prevents startup hang)
- [2026-03] Graceful startup error handling (all steps wrapped in try/except)
- [2026-03] MongoDB Atlas connected
- [2026-03] Login fix: graceful hashed_password/password_hash fallback
- [2026-03] Binance API key management UI in Config page (PUT /api/bot/binance-keys)
- [2026-03] Bot LIVE trade fallback: failed live orders now fall back to DRY recording
- [2026-03] Code review fixes: hardcoded test credentials → env vars, console.error removed (6 files), array index keys → stable keys (MarketIntelPage, LeaderboardPage, BacktesterPage, ComparePage), server_legacy.py deleted, TradesPage PAGE_LIMIT extracted as module constant, BacktesterPage unused catch var fixed

## Render Deployment Lessons Learned
1. packageManager field in package.json blocks npm on Render → removed
2. NODE_VERSION must be a real nvm version (20.18.0, not 20.20.1 which is Emergent-specific)
3. .npmrc with legacy-peer-deps=true needed for React 19 + react-scripts 5
4. Health check path must be set to /api/health (not default /)
5. BinanceAsyncClient.create() must have asyncio.wait_for timeout (15s) to prevent startup hang
6. MongoDB Atlas IP whitelist must include 0.0.0.0/0 for Render dynamic IPs

## P0/P1/P2 Remaining Backlog
### P1 — Next Up
- WebSocket real-time updates (replace setInterval polling)
- Telegram/Email trade notifications (alerts on position open/close)

### P2 — Future
- Multi-exchange support (Bybit as primary alternative to Binance)
- Strategy marketplace (share/compare strategies with community)
- Mobile-responsive dashboard optimization

### P3 — Backlog
- React hydration warning fix (TradeRow component)
- Automated backtesting scheduler
- Multi-user leaderboard (cross-account)
