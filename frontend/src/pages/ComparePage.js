import { useState } from "react";
import { api } from "@/App";
import { AppLayout } from "@/components/AppLayout";
import {
  GitCompareArrows,
  Play,
  Trophy,
  TrendingUp,
  TrendingDown,
  ChevronDown,
  ChevronUp,
  Check,
  X as XIcon,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from "recharts";
import { toast } from "sonner";

const SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT"];

const PRESETS = {
  conservative: {
    label: "Conservative",
    base_usdt_per_trade: 30, risk_per_trade_percent: 0.3,
    min_entry_probability: 0.6, rsi_overbought: 65, rsi_oversold: 35,
    atr_sl_multiplier: 1.5, atr_tp_multiplier: 3.0,
    trailing_stop_activate_pips: 3.0, trailing_stop_distance_pips: 1.5,
    volume_filter_multiplier: 2.0, volatility_regime_enabled: true, volatility_reduce_factor: 0.3,
    slippage_pct: 0.05, fee_pct: 0.1,
  },
  aggressive: {
    label: "Aggressive",
    base_usdt_per_trade: 80, risk_per_trade_percent: 1.0,
    min_entry_probability: 0.35, rsi_overbought: 75, rsi_oversold: 25,
    atr_sl_multiplier: 1.0, atr_tp_multiplier: 2.0,
    trailing_stop_activate_pips: 1.8, trailing_stop_distance_pips: 0.8,
    volume_filter_multiplier: 1.0, volatility_regime_enabled: false, volatility_reduce_factor: 1.0,
    slippage_pct: 0.05, fee_pct: 0.1,
  },
  balanced: {
    label: "Balanced",
    base_usdt_per_trade: 50, risk_per_trade_percent: 0.5,
    min_entry_probability: 0.45, rsi_overbought: 70, rsi_oversold: 30,
    atr_sl_multiplier: 1.2, atr_tp_multiplier: 2.4,
    trailing_stop_activate_pips: 2.4, trailing_stop_distance_pips: 1.2,
    volume_filter_multiplier: 1.5, volatility_regime_enabled: true, volatility_reduce_factor: 0.5,
    slippage_pct: 0.05, fee_pct: 0.1,
  },
};

const SmallInput = ({ label, name, value, onChange, step, min, max }) => (
  <div>
    <label className="text-[9px] text-zinc-500 uppercase tracking-wider block mb-1">{label}</label>
    <input type="number" value={value} onChange={(e) => onChange(name, parseFloat(e.target.value) || 0)}
      step={step} min={min} max={max}
      className="w-full h-7 px-2 rounded-sm bg-[#0A0A0A] border border-[#27272A] text-[11px] font-mono text-white focus:outline-none focus:border-blue-500 transition-colors" />
  </div>
);

const METRIC_LABELS = {
  total_pnl: "Total PnL", win_rate: "Win Rate", profit_factor: "Profit Factor",
  max_drawdown: "Max Drawdown", sharpe_ratio: "Sharpe Ratio", expectancy: "Expectancy",
};

const CompareTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#0A0A0A] border border-[#333] rounded px-3 py-2 text-xs">
      {payload.map((p) => (
        <div key={p.dataKey || p.name} className="font-mono" style={{ color: p.color }}>
          {p.name}: ${p.value?.toLocaleString()}
        </div>
      ))}
    </div>
  );
};

