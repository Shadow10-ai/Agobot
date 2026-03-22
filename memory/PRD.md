# AgoBot - ML-Powered Autonomous Crypto Trading Bot

## Original Problem Statement
Port an autonomous crypto trading bot ("AgoBot") from Node.js to Python/React. User reported poor initial trade results and requested institutional-grade upgrades including:
- Machine Learning (LightGBM) to learn from past trades
- 11-gate smart filtering (R:R, trend, volume, liquidity, correlation, cooldown, confidence)
- Professional Risk Management (Circuit breakers, Monte Carlo simulations, Market Regime Detection, Trading Sessions)
- Market Intelligence (Order book flow, Funding rate arbitrage, Whale tracking)

## User Personas
- Crypto trader managing personal funds on Binance
- Needs both DRY (simulated) and LIVE (real) mode
- Wants data-driven decisions with ML filtering

## Core Requirements
1. Autonomous bot scanning selected symbols every 10s
2. 11-gate entry filter before opening any position
3. LightGBM ML model trained on historical signals
4. Risk management with circuit breaker and Monte Carlo simulation
5. Market intelligence dashboard (order flow, funding rates, whale activity)
6. DRY/LIVE mode toggle with Binance API integration
7. SHORT selling support (configurable toggle)

## Architecture

### Backend (FastAPI + MongoDB + Motor async)
```
/app/backend/
├── server.py              (109 lines - entry point, router includes, startup/shutdown)
├── database.py            (MongoDB Motor client)
├── config.py              (constants: VALID_SYMBOLS, TRADING_SESSIONS, ML config, JWT)
├── state.py               (mutable global state: bot_state, ml_model_state, _circuit_breaker, etc.)
├── auth.py                (JWT helpers: create_token, get_current_user)
├── models.py              (Pydantic request/response models)
├── services/
│   ├── indicators.py      (pure math: ema, sma, rsi_calc, macd_calc, atr_calc, bollinger_bands)
│   ├── binance_service.py (Binance async client, generate_candles for DRY mode)
│   ├── filters.py         (11-gate filters + confidence scoring)
│   ├── ml_service.py      (LightGBM training, ml_predict, dataset logging)
│   ├── risk_service.py    (circuit breaker, session check, regime detection, monte carlo)
│   ├── market_intel.py    (order flow, funding rates, whale activity)
│   ├── signal_service.py  (calculate_signal: indicators → entry signal)
│   ├── bot_loop.py        (main trading loop: scan → filter → open/close positions)
│   └── backtest_service.py (historical candle gen + strategy simulation)
└── routes/
    ├── auth_routes.py      (/auth/register, /auth/login, /auth/me)
    ├── bot_routes.py       (/bot/status, /bot/start, /bot/stop, /bot/config, /bot/mode)
    ├── trading_routes.py   (/dashboard, /positions, /trades, /performance, /leaderboard)
    ├── backtest_routes.py  (/backtest, /backtest/compare)
    ├── ml_routes.py        (/ml/status, /ml/train, /ml/dataset)
    ├── risk_routes.py      (/risk/circuit-breaker, /risk/sessions, /risk/regime, /risk/monte-carlo)
    ├── market_intel_routes.py (/orderflow, /orderflow/{symbol}, /funding-rates, /whale-activity)
    └── misc_routes.py      (/prices, /prices/history/{symbol}, /dataset/stats, /health, /backtests)
```

### Frontend (React + TailwindCSS + Recharts)
```
/app/frontend/src/
├── App.js                 (routing, auth context, axios interceptor)
├── components/AppLayout.js (sidebar navigation)
└── pages/
    ├── LoginPage.js       (register/login)
    ├── DashboardPage.js   (live positions, recent trades, price feed)
    ├── ConfigPage.js      (bot settings: symbols, risk params, ML thresholds, SHORT toggle)
    ├── MLPage.js          (ML model status, feature importance, dataset explorer)
    ├── RiskPage.js        (circuit breaker, sessions, regime detection, monte carlo)
    ├── MarketIntelPage.js (order flow, funding rates, whale activity)
    ├── TradeHistoryPage.js
    ├── LeaderboardPage.js
    ├── BacktesterPage.js
    └── StrategyComparisonPage.js
```

