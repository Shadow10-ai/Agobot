import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { AppLayout } from "@/components/AppLayout";
import {
  FlaskConical,
  Play,
  RotateCcw,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Target,
  Shield,
  Flame,
  Clock,
  DollarSign,
  ChevronDown,
  ChevronUp,
  Activity,
  Zap,
} from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
  ComposedChart,
  Line,
} from "recharts";
import { toast } from "sonner";

const SYMBOLS = [
  "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
  "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT",
];

const DEFAULT_PARAMS = {
  symbol: "BTCUSDT",
  period_days: 30,
  base_usdt_per_trade: 50,
  risk_per_trade_percent: 0.5,
  rsi_period: 14,
  rsi_overbought: 70,
  rsi_oversold: 30,
  min_entry_probability: 0.45,
  trailing_stop_activate_pips: 2.4,
  trailing_stop_distance_pips: 1.2,
  atr_sl_multiplier: 1.2,
  atr_tp_multiplier: 2.4,
  initial_balance: 10000,
};

const ParamInput = ({ label, name, value, onChange, step, min, max, description }) => (
  <div>
    <label className="overline block mb-1.5">{label}</label>
    <input
      data-testid={`bt-param-${name}`}
      type="number"
      value={value}
      onChange={(e) => onChange(name, parseFloat(e.target.value) || 0)}
      step={step}
      min={min}
      max={max}
      className="w-full h-8 px-2.5 rounded-sm bg-[#0A0A0A] border border-[#27272A] text-xs font-mono text-white focus:outline-none focus:border-blue-500 transition-colors"
    />
    {description && <p className="text-[9px] text-zinc-600 mt-1">{description}</p>}
  </div>
);

const MetricCard = ({ label, value, subvalue, icon: Icon, color, highlight }) => (
  <div className={`p-4 bg-[#121212] border rounded-lg animate-fade-in ${highlight ? "border-blue-500/30 glow-blue" : "border-white/5"}`}>
    <div className="flex items-center gap-2 mb-2">
      <div className="w-6 h-6 rounded-sm flex items-center justify-center" style={{ backgroundColor: `${color}15` }}>
        <Icon className="w-3 h-3" style={{ color }} />
      </div>
      <span className="text-[9px] font-semibold uppercase tracking-wider text-zinc-500">{label}</span>
    </div>
    <div className="font-mono text-lg font-bold tracking-tight">{value}</div>
    {subvalue && <div className="mt-0.5 text-[10px] text-zinc-500">{subvalue}</div>}
  </div>
);

const EquityTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="bg-[#0A0A0A] border border-[#333] rounded px-3 py-2 text-xs">
      <div className="text-zinc-500 mb-1">{d?.time ? new Date(d.time).toLocaleDateString() : ""}</div>
      <div className="font-mono font-bold text-white">${d?.equity?.toLocaleString()}</div>
      {d?.drawdown > 0 && (
        <div className="text-[#FF2E5B] font-mono text-[10px]">DD: -{d.drawdown}%</div>
      )}
    </div>
  );
};

const MonthlyTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="bg-[#0A0A0A] border border-[#333] rounded px-3 py-2 text-xs">
      <div className="font-bold text-white mb-1">{d?.month}</div>
      <div className="font-mono">
        PnL: <span className={d?.pnl >= 0 ? "text-[#00F090]" : "text-[#FF2E5B]"}>${d?.pnl?.toFixed(2)}</span>
      </div>
      <div className="text-zinc-500">{d?.trades} trades &middot; {d?.wins}W</div>
    </div>
  );
};

const EXIT_COLORS = {
  TAKE_PROFIT: "#00F090",
  STOP_LOSS: "#FF2E5B",
  TRAIL_STOP: "#8B5CF6",
  END_OF_DATA: "#F59E0B",
  MANUAL: "#3B82F6",
};

