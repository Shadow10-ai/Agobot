import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { AppLayout } from "@/components/AppLayout";
import { ShieldAlert, Activity, Clock, BarChart3, RefreshCw, Play, Pause, TrendingUp, TrendingDown } from "lucide-react";
import { toast } from "sonner";

const StatBox = ({ label, value, sub, color = "text-white" }) => (
  <div className="bg-[#0A0A0A] border border-white/5 rounded-lg p-4">
    <p className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</p>
    <p className={`text-xl font-bold font-mono mt-1 ${color}`}>{value}</p>
    {sub && <p className="text-[10px] text-zinc-600 mt-1">{sub}</p>}
  </div>
);

const regimeColors = {
  TRENDING_UP: "text-emerald-400",
  TRENDING_DOWN: "text-red-400",
  RANGING: "text-yellow-400",
  VOLATILE: "text-orange-400",
  CALM: "text-blue-400",
  UNKNOWN: "text-zinc-500",
};

const regimeBg = {
  TRENDING_UP: "bg-emerald-500/10 border-emerald-500/20",
  TRENDING_DOWN: "bg-red-500/10 border-red-500/20",
  RANGING: "bg-yellow-500/10 border-yellow-500/20",
  VOLATILE: "bg-orange-500/10 border-orange-500/20",
  CALM: "bg-blue-500/10 border-blue-500/20",
  UNKNOWN: "bg-zinc-800 border-zinc-700",
};

