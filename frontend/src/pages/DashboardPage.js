import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/App";
import { AppLayout } from "@/components/AppLayout";
import { useWS } from "@/context/WebSocketContext";
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Activity,
  BarChart3,
  Zap,
  Play,
  Pause,
  Square,
  RefreshCw,
  ArrowUpRight,
  ArrowDownRight,
  X as CloseIcon,
  Brain,
  AlertTriangle,
  CheckCircle,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { toast } from "sonner";

const KPICard = ({ label, value, subvalue, icon: Icon, color, testId }) => (
  <div
    data-testid={testId}
    className="p-5 bg-[#121212] border border-white/5 rounded-lg animate-fade-in"
  >
    <div className="flex items-center justify-between mb-3">
      <span className="overline">{label}</span>
      <div
        className="w-8 h-8 rounded-sm flex items-center justify-center"
        style={{ backgroundColor: `${color}15` }}
      >
        <Icon className="w-4 h-4" style={{ color }} />
      </div>
    </div>
    <div className="font-mono text-2xl font-bold tracking-tight">{value}</div>
    {subvalue && (
      <div className="mt-1 text-xs text-zinc-500">{subvalue}</div>
    )}
  </div>
);

const PositionCard = ({ position, onClose }) => {
  const pnl = position.unrealized_pnl || 0;
  const pnlPct = position.unrealized_pnl_percent || 0;
  const isPositive = pnl >= 0;

  return (
    <div
      data-testid={`position-${position.symbol}`}
      className="p-4 bg-[#121212] border border-white/5 rounded-lg animate-fade-in"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold">{position.symbol}</span>
          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${position.side === 'SHORT' ? 'bg-orange-500/10 text-orange-400' : 'bg-blue-500/10 text-blue-400'}`}>
            {position.side || 'LONG'}
          </span>
        </div>
        <button
          data-testid={`close-position-${position.symbol}`}
          onClick={() => onClose(position.id)}
          className="text-zinc-600 hover:text-red-400 transition-colors"
          title="Close position"
        >
          <CloseIcon className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <div className="text-zinc-600 mb-0.5">Entry</div>
          <div className="font-mono font-medium">
            ${position.entry_price?.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-zinc-600 mb-0.5">Current</div>
          <div className="font-mono font-medium">
            ${position.current_price?.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-zinc-600 mb-0.5">SL</div>
          <div className="font-mono text-[#FF2E5B]">
            ${position.stop_loss?.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-zinc-600 mb-0.5">TP</div>
          <div className="font-mono text-[#00F090]">
            ${position.take_profit?.toFixed(2)}
          </div>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between">
        <div className="flex items-center gap-1">
          {isPositive ? (
            <ArrowUpRight className="w-3.5 h-3.5 text-[#00F090]" />
          ) : (
            <ArrowDownRight className="w-3.5 h-3.5 text-[#FF2E5B]" />
          )}
          <span
            className={`font-mono text-sm font-bold ${isPositive ? "text-[#00F090]" : "text-[#FF2E5B]"}`}
          >
            {isPositive ? "+" : ""}
            {pnl.toFixed(2)}
          </span>
        </div>
        <span
          className={`font-mono text-xs ${isPositive ? "text-[#00F090]" : "text-[#FF2E5B]"}`}
        >
          {isPositive ? "+" : ""}
          {pnlPct.toFixed(2)}%
        </span>
      </div>

      {position.trail_activated && (
        <div className="mt-2 text-[10px] font-mono px-2 py-1 rounded bg-purple-500/10 text-purple-400 text-center">
          TRAILING ACTIVE
        </div>
      )}
    </div>
  );
};

const TradeRow = ({ trade }) => {
  const isWin = trade.pnl > 0;
  return (
    <tr
      data-testid={`trade-row-${trade.id}`}
      className="border-b border-white/5 hover:bg-white/[0.02] transition-colors"
    >
      <td className="py-2.5 px-3">
        <span className="text-xs font-bold">{trade.symbol}</span>
      </td>
      <td className="py-2.5 px-3">
        <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${trade.side === 'SHORT' ? 'bg-orange-500/10 text-orange-400' : 'bg-blue-500/10 text-blue-400'}`}>
          {trade.side || 'LONG'}
        </span>
      </td>
      <td className="py-2.5 px-3 font-mono text-xs">
        ${trade.entry_price?.toFixed(2)}
      </td>
      <td className="py-2.5 px-3 font-mono text-xs">
        ${trade.exit_price?.toFixed(2)}
      </td>
      <td className="py-2.5 px-3">
        <span
          className={`font-mono text-xs font-medium ${isWin ? "text-[#00F090]" : "text-[#FF2E5B]"}`}
        >
          {isWin ? "+" : ""}
          {trade.pnl?.toFixed(2)}
        </span>
      </td>
      <td className="py-2.5 px-3">
        <span
          className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
            trade.exit_reason === "TAKE_PROFIT"
              ? "bg-[#00F090]/10 text-[#00F090]"
              : trade.exit_reason === "STOP_LOSS"
                ? "bg-[#FF2E5B]/10 text-[#FF2E5B]"
                : "bg-zinc-500/10 text-zinc-400"
          }`}
        >
          {trade.exit_reason}
        </span>
      </td>
    </tr>
  );
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#0A0A0A] border border-[#333] rounded px-3 py-2 text-xs">
      <div className="text-zinc-500 mb-1">{label}</div>
      <div className="font-mono font-bold text-white">
        ${payload[0]?.value?.toFixed(2)}
      </div>
    </div>
  );
};

const MLHealthCard = ({ ml }) => {
  if (!ml) return null;
  const isActive = ml.status === "ACTIVE";
  const isLearning = ml.status === "LEARNING";
  const overfitWarn = ml.overfit_warning;
  const trainAcc = ml.accuracy != null ? (ml.accuracy * 100).toFixed(1) : null;
  const testAcc = ml.test_accuracy != null ? (ml.test_accuracy * 100).toFixed(1) : null;
  const samples = ml.training_data?.total_samples ?? ml.training_samples ?? 0;
  const needed = ml.min_samples_required ?? 30;
  const pct = Math.min(100, Math.round((samples / needed) * 100));

  return (
    <div
      data-testid="ml-health-card"
      className={`p-4 rounded-lg border flex items-start gap-3 ${
        overfitWarn
          ? "bg-amber-500/5 border-amber-500/20"
          : isActive
          ? "bg-purple-500/5 border-purple-500/20"
          : "bg-zinc-800/40 border-white/5"
      }`}
    >
      <div className={`mt-0.5 flex-shrink-0 ${overfitWarn ? "text-amber-400" : isActive ? "text-purple-400" : "text-zinc-500"}`}>
        {overfitWarn ? <AlertTriangle className="w-4 h-4" /> : isActive ? <CheckCircle className="w-4 h-4" /> : <Brain className="w-4 h-4" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-semibold text-zinc-200">ML Model</span>
          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full tracking-wider ${
            isActive ? "bg-purple-500/20 text-purple-400" :
            isLearning ? "bg-yellow-500/20 text-yellow-400" :
            "bg-zinc-500/20 text-zinc-400"
          }`}>{ml.status}</span>
          {overfitWarn && (
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400">OVERFIT</span>
          )}
        </div>

        {isActive ? (
          <div className="flex items-center gap-3 text-[10px] font-mono">
            <span className="text-zinc-500">Train <span className="text-purple-300">{trainAcc}%</span></span>
            {testAcc && <span className="text-zinc-500">Test <span className={overfitWarn ? "text-amber-400" : "text-emerald-400"}>{testAcc}%</span></span>}
            <span className="text-zinc-500">{samples} samples</span>
          </div>
        ) : (
          <div>
            <div className="text-[10px] text-zinc-500 mb-1.5">{samples}/{needed} labeled trades</div>
            <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
              <div className="h-full bg-yellow-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}

        {overfitWarn && (
          <p className="text-[10px] text-amber-400/80 mt-1">Model may be memorising — more trades needed to generalise.</p>
        )}
      </div>
      <a href="/ml" className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors flex-shrink-0 mt-0.5">Details →</a>
    </div>
  );
};

