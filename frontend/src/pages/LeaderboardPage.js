import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { AppLayout } from "@/components/AppLayout";
import {
  Trophy,
  Medal,
  TrendingUp,
  TrendingDown,
  Flame,
  Clock,
  Target,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Zap,
  Shield,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
} from "recharts";

const MEDAL_COLORS = ["#FFD700", "#C0C0C0", "#CD7F32"];
const MEDAL_LABELS = ["Gold", "Silver", "Bronze"];

const RankBadge = ({ rank }) => {
  if (rank <= 3) {
    return (
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
        style={{
          background: `${MEDAL_COLORS[rank - 1]}20`,
          color: MEDAL_COLORS[rank - 1],
          border: `1px solid ${MEDAL_COLORS[rank - 1]}40`,
        }}
        data-testid={`rank-badge-${rank}`}
      >
        {rank}
      </div>
    );
  }
  return (
    <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-mono font-medium text-zinc-500 bg-zinc-800/50">
      {rank}
    </div>
  );
};

const StatCard = ({ label, value, subvalue, icon: Icon, color, testId }) => (
  <div
    data-testid={testId}
    className="p-5 bg-[#121212] border border-white/5 rounded-lg animate-fade-in"
  >
    <div className="flex items-center gap-2 mb-3">
      <div
        className="w-7 h-7 rounded-sm flex items-center justify-center"
        style={{ backgroundColor: `${color}15` }}
      >
        <Icon className="w-3.5 h-3.5" style={{ color }} />
      </div>
      <span className="overline">{label}</span>
    </div>
    <div className="font-mono text-xl font-bold tracking-tight">{value}</div>
    {subvalue && <div className="mt-1 text-[11px] text-zinc-500">{subvalue}</div>}
  </div>
);

const CustomBarTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="bg-[#0A0A0A] border border-[#333] rounded px-3 py-2 text-xs">
      <div className="font-bold text-white mb-1">
        {d?.symbol?.replace("USDT", "/USDT") || d?.reason || `${d?.hour}:00`}
      </div>
      <div className="font-mono">
        PnL:{" "}
        <span className={d?.pnl >= 0 ? "text-[#00F090]" : "text-[#FF2E5B]"}>
          ${d?.pnl?.toFixed(2)}
        </span>
      </div>
      {d?.trades && (
        <div className="text-zinc-500">{d.trades} trades</div>
      )}
      {d?.win_rate !== undefined && (
        <div className="text-zinc-500">Win: {d.win_rate}%</div>
      )}
    </div>
  );
};

const CustomPieTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="bg-[#0A0A0A] border border-[#333] rounded px-3 py-2 text-xs">
      <div className="font-bold text-white mb-1">{d?.reason}</div>
      <div className="text-zinc-400">{d?.count} trades ({d?.win_rate}% win)</div>
      <div className="font-mono">
        PnL:{" "}
        <span className={d?.pnl >= 0 ? "text-[#00F090]" : "text-[#FF2E5B]"}>
          ${d?.pnl?.toFixed(2)}
        </span>
      </div>
    </div>
  );
};

const EXIT_COLORS = {
  TAKE_PROFIT: "#00F090",
  STOP_LOSS: "#FF2E5B",
  TRAIL_STOP: "#8B5CF6",
  MANUAL: "#3B82F6",
  UNKNOWN: "#71717A",
};

