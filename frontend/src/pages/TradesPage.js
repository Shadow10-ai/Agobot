import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { AppLayout } from "@/components/AppLayout";
import { Download, Search, Filter, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const PAGE_LIMIT = 20;

export default function TradesPage({ user, onLogout }) {
  const [trades, setTrades] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [symbolFilter, setSymbolFilter] = useState("");

  const fetchTrades = useCallback(async () => {
    try {
      const params = { limit: PAGE_LIMIT, skip: page * PAGE_LIMIT };
      if (symbolFilter) params.symbol = symbolFilter;
      const res = await api.get("/trades", { params });
      setTrades(res.data.trades || []);
      setTotal(res.data.total || 0);
    } catch {
      // silently swallow — UI shows empty state
    } finally {
      setLoading(false);
    }
  }, [page, symbolFilter]);

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades]);

  const exportCSV = () => {
    if (trades.length === 0) {
      toast.error("No trades to export");
      return;
    }
    const headers = "Symbol,Side,Entry,Exit,Qty,PnL,PnL%,Reason,Opened,Closed\n";
    const rows = trades
      .map(
        (t) =>
          `${t.symbol},${t.side},${t.entry_price},${t.exit_price},${t.quantity},${t.pnl},${t.pnl_percent},${t.exit_reason},${t.opened_at},${t.closed_at}`
      )
      .join("\n");
    const blob = new Blob([headers + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trades_${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Exported successfully");
  };

  const totalPages = Math.ceil(total / PAGE_LIMIT);

  return (
    <AppLayout user={user} onLogout={onLogout}>
      <div className="p-5 lg:p-8 space-y-6" data-testid="trades-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Trade History</h1>
            <p className="text-sm text-zinc-500 mt-1">
              {total} total trades recorded
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              data-testid="refresh-trades"
              onClick={() => { setLoading(true); fetchTrades(); }}
              className="h-8 px-3 rounded-sm border border-white/10 text-zinc-400 text-xs font-medium hover:bg-white/5 transition-colors flex items-center gap-1.5"
            >
              <RefreshCw className="w-3 h-3" /> Refresh
            </button>
            <button
              data-testid="export-csv"
              onClick={exportCSV}
              className="h-8 px-3 rounded-sm bg-blue-500/10 text-blue-400 text-xs font-medium hover:bg-blue-500/20 transition-colors flex items-center gap-1.5"
            >
              <Download className="w-3 h-3" /> Export CSV
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600" />
            <select
              data-testid="symbol-filter"
              value={symbolFilter}
              onChange={(e) => { setSymbolFilter(e.target.value); setPage(0); }}
              className="h-9 pl-9 pr-8 rounded-sm bg-[#121212] border border-[#27272A] text-sm text-zinc-300 appearance-none focus:outline-none focus:border-blue-500 transition-colors"
            >
              <option value="">All Symbols</option>
              {["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT"].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Table */}
        <div className="bg-[#121212] border border-white/5 rounded-lg overflow-hidden">
          {loading ? (
            <div className="p-16 text-center">
              <RefreshCw className="w-5 h-5 text-blue-500 animate-spin mx-auto" />
            </div>
          ) : trades.length === 0 ? (
            <div className="p-16 text-center text-sm text-zinc-600">
              No trades found
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full" data-testid="trades-table">
                <thead>
                  <tr className="border-b border-white/5">
                    {["Symbol", "Side", "Entry", "Exit", "Qty", "PnL", "PnL %", "Reason", "Time"].map((h) => (
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
                  {trades.map((t) => (
                    <tr
                      key={t.id}
                      data-testid={`history-trade-${t.id}`}
                      className="border-b border-white/5 hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="py-3 px-4 text-xs font-bold">{t.symbol}</td>
                      <td className="py-3 px-4">
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400">
                          {t.side}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-xs">
                        ${t.entry_price?.toFixed(2)}
                      </td>
                      <td className="py-3 px-4 font-mono text-xs">
                        ${t.exit_price?.toFixed(2)}
                      </td>
                      <td className="py-3 px-4 font-mono text-xs text-zinc-400">
                        {t.quantity?.toFixed(6)}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`font-mono text-xs font-medium ${t.pnl > 0 ? "text-[#00F090]" : "text-[#FF2E5B]"}`}
                        >
                          {t.pnl > 0 ? "+" : ""}
                          ${t.pnl?.toFixed(2)}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`font-mono text-xs ${t.pnl_percent > 0 ? "text-[#00F090]" : "text-[#FF2E5B]"}`}
                        >
                          {t.pnl_percent > 0 ? "+" : ""}
                          {t.pnl_percent?.toFixed(2)}%
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                            t.exit_reason === "TAKE_PROFIT"
                              ? "bg-[#00F090]/10 text-[#00F090]"
                              : t.exit_reason === "STOP_LOSS"
                                ? "bg-[#FF2E5B]/10 text-[#FF2E5B]"
                                : t.exit_reason === "TRAIL_STOP"
                                  ? "bg-purple-500/10 text-purple-400"
                                  : "bg-zinc-500/10 text-zinc-400"
                          }`}
                        >
                          {t.exit_reason}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-xs text-zinc-500">
                        {t.closed_at ? new Date(t.closed_at).toLocaleString() : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="px-4 py-3 border-t border-white/5 flex items-center justify-between">
              <span className="text-xs text-zinc-500">
                Page {page + 1} of {totalPages}
              </span>
              <div className="flex items-center gap-2">
                <button
                  data-testid="prev-page"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="h-7 px-3 rounded-sm border border-white/10 text-xs text-zinc-400 hover:bg-white/5 disabled:opacity-30 transition-colors"
                >
                  Previous
                </button>
                <button
                  data-testid="next-page"
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="h-7 px-3 rounded-sm border border-white/10 text-xs text-zinc-400 hover:bg-white/5 disabled:opacity-30 transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
