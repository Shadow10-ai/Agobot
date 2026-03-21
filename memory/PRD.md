# AgoBot - Crypto Trading Dashboard PRD

## Original Problem Statement
Build a trading app focused on crypto trading with autonomous execution. Ported from Node.js to Python/FastAPI. Now enhanced with ML-ready smart filters for professional-grade signal quality.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + shadcn/ui + Recharts
- **Backend**: FastAPI (Python) with async trading bot engine + python-binance
- **Database**: MongoDB (motor async driver)
- **Auth**: JWT-based authentication
- **Trading**: DRY/LIVE mode with Binance API integration + 11-gate smart filter system

## What's Been Implemented

### Core Features
1. Auth system (register, login, JWT)
2. Real-time dashboard (balance, PnL, positions, price ticker)
3. Trading bot engine (DRY/LIVE mode, RSI/MACD/BB/ATR/EMA signals, SL/TP/trailing)
4. Trade history (paginated, CSV export)
5. Performance leaderboard
6. Strategy backtester (historical replay, slippage/fee modeling)
7. Strategy comparison (A/B testing)
8. DRY/LIVE mode toggle with confirmation dialog
9. LONG/SHORT configurable toggle
10. Binance API integration (python-binance AsyncClient)

### Phase 1: Smart Filters & Dataset Builder (Mar 2026)
11. **11-Gate Signal Filter Chain:**
    - Gate 1: Overtrade limits (max trades/hour, max trades/day)
    - Gate 2: Post-loss cooldown (configurable scan wait)
    - Gate 3: Correlation exposure check
    - Gate 4: Technical probability threshold
    - Gate 5: Volume filter
    - Gate 6: Spread check (bid-ask spread limit)
    - Gate 7: Slippage protection (estimated slippage limit)
    - Gate 8: Minimum liquidity (24h volume)
    - Gate 9: Risk/Reward ratio enforcement (min 2.5:1)
    - Gate 10: Multi-timeframe trend alignment
    - Gate 11: Composite confidence score threshold

12. **Trade Dataset Builder:**
    - Logs every signal (taken + rejected) with 30+ features
    - Features: RSI, MACD, EMA slope, ATR, BB, volume ratio, volatility regime, candle structure, trend, spread, confidence breakdown
    - Records outcome (WIN/LOSS) after trade closes
    - Ready for ML model training in Phase 2

13. **Confidence Scoring:**
    - Composite score: technical (30%) + trend alignment (25%) + volume (15%) + regime (15%) + R:R (15%)
    - Positions store confidence score + breakdown

14. **Config Page Updates:**
    - Smart Filters section with 9 configurable parameters
    - Trend Alignment toggle
    - All filter values persist to config

### Production Readiness
- `/api/health` endpoint for Kubernetes probes
- Graceful index creation, efficient cleanup
- `load_dotenv(override=False)` for production env safety
- Reduced frontend polling (30s)
- Defensive bot auto-start

## Key API Endpoints
- Auth: `POST /api/auth/register|login`, `GET /api/auth/me`
- Health: `GET /api/health` (no auth)
- Dashboard: `GET /api/dashboard`
- Bot: `GET /api/bot/status`, `POST /api/bot/start|stop|pause|resume`
- Config: `GET/PUT /api/bot/config`, `PUT /api/bot/telegram`
- Mode: `GET/PUT /api/bot/mode`
- Positions: `GET /api/positions`, `POST /api/positions/{id}/close`
- Trades: `GET /api/trades`
- Analytics: `GET /api/performance|leaderboard`
- Backtester: `POST /api/backtest|compare`
- **Dataset: `GET /api/dataset/stats`**
- **Filters: `GET /api/bot/filters`**

## Bot IP Address for Binance
`35.184.53.215`

## Test Credentials
- Email: user@example.com, Password: password

## Prioritized Backlog
### Phase 2: ML Signal Filter (P0)
- Feature engineering from signal_dataset
- Train XGBoost/LightGBM classifier on trade outcomes
- ML model as gatekeeper (>70% ML confidence)
- Reinforcement feedback loop (retrain on closed trades)

### Phase 3: Professional Features (P1)
- Market Regime Detection (HMM-based)
- Order flow analysis (Binance order book depth)
- Session-aware trading (London/NYC overlap)
- Drawdown circuit breaker
- Monte Carlo risk analysis

### Future (P2)
- Funding rate arbitrage awareness
- Whale wallet tracking
- Fear & Greed index integration
- News sentiment filter
- WebSocket real-time updates
- Multi-exchange support