export default function LeaderboardPage({ user, onLogout }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const res = await api.get("/leaderboard");
      setData(res.data);
    } catch (err) {
      console.error("Failed to fetch leaderboard:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <AppLayout user={user} onLogout={onLogout}>
        <div className="flex items-center justify-center min-h-screen">
          <RefreshCw className="w-6 h-6 text-blue-500 animate-spin" />
        </div>
      </AppLayout>
    );
  }

  const d = data || {};
  const rankings = d.symbol_rankings || [];
  const bestTrades = d.best_trades || [];
  const worstTrades = d.worst_trades || [];
  const streaks = d.streaks || {};
  const timeAnalysis = d.time_analysis || {};
  const exitAnalysis = d.exit_analysis || [];
  const weeklyPnl = d.weekly_pnl || [];
  const hasData = rankings.length > 0;

  return (
    <AppLayout user={user} onLogout={onLogout}>
      <div className="p-5 lg:p-8 space-y-6" data-testid="leaderboard-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              Performance Leaderboard
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              Symbol rankings, streaks, and trading analytics
            </p>
          </div>
          <button
            data-testid="refresh-leaderboard"
            onClick={() => {
              setLoading(true);
              fetchData();
            }}
            className="h-8 px-3 rounded-sm border border-white/10 text-zinc-400 text-xs font-medium hover:bg-white/5 transition-colors flex items-center gap-1.5"
          >
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>

        {!hasData ? (
          <div className="p-16 bg-[#121212] border border-white/5 rounded-lg text-center">
            <Trophy className="w-12 h-12 text-zinc-700 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-zinc-400 mb-2">
              No trade data yet
            </h3>
            <p className="text-sm text-zinc-600 max-w-md mx-auto">
              The leaderboard will populate as the bot executes trades. Keep the
              bot running to see symbol rankings, win streaks, and performance
              analytics.
            </p>
          </div>
        ) : (
          <>
            {/* Overview Stats */}
            <div
              className="grid grid-cols-2 lg:grid-cols-5 gap-4 stagger-children"
              data-testid="leaderboard-stats"
            >
              <StatCard
                testId="stat-consistency"
                label="Consistency"
                value={`${d.consistency_score || 0}%`}
                subvalue="Profitable weeks"
                icon={Shield}
                color="#00F090"
              />
              <StatCard
                testId="stat-risk-reward"
                label="Avg R:R"
                value={`${d.risk_reward_avg || 0}x`}
                subvalue="Risk to reward ratio"
                icon={Target}
                color="#3B82F6"
              />
              <StatCard
                testId="stat-win-streak"
                label="Best Win Streak"
                value={streaks.best_win || 0}
                subvalue={`Current: ${streaks.current || 0} ${streaks.current_type || ""}`}
                icon={Flame}
                color="#F59E0B"
              />
              <StatCard
                testId="stat-loss-streak"
                label="Worst Loss Streak"
                value={streaks.worst_loss || 0}
                subvalue="Consecutive losses"
                icon={TrendingDown}
                color="#FF2E5B"
              />
              <StatCard
                testId="stat-best-hour"
                label="Best Hour (UTC)"
                value={
                  timeAnalysis.best_hour
                    ? `${timeAnalysis.best_hour.hour}:00`
                    : "N/A"
                }
                subvalue={
                  timeAnalysis.best_hour
                    ? `$${timeAnalysis.best_hour.pnl?.toFixed(2)} PnL`
                    : ""
                }
                icon={Clock}
                color="#8B5CF6"
              />
            </div>

            {/* Symbol Rankings Table */}
            <div
              className="bg-[#121212] border border-white/5 rounded-lg overflow-hidden"
              data-testid="symbol-rankings"
            >
              <div className="px-5 py-4 border-b border-white/5 flex items-center gap-2">
                <Trophy className="w-4 h-4 text-[#FFD700]" />
                <h3 className="text-sm font-semibold">
                  Symbol Performance Rankings
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-white/5">
                      {[
                        "Rank",
                        "Symbol",
                        "Total PnL",
                        "Trades",
                        "Win Rate",
                        "Avg PnL",
                        "Best Trade",
                        "Worst Trade",
                        "Avg Hold",
                      ].map((h) => (
                        <th
                          key={h}
                          className="py-3 px-4 text-left text-[10px] font-semibold text-zinc-500 uppercase tracking-wider"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rankings.map((r) => (
                      <tr
                        key={r.symbol}
                        data-testid={`ranking-${r.symbol}`}
                        className={`border-b border-white/5 hover:bg-white/[0.02] transition-colors ${
                          r.rank === 1 ? "bg-[#FFD700]/[0.03]" : ""
                        }`}
                      >
                        <td className="py-3 px-4">
                          <RankBadge rank={r.rank} />
                        </td>
                        <td className="py-3 px-4">
                          <span className="text-sm font-bold">{r.symbol}</span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1">
                            {r.pnl >= 0 ? (
                              <ArrowUpRight className="w-3 h-3 text-[#00F090]" />
                            ) : (
                              <ArrowDownRight className="w-3 h-3 text-[#FF2E5B]" />
                            )}
                            <span
                              className={`font-mono text-sm font-bold ${
                                r.pnl >= 0
                                  ? "text-[#00F090]"
                                  : "text-[#FF2E5B]"
                              }`}
                            >
                              {r.pnl >= 0 ? "+" : ""}${r.pnl.toFixed(2)}
                            </span>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-zinc-400">
                          {r.trades}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden max-w-[60px]">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${r.win_rate}%`,
                                  backgroundColor:
                                    r.win_rate >= 50 ? "#00F090" : "#FF2E5B",
                                }}
                              />
                            </div>
                            <span className="font-mono text-xs text-zinc-300">
                              {r.win_rate}%
                            </span>
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`font-mono text-xs ${
                              r.avg_pnl >= 0
                                ? "text-[#00F090]"
                                : "text-[#FF2E5B]"
                            }`}
                          >
                            ${r.avg_pnl.toFixed(2)}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-[#00F090]">
                          +${r.best_trade.toFixed(2)}
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-[#FF2E5B]">
                          ${r.worst_trade.toFixed(2)}
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-zinc-500">
                          {r.avg_hold_time_min.toFixed(0)}m
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Charts Row */}
            <div className="grid grid-cols-12 gap-4">
              {/* Symbol PnL Bar Chart */}
              <div
                className="col-span-12 lg:col-span-7 bg-[#121212] border border-white/5 rounded-lg p-5"
                data-testid="symbol-pnl-chart"
              >
                <div className="flex items-center gap-2 mb-4">
                  <BarChart3 className="w-4 h-4 text-blue-400" />
                  <h3 className="text-sm font-semibold">PnL by Symbol</h3>
                </div>
                <div className="h-[240px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={rankings}>
                      <CartesianGrid
                        stroke="#333"
                        strokeDasharray="3 3"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="symbol"
                        stroke="#666"
                        fontSize={10}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => v.replace("USDT", "")}
                      />
                      <YAxis
                        stroke="#666"
                        fontSize={10}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => `$${v}`}
                      />
                      <Tooltip content={<CustomBarTooltip />} />
                      <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                        {rankings.map((entry, idx) => (
                          <Cell
                            key={`cell-${idx}`}
                            fill={entry.pnl >= 0 ? "#00F090" : "#FF2E5B"}
                            fillOpacity={0.8}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Exit Strategy Breakdown */}
              <div
                className="col-span-12 lg:col-span-5 bg-[#121212] border border-white/5 rounded-lg p-5"
                data-testid="exit-analysis"
              >
                <div className="flex items-center gap-2 mb-4">
                  <Target className="w-4 h-4 text-purple-400" />
                  <h3 className="text-sm font-semibold">
                    Exit Strategy Breakdown
                  </h3>
                </div>
                {exitAnalysis.length > 0 ? (
                  <div className="flex items-center gap-6">
                    <div className="h-[200px] w-[200px] flex-shrink-0">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={exitAnalysis}
                            dataKey="count"
                            nameKey="reason"
                            cx="50%"
                            cy="50%"
                            innerRadius={50}
                            outerRadius={80}
                            strokeWidth={0}
                          >
                            {exitAnalysis.map((entry, idx) => (
                              <Cell
                                key={`pie-${idx}`}
                                fill={
                                  EXIT_COLORS[entry.reason] || EXIT_COLORS.UNKNOWN
                                }
                                fillOpacity={0.85}
                              />
                            ))}
                          </Pie>
                          <Tooltip content={<CustomPieTooltip />} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="flex-1 space-y-3">
                      {exitAnalysis.map((e) => (
                        <div key={e.reason} className="flex items-center gap-3">
                          <div
                            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                            style={{
                              backgroundColor:
                                EXIT_COLORS[e.reason] || EXIT_COLORS.UNKNOWN,
                            }}
                          />
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-medium text-zinc-300">
                              {e.reason.replace("_", " ")}
                            </div>
                            <div className="text-[10px] text-zinc-600">
                              {e.count} trades &middot; {e.win_rate}% win
                            </div>
                          </div>
                          <span
                            className={`font-mono text-xs font-medium ${
                              e.pnl >= 0
                                ? "text-[#00F090]"
                                : "text-[#FF2E5B]"
                            }`}
                          >
                            ${e.pnl.toFixed(2)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="h-[200px] flex items-center justify-center text-zinc-600 text-sm">
                    No exit data yet
                  </div>
                )}
              </div>
            </div>

            {/* Best & Worst Trades */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Best Trades */}
              <div
                className="bg-[#121212] border border-white/5 rounded-lg overflow-hidden"
                data-testid="best-trades"
              >
                <div className="px-5 py-4 border-b border-white/5 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-[#00F090]" />
                  <h3 className="text-sm font-semibold">Top 5 Best Trades</h3>
                </div>
                <div className="divide-y divide-white/5">
                  {bestTrades.map((t, i) => (
                    <div
                      key={i}
                      data-testid={`best-trade-${i}`}
                      className="px-5 py-3 flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono font-bold text-[#FFD700] w-5">
                          #{i + 1}
                        </span>
                        <div>
                          <div className="text-xs font-bold">{t.symbol}</div>
                          <div className="text-[10px] text-zinc-600">
                            {t.exit_reason} &middot;{" "}
                            {t.closed_at
                              ? new Date(t.closed_at).toLocaleDateString()
                              : ""}
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-mono text-sm font-bold text-[#00F090]">
                          +${t.pnl.toFixed(2)}
                        </div>
                        <div className="font-mono text-[10px] text-[#00F090]/70">
                          +{t.pnl_percent.toFixed(2)}%
                        </div>
                      </div>
                    </div>
                  ))}
                  {bestTrades.length === 0 && (
                    <div className="p-6 text-center text-xs text-zinc-600">
                      No trades yet
                    </div>
                  )}
                </div>
              </div>

              {/* Worst Trades */}
              <div
                className="bg-[#121212] border border-white/5 rounded-lg overflow-hidden"
                data-testid="worst-trades"
              >
                <div className="px-5 py-4 border-b border-white/5 flex items-center gap-2">
                  <TrendingDown className="w-4 h-4 text-[#FF2E5B]" />
                  <h3 className="text-sm font-semibold">
                    Top 5 Worst Trades
                  </h3>
                </div>
                <div className="divide-y divide-white/5">
                  {worstTrades.map((t, i) => (
                    <div
                      key={i}
                      data-testid={`worst-trade-${i}`}
                      className="px-5 py-3 flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono font-bold text-[#FF2E5B] w-5">
                          #{i + 1}
                        </span>
                        <div>
                          <div className="text-xs font-bold">{t.symbol}</div>
                          <div className="text-[10px] text-zinc-600">
                            {t.exit_reason} &middot;{" "}
                            {t.closed_at
                              ? new Date(t.closed_at).toLocaleDateString()
                              : ""}
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-mono text-sm font-bold text-[#FF2E5B]">
                          ${t.pnl.toFixed(2)}
                        </div>
                        <div className="font-mono text-[10px] text-[#FF2E5B]/70">
                          {t.pnl_percent.toFixed(2)}%
                        </div>
                      </div>
                    </div>
                  ))}
                  {worstTrades.length === 0 && (
                    <div className="p-6 text-center text-xs text-zinc-600">
                      No trades yet
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Weekly PnL */}
            {weeklyPnl.length > 0 && (
              <div
                className="bg-[#121212] border border-white/5 rounded-lg p-5"
                data-testid="weekly-pnl-chart"
              >
                <div className="flex items-center gap-2 mb-4">
                  <Zap className="w-4 h-4 text-[#F59E0B]" />
                  <h3 className="text-sm font-semibold">Weekly PnL</h3>
                </div>
                <div className="h-[200px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={weeklyPnl}>
                      <CartesianGrid
                        stroke="#333"
                        strokeDasharray="3 3"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="week"
                        stroke="#666"
                        fontSize={10}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis
                        stroke="#666"
                        fontSize={10}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => `$${v}`}
                      />
                      <Tooltip content={<CustomBarTooltip />} />
                      <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                        {weeklyPnl.map((entry, idx) => (
                          <Cell
                            key={`week-${idx}`}
                            fill={entry.pnl >= 0 ? "#00F090" : "#FF2E5B"}
                            fillOpacity={0.8}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Hourly Performance */}
            {timeAnalysis.hourly_pnl?.length > 0 && (
              <div
                className="bg-[#121212] border border-white/5 rounded-lg p-5"
                data-testid="hourly-pnl-chart"
              >
                <div className="flex items-center gap-2 mb-4">
                  <Clock className="w-4 h-4 text-blue-400" />
                  <h3 className="text-sm font-semibold">
                    Performance by Hour (UTC)
                  </h3>
                </div>
                <div className="h-[200px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={timeAnalysis.hourly_pnl}>
                      <CartesianGrid
                        stroke="#333"
                        strokeDasharray="3 3"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="hour"
                        stroke="#666"
                        fontSize={10}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => `${v}:00`}
                      />
                      <YAxis
                        stroke="#666"
                        fontSize={10}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => `$${v}`}
                      />
                      <Tooltip content={<CustomBarTooltip />} />
                      <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                        {timeAnalysis.hourly_pnl.map((entry, idx) => (
                          <Cell
                            key={`hour-${idx}`}
                            fill={entry.pnl >= 0 ? "#3B82F6" : "#FF2E5B"}
                            fillOpacity={0.8}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}
