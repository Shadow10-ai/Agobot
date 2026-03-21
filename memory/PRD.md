# AgoBot - Crypto Trading Dashboard PRD

## Original Problem Statement
Build a crypto trading bot with autonomous execution. Enhanced with ML-powered smart filters for professional-grade signal quality. The bot learns from past trade outcomes and improves over time.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + shadcn/ui + Recharts + lucide-react
- **Backend**: FastAPI (Python) with async trading bot engine + python-binance + LightGBM ML
- **Database**: MongoDB (motor async driver)
- **Auth**: JWT-based authentication
- **Trading**: DRY/LIVE mode with Binance API integration + 12-gate smart filter system + ML model

## What's Been Implemented

### Core Features
1. Auth system (register, login, JWT)
2. Real-time dashboard (balance, PnL, positions, price ticker)
3. Trading bot engine (DRY/LIVE mode, RSI/MACD/BB/ATR/EMA signals, SL/TP/trailing)
4. Trade history (paginated, CSV export)
5. Performance leaderboard
6. Strategy backtester (slippage/fee modeling)
7. Strategy comparison (A/B testing)
8. DRY/LIVE mode toggle with confirmation dialog
9. LONG/SHORT configurable toggle
10. Binance API integration (python-binance AsyncClient)

### Phase 1: Smart Filters & Dataset Builder (Mar 2026)
11. 12-Gate Signal Filter Chain (Gates 1-11 + ML Gate 12)
12. Trade Dataset Builder (30+ features per signal)
13. Confidence Scoring (composite weighted score)
14. Config Page Smart Filters section

### Phase 2: ML Signal Filter (Mar 2026)
15. **LightGBM Binary Classifier**: Predicts WIN/LOSS probability for each signal
16. **20 Input Features**: RSI, MACD, EMA slope, ATR%, volume ratio, volatility percentile, candle structure, price change, confidence, R:R, side, regime, trend, volume_passes
17. **Auto-Retrain**: Model retrains every 5 closed trades (reinforcement feedback)
18. **Dataset Seeding**: Auto-seeds from historical trades on startup
19. **ML Intelligence Page**: Full dashboard showing model status, metrics (accuracy, precision, recall, F1, CV score), feature importance, training dataset stats, rejection reasons, manual Seed/Train controls
20. **Gate 12**: ML model gates signals with configurable win probability threshold (default 0.55)
21. **Model Persistence**: Saved to disk via joblib, loaded on restart

### Production Readiness
- `/api/health` endpoint for Kubernetes probes
- Graceful index creation, efficient cleanup
- Reduced frontend polling (30s)
- Defensive bot auto-start
- `load_dotenv(override=False)` for production

## Key API Endpoints
- Auth: `POST /api/auth/register|login`, `GET /api/auth/me`
- Health: `GET /api/health` (no auth)
- Dashboard: `GET /api/dashboard`
- Bot: `GET /api/bot/status`, `POST /api/bot/start|stop|pause|resume`
- Config: `GET/PUT /api/bot/config`, `PUT /api/bot/telegram`
- Mode: `GET/PUT /api/bot/mode`
- Filters: `GET /api/bot/filters`
- Positions: `GET /api/positions`, `POST /api/positions/{id}/close`
- Trades: `GET /api/trades`
- Analytics: `GET /api/performance|leaderboard`
- Backtester: `POST /api/backtest|compare`
- Dataset: `GET /api/dataset/stats`
- **ML: `GET /api/ml/status`, `POST /api/ml/train`, `POST /api/ml/seed`**

## Bot IP for Binance Trusted IP
`35.184.53.215`

## Test Credentials
- Email: user@example.com, Password: password

## Prioritized Backlog
### Phase 3: Professional Features (P0)
- Market Regime Detection (HMM-based)
- Order flow analysis (Binance order book depth)
- Session-aware trading (London/NYC overlap)
- Drawdown circuit breaker
- Monte Carlo risk analysis

### Future (P1)
- Funding rate arbitrage awareness
- Whale wallet tracking
- Fear & Greed index integration
- News sentiment filter
- WebSocket real-time updates
- Multi-exchange support
- Refactor server.py into modular files