## What's Been Implemented

### Phase 1: Foundation (Jan 2026)
- FastAPI + MongoDB backend with JWT auth
- Binance API integration with DRY/LIVE mode toggle
- RSI/MACD/EMA/ATR/Bollinger Bands indicators
- Trailing stop-loss with activation threshold
- React frontend with TailwindCSS

### Phase 2: Smart Filters (Jan 2026)
- 11-gate entry filter: probability, volume, spread, slippage, liquidity, R:R, trend alignment, confidence, overtrade limits, cooldown, correlation
- Signal dataset logger for ML training
- Confidence scoring (5-factor composite)
- SHORT selling toggle (configurable)

### Phase 3: ML Intelligence (Jan 2026)
- LightGBM binary classifier (WIN/LOSS prediction)
- Auto-retrains every 5 new labeled trades
- MLPage.js dashboard with model metrics and feature importance
- Seed ML dataset from historical trades on startup

### Phase 4: Professional Risk Management (Jan 2026)
- Circuit breaker (auto-pause on drawdown threshold)
- Trading session filter (ASIA/LONDON/NYC)
- Advanced market regime detection (TRENDING/VOLATILE/CALM/RANGING)
- Monte Carlo simulation (1000 iterations on historical PnL distribution)
- RiskPage.js dashboard

### Phase 5: Market Intelligence (Feb 2026)
- Order flow analysis (bid/ask imbalance, walls, depth levels)
- Funding rate arbitrage awareness (sentiment signals)
- Whale activity tracking (large trade detection)
- MarketIntelPage.js dashboard

### Phase 6: Backend Refactor (Mar 2026)
- **server.py: 3,518 → 109 lines** (97% reduction)
- Created 8 route files + 9 service files + 4 foundation modules
- All 40+ API endpoints verified working after refactor
- Fixed 3 API field name regressions in risk_routes.py post-refactor

## Key API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/auth/login | POST | JWT login |
| /api/dashboard | GET | Full dashboard data |
| /api/bot/status | GET | Bot running state |
| /api/bot/mode | PUT | Toggle DRY/LIVE |
| /api/ml/status | GET | Model accuracy + feature importance |
| /api/risk/circuit-breaker | GET | Drawdown status |
| /api/risk/regime | GET | Market regime per symbol |
| /api/risk/monte-carlo | POST | Run simulation |
| /api/orderflow | GET | Order book analysis |
| /api/funding-rates | GET | Funding rate sentiment |
| /api/whale-activity | GET | Large trade tracking |
| /api/backtest | POST | Run strategy backtest |

## DB Schema
- `users`: {id, email, hashed_password, name, created_at}
- `positions`: {id, symbol, side, entry_price, stop_loss, take_profit, status, mode, ml_win_probability, market_regime, session, confidence_score, filters_passed}
- `trades`: {id, symbol, side, pnl, pnl_percent, exit_reason, opened_at, closed_at, mode}
- `signal_dataset`: {id, symbol, side, rsi, macd_*, ema_*, atr_*, volume_ratio, confidence_score, filters_passed, trade_taken, outcome, pnl}
- `bot_config`: {active, symbols, base_usdt_per_trade, min_entry_probability, allow_short, mode, ml_min_win_probability, ...}
- `bot_state`: {key, value} (account_balance, daily_pnl)
- `price_history`: {timestamp, prices: {symbol: price}}

## Known Constraints
- **Binance IP restriction**: Emergent preview IPs are blocked by Binance. Falls back to simulated data automatically. Works fine in user's actual environment.
- Minor React hydration warning (`<tr>` in DashboardPage.js) — cosmetic only
