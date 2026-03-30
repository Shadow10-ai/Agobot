"""Pydantic request/response models."""
from pydantic import BaseModel
from typing import List, Optional


class UserCreate(BaseModel):
    email: str
    password: str
    name: str = ""


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class BotConfigUpdate(BaseModel):
    symbols: Optional[List[str]] = None
    base_usdt_per_trade: Optional[float] = None
    risk_per_trade_percent: Optional[float] = None
    max_daily_loss_usdt: Optional[float] = None
    max_total_drawdown_percent: Optional[float] = None
    rsi_period: Optional[int] = None
    rsi_overbought: Optional[float] = None
    rsi_oversold: Optional[float] = None
    min_entry_probability: Optional[float] = None
    trailing_stop_activate_pips: Optional[float] = None
    trailing_stop_distance_pips: Optional[float] = None
    allow_short: Optional[bool] = None
    max_trades_per_hour: Optional[int] = None
    max_trades_per_day: Optional[int] = None
    min_risk_reward_ratio: Optional[float] = None
    cooldown_after_loss_scans: Optional[int] = None
    min_confidence_score: Optional[float] = None
    spread_max_percent: Optional[float] = None
    min_24h_volume_usdt: Optional[float] = None
    max_slippage_percent: Optional[float] = None
    require_trend_alignment: Optional[bool] = None
    ml_min_win_probability: Optional[float] = None


class TelegramConfig(BaseModel):
    telegram_token: str = ""
    telegram_chat_id: str = ""


class BinanceKeysUpdate(BaseModel):
    api_key: str
    api_secret: str


class ModeToggle(BaseModel):
    mode: str


class BacktestRequest(BaseModel):
    symbol: str = "BTCUSDT"
    period_days: int = 30
    base_usdt_per_trade: float = 50.0
    risk_per_trade_percent: float = 0.5
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    min_entry_probability: float = 0.45
    trailing_stop_activate_pips: float = 2.4
    trailing_stop_distance_pips: float = 1.2
    atr_sl_multiplier: float = 1.2
    atr_tp_multiplier: float = 2.4
    initial_balance: float = 10000.0
    slippage_pct: float = 0.05
    fee_pct: float = 0.1
    volume_filter_multiplier: float = 1.5
    volatility_regime_enabled: bool = True
    volatility_reduce_factor: float = 0.5
    label: str = ""


class StrategyCompareRequest(BaseModel):
    symbol: str = "BTCUSDT"
    period_days: int = 30
    strategy_a: BacktestRequest
    strategy_b: BacktestRequest