export default function RiskPage({ user, onLogout }) {
  const [circuitBreaker, setCircuitBreaker] = useState(null);
  const [regimes, setRegimes] = useState(null);
  const [sessions, setSessions] = useState(null);
  const [monteCarlo, setMonteCarlo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mcLoading, setMcLoading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [cbRes, regimeRes, sessRes] = await Promise.all([
        api.get("/risk/circuit-breaker"),
        api.get("/risk/regime"),
        api.get("/risk/sessions"),
      ]);
      setCircuitBreaker(cbRes.data);
      setRegimes(regimeRes.data);
      setSessions(sessRes.data);
    } catch {
      // silently swallow — UI shows stale data or empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const runMonteCarlo = async () => {
    setMcLoading(true);
    try {
      const res = await api.post("/risk/monte-carlo");
      setMonteCarlo(res.data);
      if (res.data.error) {
        toast.error(res.data.error);
      } else {
        toast.success("Monte Carlo simulation complete");
      }
    } catch (err) {
      toast.error("Simulation failed");
    } finally {
      setMcLoading(false);
    }
  };

  const resetBreaker = async () => {
    try {
      await api.post("/risk/circuit-breaker/reset");
      toast.success("Circuit breaker reset. Bot unpaused.");
      fetchData();
    } catch (err) {
      toast.error("Reset failed");
    }
  };

  if (loading) {
    return (
      <AppLayout user={user} onLogout={onLogout}>
        <div className="flex items-center justify-center min-h-screen">
          <div className="w-5 h-5 border-2 border-red-500 border-t-transparent rounded-full animate-spin" />
        </div>
      </AppLayout>
    );
  }

  const cb = circuitBreaker || {};
  const mc = monteCarlo;
  const sess = sessions || {};
  const regimeData = regimes?.regimes || {};

  return (
    <AppLayout user={user} onLogout={onLogout}>
      <div className="p-5 lg:p-8 space-y-6" data-testid="risk-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Risk Management</h1>
            <p className="text-sm text-zinc-500 mt-1">Circuit breaker, market regime, session awareness & Monte Carlo</p>
          </div>
          <button onClick={fetchData} className="h-8 px-3 rounded-sm border border-white/10 text-zinc-400 text-xs hover:bg-white/5 transition-colors">
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        {/* Circuit Breaker */}
        <div
          data-testid="circuit-breaker-section"
          className={`relative overflow-hidden rounded-lg border p-5 ${
            cb.tripped ? "bg-red-500/10 border-red-500/30" : "bg-emerald-500/5 border-emerald-500/20"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <ShieldAlert className={`w-5 h-5 ${cb.tripped ? "text-red-400" : "text-emerald-400"}`} />
              <div>
                <div className="text-sm font-semibold flex items-center gap-2">
                  Drawdown Circuit Breaker
                  <span
                    data-testid="breaker-badge"
                    className={`text-[10px] px-2 py-0.5 rounded-full font-bold tracking-wider ${
                      cb.tripped ? "bg-red-500/20 text-red-400 border border-red-500/30" : "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    }`}
                  >
                    {cb.tripped ? "TRIPPED" : "ARMED"}
                  </span>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {cb.tripped
                    ? `Tripped at ${cb.drawdown_at_trip}% drawdown. Bot is paused. Reset to resume.`
                    : `Auto-pauses bot if drawdown exceeds ${cb.max_drawdown_threshold}%.`}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className="text-[10px] text-zinc-500">Current Drawdown</p>
                <p className={`text-lg font-bold font-mono ${cb.current_drawdown > 3 ? "text-red-400" : "text-emerald-400"}`}>
                  {cb.current_drawdown}%
                </p>
              </div>
              <div className="text-right">
                <p className="text-[10px] text-zinc-500">Threshold</p>
                <p className="text-lg font-bold font-mono text-zinc-400">{cb.max_drawdown_threshold}%</p>
              </div>
              {cb.tripped && (
                <button
                  data-testid="reset-breaker"
                  onClick={resetBreaker}
                  className="h-8 px-3 rounded-sm bg-red-500 text-white text-xs font-medium hover:bg-red-600 transition-colors"
                >
                  Reset
                </button>
              )}
            </div>
          </div>
          {/* Drawdown bar */}
          <div className="mt-3">
            <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${cb.current_drawdown > 3 ? "bg-red-500" : "bg-emerald-500"}`}
                style={{ width: `${Math.min(100, (cb.current_drawdown / cb.max_drawdown_threshold) * 100)}%` }}
              />
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-[9px] text-zinc-600">0%</span>
              <span className="text-[9px] text-zinc-600">{cb.max_drawdown_threshold}% (auto-pause)</span>
            </div>
          </div>
        </div>

        {/* Trading Session */}
        <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="sessions-section">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Trading Sessions</h3>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${sess.in_session ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"}`}>
              {sess.in_session ? sess.active_session : "OUTSIDE"}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(sess.sessions || {}).map(([name, times]) => {
              const isActive = sess.active_session === name;
              const isAllowed = (sess.allowed || []).includes(name);
              return (
                <div
                  key={name}
                  className={`p-3 rounded-lg border ${
                    isActive ? "bg-cyan-500/10 border-cyan-500/30" : isAllowed ? "bg-zinc-800/50 border-white/5" : "bg-zinc-900/50 border-zinc-800 opacity-50"
                  }`}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    {isActive && <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />}
                    <span className="text-[10px] font-semibold tracking-wider">{name}</span>
                  </div>
                  <p className="text-[10px] text-zinc-500 font-mono">{times.start}:00 - {times.end}:00 UTC</p>
                </div>
              );
            })}
          </div>
          <p className="text-[10px] text-zinc-600 mt-2">Current UTC: {sess.current_utc ? new Date(sess.current_utc).toLocaleTimeString() : "..."}</p>
        </div>

        {/* Market Regimes */}
        <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="regime-section">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-4 h-4 text-purple-400" />
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Market Regime Detection</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(regimeData).map(([symbol, data]) => (
              <div key={symbol} className={`p-3 rounded-lg border ${regimeBg[data.regime] || regimeBg.UNKNOWN}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold">{symbol.replace("USDT", "")}</span>
                  {data.regime.includes("UP") ? (
                    <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                  ) : data.regime.includes("DOWN") ? (
                    <TrendingDown className="w-3.5 h-3.5 text-red-400" />
                  ) : null}
                </div>
                <p className={`text-[10px] font-bold ${regimeColors[data.regime] || "text-zinc-400"}`}>{data.regime}</p>
                <p className="text-[10px] text-zinc-600 font-mono mt-0.5">strength: {data.strength}</p>
                <p className="text-[10px] text-zinc-600 font-mono">ATR: {data.details?.atr_percent?.toFixed(2)}%</p>
              </div>
            ))}
          </div>
        </div>

        {/* Monte Carlo */}
        <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="monte-carlo-section">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-orange-400" />
              <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Monte Carlo Risk Simulation</h3>
            </div>
            <button
              data-testid="run-monte-carlo"
              onClick={runMonteCarlo}
              disabled={mcLoading}
              className="h-8 px-4 rounded-sm bg-orange-500 text-white text-xs font-medium hover:bg-orange-600 disabled:opacity-50 shadow-[0_0_15px_rgba(249,115,22,0.3)] transition-colors flex items-center gap-1.5"
            >
              <Play className="w-3 h-3" /> {mcLoading ? "Running 1000 sims..." : "Run Simulation"}
            </button>
          </div>

          {mc && !mc.error ? (
            <div className="space-y-5">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatBox label="Mean Final Balance" value={`$${mc.results.mean_final_balance.toLocaleString()}`} color={mc.results.mean_final_balance > mc.initial_balance ? "text-emerald-400" : "text-red-400"} />
                <StatBox label="Prob. Profitable" value={`${mc.risk.probability_profitable}%`} color={mc.risk.probability_profitable > 50 ? "text-emerald-400" : "text-red-400"} />
                <StatBox label="Prob. of Ruin" value={`${mc.risk.probability_of_ruin}%`} color={mc.risk.probability_of_ruin < 5 ? "text-emerald-400" : "text-red-400"} />
                <StatBox label="Avg Max Drawdown" value={`${mc.risk.avg_max_drawdown}%`} color="text-orange-400" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Results Range */}
                <div className="bg-[#0A0A0A] border border-white/5 rounded-lg p-4">
                  <h4 className="text-[10px] text-zinc-500 uppercase mb-3">Balance Distribution</h4>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between"><span className="text-zinc-500">Best Case</span><span className="text-emerald-400 font-mono">${mc.results.best_case.toLocaleString()}</span></div>
                    <div className="flex justify-between"><span className="text-zinc-500">95th Percentile</span><span className="text-emerald-400/70 font-mono">${mc.results.percentile_95.toLocaleString()}</span></div>
                    <div className="flex justify-between"><span className="text-zinc-500">75th Percentile</span><span className="text-blue-400 font-mono">${mc.results.percentile_75.toLocaleString()}</span></div>
                    <div className="flex justify-between"><span className="text-zinc-500">Median</span><span className="text-white font-mono">${mc.results.median_final_balance.toLocaleString()}</span></div>
                    <div className="flex justify-between"><span className="text-zinc-500">25th Percentile</span><span className="text-yellow-400 font-mono">${mc.results.percentile_25.toLocaleString()}</span></div>
                    <div className="flex justify-between"><span className="text-zinc-500">5th Percentile</span><span className="text-red-400/70 font-mono">${mc.results.percentile_5.toLocaleString()}</span></div>
                    <div className="flex justify-between"><span className="text-zinc-500">Worst Case</span><span className="text-red-400 font-mono">${mc.results.worst_case.toLocaleString()}</span></div>
                  </div>
                </div>

                {/* Distribution */}
                <div className="bg-[#0A0A0A] border border-white/5 rounded-lg p-4">
                  <h4 className="text-[10px] text-zinc-500 uppercase mb-3">Outcome Distribution</h4>
                  <div className="space-y-3">
                    {Object.entries(mc.distribution).map(([range, pct]) => (
                      <div key={range}>
                        <div className="flex justify-between mb-1">
                          <span className="text-[10px] text-zinc-400">${range.replace(/_/g, " - $").replace("below ", "<").replace("above ", ">")}</span>
                          <span className="text-[10px] font-mono text-zinc-300">{pct}%</span>
                        </div>
                        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${range.includes("above") || range.includes("10000_to") ? "bg-emerald-500" : "bg-red-500/60"}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-zinc-600 mt-3">{mc.simulations} simulations x {mc.trades_per_sim} trades each, using {mc.historical_trades_used} historical trades</p>
                </div>
              </div>
            </div>
          ) : mc?.error ? (
            <p className="text-xs text-red-400">{mc.error}</p>
          ) : (
            <p className="text-xs text-zinc-500">Click "Run Simulation" to analyze risk across 1,000 randomized trade sequences.</p>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