export default function DashboardPage({ user, onLogout }) {
  const [dashboard, setDashboard] = useState(null);
  const [performance, setPerformance] = useState(null);
  const [mlStatus, setMlStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [botLoading, setBotLoading] = useState(false);
  const intervalRef = useRef(null);
  const { lastMessage, connected } = useWS();

  const fetchData = useCallback(async () => {
    try {
      const [dashRes, perfRes, mlRes] = await Promise.all([
        api.get("/dashboard"),
        api.get("/performance"),
        api.get("/ml/status"),
      ]);
      setDashboard(dashRes.data);
      setPerformance(perfRes.data);
      setMlStatus(mlRes.data);
    } catch (err) {
      console.error('Dashboard fetch failed:', err?.message || err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + 30s refresh for full data (recent trades, performance chart)
  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(fetchData, 30000);
    return () => clearInterval(intervalRef.current);
  }, [fetchData]);

  // WebSocket: live-update positions, prices, bot status on every scan (~10s)
  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.type === "scan_update") {
      setDashboard((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          bot_status: lastMessage.bot,
          positions: lastMessage.positions ?? prev.positions,
          open_positions_count: (lastMessage.positions ?? prev.positions ?? []).length,
          prices: lastMessage.prices ?? prev.prices,
        };
      });
    }
    if (lastMessage.type === "ml_update") {
      setMlStatus((prev) => prev ? {
        ...prev,
        status: lastMessage.status ?? prev.status,
        accuracy: lastMessage.accuracy ?? prev.accuracy,
        training_data: { ...prev.training_data, total_samples: lastMessage.training_samples ?? prev.training_data?.total_samples },
        version: lastMessage.version ?? prev.version,
      } : prev);
    }
  }, [lastMessage]);

  const handleBotAction = async (action) => {
    setBotLoading(true);
    try {
      await api.post(`/bot/${action}`);
      toast.success(`Bot ${action}ed`);
      await fetchData();
    } catch (err) {
      toast.error(`Failed to ${action} bot`);
    } finally {
      setBotLoading(false);
    }
  };

  const handleClosePosition = async (positionId) => {
    try {
      await api.post(`/positions/${positionId}/close`);
      toast.success("Position closed");
      await fetchData();
    } catch (err) {
      toast.error("Failed to close position");
    }
  };

  if (loading) {
    return (
      <AppLayout user={user} onLogout={onLogout}>
        <div className="flex items-center justify-center min-h-screen">
          <RefreshCw className="w-6 h-6 text-blue-500 animate-spin" />
        </div>
      </AppLayout>
    );
  }

  const d = dashboard || {};
  const botStatus = d.bot_status || {};
  const positions = d.positions || [];
  const recentTrades = d.recent_trades || [];
  const pnlData = (performance?.cumulative_pnl || []).map((p, i) => ({
    name: `T${i + 1}`,
    pnl: p.pnl,
  }));

  return (
    <AppLayout user={user} onLogout={onLogout}>
      <div className="p-5 lg:p-8 space-y-6" data-testid="dashboard-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
            <p className="text-sm text-zinc-500 mt-1">
              {botStatus.mode} MODE
              {botStatus.last_scan && (
                <> &middot; Last scan: {new Date(botStatus.last_scan).toLocaleTimeString()}</>
              )}
              {connected && (
                <span className="ml-2 inline-flex items-center gap-1 text-[#00F090] text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#00F090] inline-block animate-pulse" />
                  LIVE
                </span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* Bot status indicator */}
            <div
              data-testid="bot-status-indicator"
              className={`flex items-center gap-2 px-3 py-1.5 rounded-sm text-xs font-medium ${
                botStatus.running && !botStatus.paused
                  ? "bg-[#00F090]/10 text-[#00F090]"
                  : botStatus.paused
                    ? "bg-yellow-500/10 text-yellow-400"
                    : "bg-zinc-500/10 text-zinc-400"
              }`}
            >
              <div
                className={`w-1.5 h-1.5 rounded-full pulse-dot ${
                  botStatus.running && !botStatus.paused
                    ? "bg-[#00F090]"
                    : botStatus.paused
                      ? "bg-yellow-400"
                      : "bg-zinc-500"
                }`}
              />
              {botStatus.running && !botStatus.paused
                ? "Running"
                : botStatus.paused
                  ? "Paused"
                  : "Stopped"}
            </div>

            {/* Bot controls */}
            {!botStatus.running ? (
              <button
                data-testid="bot-start-button"
                onClick={() => handleBotAction("start")}
                disabled={botLoading}
                className="h-8 px-3 rounded-sm bg-[#00F090]/10 text-[#00F090] text-xs font-medium hover:bg-[#00F090]/20 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                <Play className="w-3 h-3" /> Start
              </button>
            ) : (
              <>
                {botStatus.paused ? (
                  <button
                    data-testid="bot-resume-button"
                    onClick={() => handleBotAction("resume")}
                    disabled={botLoading}
                    className="h-8 px-3 rounded-sm bg-blue-500/10 text-blue-400 text-xs font-medium hover:bg-blue-500/20 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                  >
                    <Play className="w-3 h-3" /> Resume
                  </button>
                ) : (
                  <button
                    data-testid="bot-pause-button"
                    onClick={() => handleBotAction("pause")}
                    disabled={botLoading}
                    className="h-8 px-3 rounded-sm bg-yellow-500/10 text-yellow-400 text-xs font-medium hover:bg-yellow-500/20 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                  >
                    <Pause className="w-3 h-3" /> Pause
                  </button>
                )}
                <button
                  data-testid="bot-stop-button"
                  onClick={() => handleBotAction("stop")}
                  disabled={botLoading}
                  className="h-8 px-3 rounded-sm bg-[#FF2E5B]/10 text-[#FF2E5B] text-xs font-medium hover:bg-[#FF2E5B]/20 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                >
                  <Square className="w-3 h-3" /> Stop
                </button>
              </>
            )}
          </div>
        </div>

        {/* KPI Cards */}
        <div
          className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-children"
          data-testid="kpi-cards"
        >
          <KPICard
            testId="kpi-balance"
            label="Account Balance"
            value={`$${(d.balance || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
            subvalue={`${d.open_positions_count || 0} open positions`}
            icon={DollarSign}
            color="#3B82F6"
          />
          <KPICard
            testId="kpi-daily-pnl"
            label="Daily PnL"
            value={`${d.daily_pnl >= 0 ? "+" : ""}$${(d.daily_pnl || 0).toFixed(2)}`}
            subvalue={`${d.total_trades || 0} total trades`}
            icon={d.daily_pnl >= 0 ? TrendingUp : TrendingDown}
            color={d.daily_pnl >= 0 ? "#00F090" : "#FF2E5B"}
          />
          <KPICard
            testId="kpi-win-rate"
            label="Win Rate"
            value={`${(d.win_rate || 0).toFixed(1)}%`}
            subvalue={`${performance?.wins || 0}W / ${performance?.losses || 0}L`}
            icon={BarChart3}
            color="#8B5CF6"
          />
          <KPICard
            testId="kpi-total-pnl"
            label="Total PnL"
            value={`${d.total_pnl >= 0 ? "+" : ""}$${(d.total_pnl || 0).toFixed(2)}`}
            subvalue={`Max DD: $${(performance?.max_drawdown || 0).toFixed(2)}`}
            icon={Activity}
            color="#F59E0B"
          />
        </div>

        {/* ML Health Card */}
        <MLHealthCard ml={mlStatus} />

        {/* Main Grid */}
        <div className="grid grid-cols-12 gap-4">
          {/* PnL Chart */}
          <div
            className="col-span-12 lg:col-span-8 bg-[#121212] border border-white/5 rounded-lg p-5"
            data-testid="pnl-chart"
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-semibold">Cumulative PnL</h3>
                <p className="text-xs text-zinc-600 mt-0.5">
                  All-time performance
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-blue-400" />
                <span className="text-xs text-zinc-500">
                  {d.total_trades || 0} trades
                </span>
              </div>
            </div>
            <div className="h-[260px]">
              {pnlData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={pnlData}>
                    <defs>
                      <linearGradient
                        id="pnlGradient"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="5%"
                          stopColor="#3B82F6"
                          stopOpacity={0.3}
                        />
                        <stop
                          offset="95%"
                          stopColor="#3B82F6"
                          stopOpacity={0}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      stroke="#333"
                      strokeDasharray="3 3"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="name"
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
                    <Tooltip content={<CustomTooltip />} />
                    <Area
                      type="monotone"
                      dataKey="pnl"
                      stroke="#3B82F6"
                      strokeWidth={2}
                      fill="url(#pnlGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-zinc-600 text-sm">
                  No trade data yet. Bot is scanning for signals...
                </div>
              )}
            </div>
          </div>

          {/* Active Positions */}
          <div
            className="col-span-12 lg:col-span-4 space-y-3"
            data-testid="positions-panel"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Active Positions</h3>
              <span className="text-xs text-zinc-600 font-mono">
                {positions.length} open
              </span>
            </div>
            {positions.length > 0 ? (
              <div className="space-y-3 stagger-children">
                {positions.map((pos) => (
                  <PositionCard
                    key={pos.id}
                    position={pos}
                    onClose={handleClosePosition}
                  />
                ))}
              </div>
            ) : (
              <div className="p-8 bg-[#121212] border border-white/5 rounded-lg text-center">
                <Activity className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
                <div className="text-sm text-zinc-500">No open positions</div>
                <div className="text-xs text-zinc-700 mt-1">
                  Bot is scanning for entry signals
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Price Ticker */}
        {d.prices && Object.keys(d.prices).length > 0 && (
          <div
            className="grid grid-cols-2 md:grid-cols-4 gap-3"
            data-testid="price-ticker"
          >
            {Object.entries(d.prices).map(([symbol, price]) => (
              <div
                key={symbol}
                className="px-4 py-3 bg-[#121212] border border-white/5 rounded-lg flex items-center justify-between"
              >
                <span className="text-xs font-bold text-zinc-300">
                  {symbol.replace("USDT", "")}
                </span>
                <span className="font-mono text-sm font-medium">
                  $
                  {price >= 1
                    ? price.toLocaleString("en-US", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })
                    : price.toFixed(4)}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Recent Trades Table */}
        <div
          className="bg-[#121212] border border-white/5 rounded-lg"
          data-testid="recent-trades-table"
        >
          <div className="px-5 py-4 border-b border-white/5 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Recent Trades</h3>
            <a
              href="/trades"
              className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
              data-testid="view-all-trades-link"
            >
              View All
            </a>
          </div>
          {recentTrades.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/5">
                    <th className="py-2.5 px-3 text-left text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
                      Symbol
                    </th>
                    <th className="py-2.5 px-3 text-left text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
                      Side
                    </th>
                    <th className="py-2.5 px-3 text-left text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
                      Entry
                    </th>
                    <th className="py-2.5 px-3 text-left text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
                      Exit
                    </th>
                    <th className="py-2.5 px-3 text-left text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
                      PnL
                    </th>
                    <th className="py-2.5 px-3 text-left text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
                      Reason
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {recentTrades.map((trade) => (
                    <TradeRow key={trade.id} trade={trade} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-10 text-center text-sm text-zinc-600">
              No trades yet. The bot will execute trades when entry signals are
              detected.
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