export default function BacktesterPage({ user, onLogout }) {
  const [params, setParams] = useState({ ...DEFAULT_PARAMS });
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [history, setHistory] = useState([]);
  const [showTrades, setShowTrades] = useState(false);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await api.get("/backtests");
      setHistory(res.data || []);
    } catch (err) {
      // Ignore
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleChange = (name, value) => {
    setParams((p) => ({ ...p, [name]: value }));
  };

  const runBacktest = async () => {
    setRunning(true);
    setResult(null);
    try {
      const res = await api.post("/backtest", params);
      setResult(res.data);
      toast.success(`Backtest complete: ${res.data.summary.total_trades} trades executed`);
      fetchHistory();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Backtest failed");
    } finally {
      setRunning(false);
    }
  };

  const resetParams = () => {
    setParams({ ...DEFAULT_PARAMS });
    toast.info("Parameters reset to defaults");
  };

  const loadPreviousResult = async (bt) => {
    setParams(bt.params);
    toast.info(`Loaded params from ${bt.symbol} backtest`);
  };

  const s = result?.summary || {};
  const equityCurve = result?.equity_curve || [];
  const monthlyPnl = result?.monthly_pnl || [];
  const exitBreakdown = result?.exit_breakdown || [];
  const trades = result?.trades || [];

  return (
    <AppLayout user={user} onLogout={onLogout}>
      <div className="p-5 lg:p-8 space-y-6" data-testid="backtester-page">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Strategy Backtester</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Replay historical data against your signal logic to validate parameters
          </p>
        </div>

        <div className="grid grid-cols-12 gap-6">
          {/* Left: Config Panel */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            {/* Core Settings */}
            <div className="bg-[#121212] border border-white/5 rounded-lg p-5 space-y-4" data-testid="bt-config-panel">
              <div className="flex items-center gap-2">
                <FlaskConical className="w-4 h-4 text-blue-400" />
                <h3 className="text-sm font-semibold">Backtest Settings</h3>
              </div>

              <div>
                <label className="overline block mb-1.5">Symbol</label>
                <select
                  data-testid="bt-symbol-select"
                  value={params.symbol}
                  onChange={(e) => handleChange("symbol", e.target.value)}
                  className="w-full h-8 px-2.5 rounded-sm bg-[#0A0A0A] border border-[#27272A] text-xs font-mono text-white appearance-none focus:outline-none focus:border-blue-500 transition-colors"
                >
                  {SYMBOLS.map((s) => (
                    <option key={s} value={s}>{s.replace("USDT", "/USDT")}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <ParamInput label="Period (days)" name="period_days" value={params.period_days} onChange={handleChange} step={1} min={7} max={365} />
                <ParamInput label="Initial Balance" name="initial_balance" value={params.initial_balance} onChange={handleChange} step={1000} min={100} />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <ParamInput label="USDT/Trade" name="base_usdt_per_trade" value={params.base_usdt_per_trade} onChange={handleChange} step={10} min={10} />
                <ParamInput label="Risk %" name="risk_per_trade_percent" value={params.risk_per_trade_percent} onChange={handleChange} step={0.1} min={0.1} max={5} />
              </div>

              <ParamInput label="Min Entry Probability" name="min_entry_probability" value={params.min_entry_probability} onChange={handleChange} step={0.05} min={0.1} max={1} description="Lower = more trades, higher = more selective" />

              {/* Advanced toggle */}
              <button
                data-testid="bt-toggle-advanced"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors w-full"
              >
                {showAdvanced ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                {showAdvanced ? "Hide" : "Show"} Advanced Parameters
              </button>

              {showAdvanced && (
                <div className="space-y-3 pt-2 border-t border-white/5">
                  <div className="grid grid-cols-2 gap-3">
                    <ParamInput label="RSI Period" name="rsi_period" value={params.rsi_period} onChange={handleChange} step={1} min={5} max={30} />
                    <ParamInput label="RSI Overbought" name="rsi_overbought" value={params.rsi_overbought} onChange={handleChange} step={1} min={60} max={90} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <ParamInput label="SL (ATR x)" name="atr_sl_multiplier" value={params.atr_sl_multiplier} onChange={handleChange} step={0.1} min={0.5} max={5} />
                    <ParamInput label="TP (ATR x)" name="atr_tp_multiplier" value={params.atr_tp_multiplier} onChange={handleChange} step={0.1} min={0.5} max={10} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <ParamInput label="Trail Activate" name="trailing_stop_activate_pips" value={params.trailing_stop_activate_pips} onChange={handleChange} step={0.1} min={0.5} />
                    <ParamInput label="Trail Distance" name="trailing_stop_distance_pips" value={params.trailing_stop_distance_pips} onChange={handleChange} step={0.1} min={0.1} />
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2 pt-2">
                <button
                  data-testid="bt-run-button"
                  onClick={runBacktest}
                  disabled={running}
                  className="flex-1 h-9 rounded-sm bg-blue-500 text-white text-xs font-medium hover:bg-blue-600 disabled:opacity-50 shadow-[0_0_15px_rgba(59,130,246,0.3)] transition-colors flex items-center justify-center gap-1.5"
                >
                  {running ? (
                    <>
                      <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Running...
                    </>
                  ) : (
                    <>
                      <Play className="w-3 h-3" /> Run Backtest
                    </>
                  )}
                </button>
                <button
                  data-testid="bt-reset-button"
                  onClick={resetParams}
                  className="h-9 px-3 rounded-sm border border-white/10 text-zinc-400 text-xs font-medium hover:bg-white/5 transition-colors"
                >
                  <RotateCcw className="w-3 h-3" />
                </button>
              </div>
            </div>

            {/* Previous Backtests */}
            {history.length > 0 && (
              <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="bt-history">
                <h3 className="text-xs font-semibold text-zinc-400 mb-3">Previous Backtests</h3>
                <div className="space-y-2 max-h-[250px] overflow-y-auto">
                  {history.map((bt) => (
                    <button
                      key={bt.id}
                      data-testid={`bt-history-${bt.id}`}
                      onClick={() => loadPreviousResult(bt)}
                      className="w-full text-left px-3 py-2.5 rounded-sm bg-[#0A0A0A] border border-[#27272A] hover:border-blue-500/30 transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold">{bt.symbol}</span>
                        <span className={`font-mono text-xs font-medium ${bt.summary.total_pnl >= 0 ? "text-[#00F090]" : "text-[#FF2E5B]"}`}>
                          {bt.summary.total_pnl >= 0 ? "+" : ""}${bt.summary.total_pnl.toFixed(2)}
                        </span>
                      </div>
                      <div className="text-[10px] text-zinc-600 mt-0.5">
                        {bt.params.period_days}d &middot; {bt.summary.total_trades} trades &middot; {bt.summary.win_rate}% WR
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right: Results */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            {!result && !running && (
              <div className="bg-[#121212] border border-white/5 rounded-lg p-16 text-center" data-testid="bt-empty-state">
                <FlaskConical className="w-12 h-12 text-zinc-700 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-zinc-400 mb-2">Configure & Run</h3>
                <p className="text-sm text-zinc-600 max-w-md mx-auto">
                  Set your strategy parameters on the left and hit "Run Backtest" to simulate
                  trades against historical price data. Optimize before going live.
                </p>
              </div>
            )}

            {running && (
              <div className="bg-[#121212] border border-white/5 rounded-lg p-16 text-center">
                <div className="w-10 h-10 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto mb-4" />
                <h3 className="text-sm font-semibold text-zinc-300 mb-1">Running Backtest</h3>
                <p className="text-xs text-zinc-600">Simulating {params.period_days} days of {params.symbol} data...</p>
              </div>
            )}

            {result && (
              <>
                {/* Price Range Banner */}
                <div className="flex items-center gap-4 px-4 py-3 bg-[#121212] border border-white/5 rounded-lg text-xs" data-testid="bt-price-banner">
                  <span className="text-zinc-500">{params.symbol}</span>
                  <span className="text-zinc-500">&middot;</span>
                  <span className="text-zinc-400">
                    {params.period_days} days &middot; {result.candle_count} candles
                  </span>
                  <span className="text-zinc-500">&middot;</span>
                  <span className="font-mono text-zinc-300">
                    ${result.price_range?.start} → ${result.price_range?.end}
                  </span>
                  <span className="text-zinc-500">&middot;</span>
                  <span className="font-mono text-zinc-500">
                    H: ${result.price_range?.high} L: ${result.price_range?.low}
                  </span>
                </div>

                {/* Summary Metrics */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 stagger-children" data-testid="bt-summary-metrics">
                  <MetricCard
                    label="Total PnL"
                    value={`${s.total_pnl >= 0 ? "+" : ""}$${s.total_pnl?.toFixed(2)}`}
                    subvalue={`${s.total_pnl_percent >= 0 ? "+" : ""}${s.total_pnl_percent}% return`}
                    icon={DollarSign}
                    color={s.total_pnl >= 0 ? "#00F090" : "#FF2E5B"}
                    highlight
                  />
                  <MetricCard
                    label="Win Rate"
                    value={`${s.win_rate}%`}
                    subvalue={`${s.wins}W / ${s.losses}L of ${s.total_trades}`}
                    icon={Target}
                    color="#3B82F6"
                  />
                  <MetricCard
                    label="Profit Factor"
                    value={s.profit_factor}
                    subvalue={`Sharpe: ${s.sharpe_ratio}`}
                    icon={BarChart3}
                    color="#8B5CF6"
                  />
                  <MetricCard
                    label="Max Drawdown"
                    value={`-${s.max_drawdown_pct}%`}
                    subvalue={`-$${s.max_drawdown?.toFixed(2)}`}
                    icon={TrendingDown}
                    color="#FF2E5B"
                  />
                </div>

                {/* Second row metrics */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 stagger-children">
                  <MetricCard
                    label="Final Balance"
                    value={`$${s.final_balance?.toLocaleString()}`}
                    subvalue={`From $${s.initial_balance?.toLocaleString()}`}
                    icon={DollarSign}
                    color="#F59E0B"
                  />
                  <MetricCard
                    label="Avg Win / Loss"
                    value={`$${s.avg_win?.toFixed(2)}`}
                    subvalue={`Avg Loss: $${s.avg_loss?.toFixed(2)}`}
                    icon={Activity}
                    color="#00F090"
                  />
                  <MetricCard
                    label="Expectancy"
                    value={`$${s.expectancy?.toFixed(2)}`}
                    subvalue="Per trade expected"
                    icon={Zap}
                    color="#3B82F6"
                  />
                  <MetricCard
                    label="Streaks"
                    value={`${s.best_win_streak}W / ${s.worst_loss_streak}L`}
                    subvalue={`Avg hold: ${s.avg_hold_candles} candles`}
                    icon={Flame}
                    color="#F59E0B"
                  />
                </div>

                {/* Equity Curve */}
                <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="bt-equity-chart">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-blue-400" />
                      <h3 className="text-sm font-semibold">Equity Curve</h3>
                    </div>
                    <div className="flex items-center gap-4 text-[10px] text-zinc-500">
                      <span className="flex items-center gap-1"><span className="w-2 h-0.5 bg-blue-400 rounded" /> Equity</span>
                      <span className="flex items-center gap-1"><span className="w-2 h-0.5 bg-[#FF2E5B] rounded" /> Drawdown</span>
                    </div>
                  </div>
                  <div className="h-[280px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={equityCurve}>
                        <defs>
                          <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.2} />
                            <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="#222" strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="time" stroke="#555" fontSize={9} tickLine={false} axisLine={false}
                          tickFormatter={(v) => v ? new Date(v).toLocaleDateString("en", { month: "short", day: "numeric" }) : ""} />
                        <YAxis yAxisId="left" stroke="#555" fontSize={9} tickLine={false} axisLine={false}
                          tickFormatter={(v) => `$${v.toLocaleString()}`} />
                        <YAxis yAxisId="right" orientation="right" stroke="#555" fontSize={9} tickLine={false} axisLine={false}
                          tickFormatter={(v) => `${v}%`} />
                        <Tooltip content={<EquityTooltip />} />
                        <ReferenceLine yAxisId="left" y={params.initial_balance} stroke="#666" strokeDasharray="5 5" />
                        <Area yAxisId="left" type="monotone" dataKey="equity" stroke="#3B82F6" strokeWidth={2} fill="url(#eqGrad)" />
                        <Line yAxisId="right" type="monotone" dataKey="drawdown" stroke="#FF2E5B" strokeWidth={1} dot={false} strokeOpacity={0.6} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Monthly PnL + Exit Breakdown */}
                <div className="grid grid-cols-12 gap-4">
                  {monthlyPnl.length > 0 && (
                    <div className="col-span-12 lg:col-span-7 bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="bt-monthly-chart">
                      <div className="flex items-center gap-2 mb-4">
                        <BarChart3 className="w-4 h-4 text-blue-400" />
                        <h3 className="text-sm font-semibold">Monthly PnL</h3>
                      </div>
                      <div className="h-[200px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={monthlyPnl}>
                            <CartesianGrid stroke="#333" strokeDasharray="3 3" vertical={false} />
                            <XAxis dataKey="month" stroke="#666" fontSize={9} tickLine={false} axisLine={false} />
                            <YAxis stroke="#666" fontSize={9} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} />
                            <Tooltip content={<MonthlyTooltip />} />
                            <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                              {monthlyPnl.map((e, i) => (
                                <Cell key={`m-${i}`} fill={e.pnl >= 0 ? "#00F090" : "#FF2E5B"} fillOpacity={0.8} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}

                  {exitBreakdown.length > 0 && (
                    <div className={`${monthlyPnl.length > 0 ? "col-span-12 lg:col-span-5" : "col-span-12"} bg-[#121212] border border-white/5 rounded-lg p-5`} data-testid="bt-exit-breakdown">
                      <div className="flex items-center gap-2 mb-4">
                        <Shield className="w-4 h-4 text-purple-400" />
                        <h3 className="text-sm font-semibold">Exit Strategy Performance</h3>
                      </div>
                      <div className="space-y-3">
                        {exitBreakdown.map((e) => {
                          const winRate = e.count > 0 ? Math.round(e.wins / e.count * 100) : 0;
                          return (
                            <div key={e.reason} className="flex items-center gap-3 p-3 rounded-sm bg-[#0A0A0A] border border-[#1A1A1A]">
                              <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: EXIT_COLORS[e.reason] || "#71717A" }} />
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between">
                                  <span className="text-xs font-medium text-zinc-300">{e.reason.replace(/_/g, " ")}</span>
                                  <span className={`font-mono text-xs font-bold ${e.pnl >= 0 ? "text-[#00F090]" : "text-[#FF2E5B]"}`}>
                                    {e.pnl >= 0 ? "+" : ""}${e.pnl.toFixed(2)}
                                  </span>
                                </div>
                                <div className="flex items-center gap-3 mt-1">
                                  <span className="text-[10px] text-zinc-600">{e.count} trades</span>
                                  <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden max-w-[80px]">
                                    <div className="h-full rounded-full" style={{ width: `${winRate}%`, backgroundColor: winRate >= 50 ? "#00F090" : "#FF2E5B" }} />
                                  </div>
                                  <span className="text-[10px] text-zinc-500 font-mono">{winRate}%</span>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>

                {/* Trade List */}
                <div className="bg-[#121212] border border-white/5 rounded-lg overflow-hidden" data-testid="bt-trades-table">
                  <button
                    data-testid="bt-toggle-trades"
                    onClick={() => setShowTrades(!showTrades)}
                    className="w-full px-5 py-4 border-b border-white/5 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-zinc-400" />
                      <h3 className="text-sm font-semibold">Individual Trades</h3>
                      <span className="text-[10px] text-zinc-600 font-mono">{trades.length} trades</span>
                    </div>
                    {showTrades ? <ChevronUp className="w-4 h-4 text-zinc-500" /> : <ChevronDown className="w-4 h-4 text-zinc-500" />}
                  </button>

                  {showTrades && (
                    <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                      <table className="w-full">
                        <thead className="sticky top-0 bg-[#121212]">
                          <tr className="border-b border-white/5">
                            {["#", "Entry", "Exit", "PnL", "PnL %", "Reason", "Hold"].map((h) => (
                              <th key={h} className="py-2.5 px-3 text-left text-[9px] font-semibold text-zinc-500 uppercase tracking-wider">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {trades.map((t, i) => (
                            <tr key={i} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                              <td className="py-2 px-3 text-[10px] text-zinc-600 font-mono">{i + 1}</td>
                              <td className="py-2 px-3 font-mono text-[10px]">${t.entry_price?.toFixed(2)}</td>
                              <td className="py-2 px-3 font-mono text-[10px]">${t.exit_price?.toFixed(2)}</td>
                              <td className="py-2 px-3">
                                <span className={`font-mono text-[10px] font-medium ${t.pnl > 0 ? "text-[#00F090]" : "text-[#FF2E5B]"}`}>
                                  {t.pnl > 0 ? "+" : ""}${t.pnl?.toFixed(2)}
                                </span>
                              </td>
                              <td className="py-2 px-3">
                                <span className={`font-mono text-[10px] ${t.pnl_percent > 0 ? "text-[#00F090]" : "text-[#FF2E5B]"}`}>
                                  {t.pnl_percent > 0 ? "+" : ""}{t.pnl_percent?.toFixed(2)}%
                                </span>
                              </td>
                              <td className="py-2 px-3">
                                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                                  style={{ backgroundColor: `${EXIT_COLORS[t.exit_reason] || "#71717A"}15`, color: EXIT_COLORS[t.exit_reason] || "#71717A" }}>
                                  {t.exit_reason}
                                </span>
                              </td>
                              <td className="py-2 px-3 font-mono text-[10px] text-zinc-500">{t.hold_candles}c</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