const StrategyPanel = ({ label, color, strategy, setStrategy, presets, side }) => {
  const [showAdvanced, setShowAdvanced] = useState(false);
  return (
    <div className="bg-[#121212] border border-white/5 rounded-lg p-4 space-y-3" data-testid={`compare-panel-${side}`}>
      <div className="flex items-center gap-2 mb-1">
        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
        <input type="text" value={strategy.label} onChange={(e) => setStrategy({ ...strategy, label: e.target.value })}
          className="text-sm font-semibold bg-transparent border-none outline-none text-white flex-1" data-testid={`compare-label-${side}`} />
      </div>
      <div className="flex gap-1.5 flex-wrap">
        {Object.entries(presets).map(([k, v]) => (
          <button key={k} onClick={() => setStrategy({ ...strategy, ...v })}
            data-testid={`preset-${side}-${k}`}
            className="text-[9px] px-2 py-1 rounded-sm border border-[#27272A] text-zinc-400 hover:border-blue-500/30 hover:text-zinc-200 transition-colors">
            {v.label}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <SmallInput label="USDT/Trade" name="base_usdt_per_trade" value={strategy.base_usdt_per_trade} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={10} min={10} />
        <SmallInput label="Risk %" name="risk_per_trade_percent" value={strategy.risk_per_trade_percent} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={0.1} min={0.1} max={5} />
        <SmallInput label="Min Probability" name="min_entry_probability" value={strategy.min_entry_probability} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={0.05} min={0.1} max={1} />
        <SmallInput label="Vol Filter (x)" name="volume_filter_multiplier" value={strategy.volume_filter_multiplier} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={0.1} min={0.5} max={5} />
      </div>
      <div className="flex items-center gap-2 text-[10px]">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input type="checkbox" checked={strategy.volatility_regime_enabled}
            onChange={(e) => setStrategy({ ...strategy, volatility_regime_enabled: e.target.checked })}
            className="w-3 h-3 rounded border-zinc-600" data-testid={`vol-regime-${side}`} />
          <span className="text-zinc-400">Vol Regime Filter</span>
        </label>
      </div>
      <button onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-1 text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors">
        {showAdvanced ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />} Advanced
      </button>
      {showAdvanced && (
        <div className="grid grid-cols-2 gap-2 pt-1 border-t border-white/5">
          <SmallInput label="SL (ATR x)" name="atr_sl_multiplier" value={strategy.atr_sl_multiplier} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={0.1} min={0.5} />
          <SmallInput label="TP (ATR x)" name="atr_tp_multiplier" value={strategy.atr_tp_multiplier} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={0.1} min={0.5} />
          <SmallInput label="Trail Activate" name="trailing_stop_activate_pips" value={strategy.trailing_stop_activate_pips} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={0.1} />
          <SmallInput label="Trail Distance" name="trailing_stop_distance_pips" value={strategy.trailing_stop_distance_pips} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={0.1} />
          <SmallInput label="Slippage %" name="slippage_pct" value={strategy.slippage_pct} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={0.01} min={0} />
          <SmallInput label="Fee %" name="fee_pct" value={strategy.fee_pct} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={0.01} min={0} />
          <SmallInput label="RSI OB" name="rsi_overbought" value={strategy.rsi_overbought} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={1} min={60} max={90} />
          <SmallInput label="Vol Reduce" name="volatility_reduce_factor" value={strategy.volatility_reduce_factor} onChange={(n, v) => setStrategy({ ...strategy, [n]: v })} step={0.1} min={0.1} max={1} />
        </div>
      )}
    </div>
  );
};

export default function ComparePage({ user, onLogout }) {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [periodDays, setPeriodDays] = useState(30);
  const [stratA, setStratA] = useState({ ...PRESETS.conservative, label: "Conservative", symbol: "BTCUSDT", period_days: 30, rsi_period: 14, initial_balance: 10000 });
  const [stratB, setStratB] = useState({ ...PRESETS.aggressive, label: "Aggressive", symbol: "BTCUSDT", period_days: 30, rsi_period: 14, initial_balance: 10000 });
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);

  const runCompare = async () => {
    setRunning(true);
    setResult(null);
    try {
      const res = await api.post("/backtest/compare", {
        symbol, period_days: periodDays,
        strategy_a: { ...stratA, symbol, period_days: periodDays },
        strategy_b: { ...stratB, symbol, period_days: periodDays },
      });
      setResult(res.data);
      toast.success(`Comparison complete: ${res.data.overall_winner === "TIE" ? "It's a tie!" : `${res.data.overall_winner === "A" ? res.data.strategy_a.label : res.data.strategy_b.label} wins!`}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Comparison failed");
    } finally {
      setRunning(false);
    }
  };

  // Merge equity curves for chart
  const mergedEquity = [];
  if (result) {
    const eqA = result.strategy_a.equity_curve || [];
    const eqB = result.strategy_b.equity_curve || [];
    const maxLen = Math.max(eqA.length, eqB.length);
    for (let i = 0; i < maxLen; i++) {
      mergedEquity.push({
        time: eqA[i]?.time || eqB[i]?.time || "",
        a: eqA[i]?.equity || null,
        b: eqB[i]?.equity || null,
      });
    }
  }

  const sa = result?.strategy_a?.summary || {};
  const sb = result?.strategy_b?.summary || {};

  return (
    <AppLayout user={user} onLogout={onLogout}>
      <div className="p-5 lg:p-8 space-y-6" data-testid="compare-page">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Strategy Comparison</h1>
          <p className="text-sm text-zinc-500 mt-1">Run two strategies on identical data to find the better approach</p>
        </div>

        {/* Global Controls */}
        <div className="flex items-center gap-3 flex-wrap">
          <div>
            <label className="overline block mb-1.5">Symbol</label>
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} data-testid="compare-symbol"
              className="h-8 px-2.5 rounded-sm bg-[#121212] border border-[#27272A] text-xs font-mono text-white appearance-none focus:outline-none focus:border-blue-500">
              {SYMBOLS.map((s) => <option key={s} value={s}>{s.replace("USDT", "/USDT")}</option>)}
            </select>
          </div>
          <div>
            <label className="overline block mb-1.5">Period (days)</label>
            <input type="number" value={periodDays} onChange={(e) => setPeriodDays(parseInt(e.target.value) || 30)}
              min={7} max={365} data-testid="compare-period"
              className="h-8 w-20 px-2.5 rounded-sm bg-[#121212] border border-[#27272A] text-xs font-mono text-white focus:outline-none focus:border-blue-500" />
          </div>
          <div className="flex items-end">
            <button onClick={runCompare} disabled={running} data-testid="compare-run-button"
              className="h-8 px-4 rounded-sm bg-blue-500 text-white text-xs font-medium hover:bg-blue-600 disabled:opacity-50 shadow-[0_0_15px_rgba(59,130,246,0.3)] transition-colors flex items-center gap-1.5">
              {running ? <><div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Running...</> : <><Play className="w-3 h-3" /> Compare</>}
            </button>
          </div>
        </div>

        {/* Strategy Panels */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <StrategyPanel label="A" color="#3B82F6" strategy={stratA} setStrategy={setStratA} presets={PRESETS} side="a" />
          <StrategyPanel label="B" color="#F59E0B" strategy={stratB} setStrategy={setStratB} presets={PRESETS} side="b" />
        </div>

        {/* Results */}
        {result && (
          <>
            {/* Winner Banner */}
            <div className={`p-4 rounded-lg border flex items-center justify-between ${
              result.overall_winner === "A" ? "bg-blue-500/5 border-blue-500/20" :
              result.overall_winner === "B" ? "bg-amber-500/5 border-amber-500/20" :
              "bg-zinc-500/5 border-zinc-500/20"
            }`} data-testid="compare-winner-banner">
              <div className="flex items-center gap-3">
                <Trophy className="w-5 h-5" style={{ color: result.overall_winner === "A" ? "#3B82F6" : result.overall_winner === "B" ? "#F59E0B" : "#71717A" }} />
                <div>
                  <div className="text-sm font-bold">
                    {result.overall_winner === "TIE" ? "It's a Tie!" :
                      `${result.overall_winner === "A" ? result.strategy_a.label : result.strategy_b.label} Wins`}
                  </div>
                  <div className="text-[11px] text-zinc-500">
                    {result.a_wins} vs {result.b_wins} metric wins &middot; {result.candle_count} candles &middot; {symbol}
                  </div>
                </div>
              </div>
              <div className="font-mono text-xs text-zinc-400">
                ${result.price_range?.start} → ${result.price_range?.end}
              </div>
            </div>

            {/* Metric Comparison Table */}
            <div className="bg-[#121212] border border-white/5 rounded-lg overflow-hidden" data-testid="compare-metrics-table">
              <div className="px-5 py-3 border-b border-white/5">
                <h3 className="text-sm font-semibold">Head-to-Head Metrics</h3>
              </div>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/5">
                    <th className="py-2.5 px-4 text-left text-[10px] font-semibold text-zinc-500 uppercase w-1/3">Metric</th>
                    <th className="py-2.5 px-4 text-center text-[10px] font-semibold uppercase w-1/3" style={{ color: "#3B82F6" }}>{result.strategy_a.label}</th>
                    <th className="py-2.5 px-4 text-center text-[10px] font-semibold uppercase w-1/3" style={{ color: "#F59E0B" }}>{result.strategy_b.label}</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { key: "total_pnl", fmt: (v) => `$${v?.toFixed(2)}`, better: "higher" },
                    { key: "win_rate", fmt: (v) => `${v}%`, better: "higher" },
                    { key: "profit_factor", fmt: (v) => v, better: "higher" },
                    { key: "max_drawdown", fmt: (v) => `${sa.max_drawdown_pct || 0}%`, fmtB: (v) => `${sb.max_drawdown_pct || 0}%`, better: "lower" },
                    { key: "sharpe_ratio", fmt: (v) => v, better: "higher" },
                    { key: "expectancy", fmt: (v) => `$${v?.toFixed(2)}`, better: "higher" },
                    { key: "total_trades", label: "Total Trades", fmt: (v) => v },
                    { key: "total_fees", label: "Total Fees", fmt: (v) => `$${v?.toFixed(2)}` },
                    { key: "total_slippage", label: "Total Slippage", fmt: (v) => `$${v?.toFixed(2)}` },
                    { key: "signals_rejected_volume", label: "Vol Filter Rejects", fmt: (v) => v },
                    { key: "signals_rejected_regime", label: "Regime Adjustments", fmt: (v) => v },
                  ].map(({ key, label, fmt, fmtB, better }) => {
                    const av = sa[key], bv = sb[key];
                    const winner = result.comparison?.[key];
                    return (
                      <tr key={key} className="border-b border-white/5 hover:bg-white/[0.02]">
                        <td className="py-2.5 px-4 text-xs text-zinc-400">{label || METRIC_LABELS[key] || key.replace(/_/g, " ")}</td>
                        <td className="py-2.5 px-4 text-center">
                          <span className={`font-mono text-xs font-medium ${winner === "A" ? "text-[#00F090]" : "text-zinc-300"}`}>
                            {fmt(av)} {winner === "A" && <Check className="w-3 h-3 inline ml-1 text-[#00F090]" />}
                          </span>
                        </td>
                        <td className="py-2.5 px-4 text-center">
                          <span className={`font-mono text-xs font-medium ${winner === "B" ? "text-[#00F090]" : "text-zinc-300"}`}>
                            {(fmtB || fmt)(bv)} {winner === "B" && <Check className="w-3 h-3 inline ml-1 text-[#00F090]" />}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Equity Curves Overlay */}
            <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="compare-equity-chart">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold">Equity Curves (Overlay)</h3>
                <div className="flex items-center gap-4 text-[10px]">
                  <span className="flex items-center gap-1"><span className="w-2 h-0.5 bg-blue-500 rounded" />{result.strategy_a.label}</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-0.5 bg-amber-500 rounded" />{result.strategy_b.label}</span>
                </div>
              </div>
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={mergedEquity}>
                    <defs>
                      <linearGradient id="gradA" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.15} />
                        <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="gradB" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#F59E0B" stopOpacity={0.15} />
                        <stop offset="95%" stopColor="#F59E0B" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#222" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="time" stroke="#555" fontSize={9} tickLine={false} axisLine={false}
                      tickFormatter={(v) => v ? new Date(v).toLocaleDateString("en", { month: "short", day: "numeric" }) : ""} />
                    <YAxis stroke="#555" fontSize={9} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v.toLocaleString()}`} />
                    <Tooltip content={<CompareTooltip />} />
                    <ReferenceLine y={10000} stroke="#555" strokeDasharray="5 5" />
                    <Area type="monotone" dataKey="a" name={result.strategy_a.label} stroke="#3B82F6" strokeWidth={2} fill="url(#gradA)" />
                    <Area type="monotone" dataKey="b" name={result.strategy_b.label} stroke="#F59E0B" strokeWidth={2} fill="url(#gradB)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Quick Summary Cards */}
            <div className="grid grid-cols-2 gap-4">
              {[
                { data: result.strategy_a, color: "#3B82F6" },
                { data: result.strategy_b, color: "#F59E0B" },
              ].map(({ data: d, color }) => (
                <div key={d.label} className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid={`compare-summary-${d.label}`}>
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                    <h3 className="text-sm font-semibold">{d.label}</h3>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { l: "PnL", v: `$${d.summary.total_pnl?.toFixed(2)}`, c: d.summary.total_pnl >= 0 },
                      { l: "Win Rate", v: `${d.summary.win_rate}%`, c: d.summary.win_rate >= 50 },
                      { l: "Trades", v: d.summary.total_trades },
                      { l: "Fees", v: `$${d.summary.total_fees?.toFixed(2)}` },
                      { l: "Slippage", v: `$${d.summary.total_slippage?.toFixed(2)}` },
                      { l: "Sharpe", v: d.summary.sharpe_ratio },
                    ].map(({ l, v, c }) => (
                      <div key={l}>
                        <div className="text-[9px] text-zinc-600 uppercase">{l}</div>
                        <div className={`font-mono text-xs font-medium ${c === true ? "text-[#00F090]" : c === false ? "text-[#FF2E5B]" : "text-zinc-300"}`}>{v}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {!result && !running && (
          <div className="bg-[#121212] border border-white/5 rounded-lg p-16 text-center" data-testid="compare-empty-state">
            <GitCompareArrows className="w-12 h-12 text-zinc-700 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-zinc-400 mb-2">Configure Two Strategies</h3>
            <p className="text-sm text-zinc-600 max-w-lg mx-auto">
              Use presets or customize parameters for each strategy. Both will run on identical price data for a fair head-to-head comparison. Includes realistic slippage, fees, volume filters, and volatility regime detection.
            </p>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
