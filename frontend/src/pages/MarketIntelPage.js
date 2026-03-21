import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { AppLayout } from "@/components/AppLayout";
import { Waves, DollarSign, Activity, RefreshCw, ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";
import { toast } from "sonner";

const pressureColor = {
  STRONG_BUY: "text-emerald-400",
  BUY: "text-emerald-400/70",
  NEUTRAL: "text-zinc-400",
  SELL: "text-red-400/70",
  STRONG_SELL: "text-red-400",
};

const sentimentColor = {
  EXTREMELY_BULLISH: "text-emerald-400",
  BULLISH: "text-emerald-400/70",
  NEUTRAL: "text-zinc-400",
  BEARISH: "text-red-400/70",
  EXTREMELY_BEARISH: "text-red-400",
};

const DepthBar = ({ bid, ask, label }) => {
  const total = bid + ask;
  const bidPct = total > 0 ? (bid / total) * 100 : 50;
  return (
    <div className="mb-2">
      <div className="flex justify-between text-[9px] mb-0.5">
        <span className="text-emerald-400 font-mono">${bid.toLocaleString()}</span>
        <span className="text-[10px] text-zinc-500">{label}</span>
        <span className="text-red-400 font-mono">${ask.toLocaleString()}</span>
      </div>
      <div className="flex h-1.5 rounded-full overflow-hidden gap-px">
        <div className="bg-emerald-500/60 rounded-l-full" style={{ width: `${bidPct}%` }} />
        <div className="bg-red-500/60 rounded-r-full" style={{ width: `${100 - bidPct}%` }} />
      </div>
    </div>
  );
};

export default function MarketIntelPage({ user, onLogout }) {
  const [orderFlow, setOrderFlow] = useState(null);
  const [selectedSymbol, setSelectedSymbol] = useState("BTCUSDT");
  const [symbolDetail, setSymbolDetail] = useState(null);
  const [fundingRates, setFundingRates] = useState(null);
  const [whaleActivity, setWhaleActivity] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [ofRes, frRes, waRes] = await Promise.all([
        api.get("/orderflow"),
        api.get("/funding-rates"),
        api.get("/whale-activity"),
      ]);
      setOrderFlow(ofRes.data);
      setFundingRates(frRes.data);
      setWhaleActivity(waRes.data);
    } catch (err) {
      console.error("Failed to fetch market intel:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSymbolDetail = useCallback(async (symbol) => {
    try {
      const res = await api.get(`/orderflow/${symbol}`);
      setSymbolDetail(res.data);
      setSelectedSymbol(symbol);
    } catch (err) {
      toast.error("Failed to fetch order book");
    }
  }, []);

  useEffect(() => {
    fetchData();
    fetchSymbolDetail("BTCUSDT");
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData, fetchSymbolDetail]);

  if (loading) {
    return (
      <AppLayout user={user} onLogout={onLogout}>
        <div className="flex items-center justify-center min-h-screen">
          <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      </AppLayout>
    );
  }

  const of = orderFlow?.symbols || {};
  const fr = fundingRates?.rates || {};
  const wa = whaleActivity || {};
  const detail = symbolDetail;

  return (
    <AppLayout user={user} onLogout={onLogout}>
      <div className="p-5 lg:p-8 space-y-6" data-testid="market-intel-page">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Market Intelligence</h1>
            <p className="text-sm text-zinc-500 mt-1">Order flow, funding rates & whale tracking</p>
          </div>
          <button onClick={() => { fetchData(); fetchSymbolDetail(selectedSymbol); }} className="h-8 px-3 rounded-sm border border-white/10 text-zinc-400 text-xs hover:bg-white/5 transition-colors">
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        {/* Order Flow Summary */}
        <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="order-flow-section">
          <div className="flex items-center gap-2 mb-4">
            <Waves className="w-4 h-4 text-blue-400" />
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Order Flow Analysis</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            {Object.entries(of).map(([symbol, data]) => (
              <button
                key={symbol}
                data-testid={`of-${symbol}`}
                onClick={() => fetchSymbolDetail(symbol)}
                className={`p-3 rounded-lg border text-left transition-colors ${
                  selectedSymbol === symbol ? "bg-blue-500/10 border-blue-500/30" : "bg-[#0A0A0A] border-white/5 hover:border-white/10"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold">{symbol.replace("USDT", "")}</span>
                  {data.pressure.includes("BUY") ? (
                    <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
                  ) : data.pressure.includes("SELL") ? (
                    <ArrowDownRight className="w-3.5 h-3.5 text-red-400" />
                  ) : (
                    <Minus className="w-3.5 h-3.5 text-zinc-500" />
                  )}
                </div>
                <p className={`text-[10px] font-bold ${pressureColor[data.pressure]}`}>{data.pressure}</p>
                <p className="text-[10px] text-zinc-600 font-mono">Ratio: {data.imbalance_ratio}</p>
                <p className="text-[10px] text-zinc-600">Walls: {data.bid_walls}B / {data.ask_walls}A</p>
              </button>
            ))}
          </div>

          {/* Detailed Order Book */}
          {detail && (
            <div className="bg-[#0A0A0A] border border-white/5 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold">{detail.symbol} Order Book Depth</span>
                <span className="text-[10px] text-zinc-500">Source: {detail.source}</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Depth Levels */}
                <div>
                  <p className="text-[10px] text-zinc-500 mb-2">Depth Levels (Bid vs Ask USDT)</p>
                  {Object.entries(detail.depth_levels || {}).map(([level, data]) => (
                    <DepthBar key={level} bid={data.bid_usdt} ask={data.ask_usdt} label={`±${level}`} />
                  ))}
                </div>
                {/* Walls & Stats */}
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-emerald-500/5 border border-emerald-500/10 rounded p-2">
                      <p className="text-[9px] text-zinc-500">Total Bid Vol</p>
                      <p className="text-sm font-mono text-emerald-400">{detail.total_bid_volume?.toFixed(2)}</p>
                    </div>
                    <div className="bg-red-500/5 border border-red-500/10 rounded p-2">
                      <p className="text-[9px] text-zinc-500">Total Ask Vol</p>
                      <p className="text-sm font-mono text-red-400">{detail.total_ask_volume?.toFixed(2)}</p>
                    </div>
                  </div>
                  {detail.bid_walls?.length > 0 && (
                    <div>
                      <p className="text-[9px] text-zinc-500 mb-1">Support Walls</p>
                      {detail.bid_walls.slice(0, 3).map((w, i) => (
                        <p key={i} className="text-[10px] text-emerald-400/70 font-mono">
                          ${w.price.toLocaleString()} — ${w.usdt_value.toLocaleString()}
                        </p>
                      ))}
                    </div>
                  )}
                  {detail.ask_walls?.length > 0 && (
                    <div>
                      <p className="text-[9px] text-zinc-500 mb-1">Resistance Walls</p>
                      {detail.ask_walls.slice(0, 3).map((w, i) => (
                        <p key={i} className="text-[10px] text-red-400/70 font-mono">
                          ${w.price.toLocaleString()} — ${w.usdt_value.toLocaleString()}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Funding Rates */}
          <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="funding-rates-section">
            <div className="flex items-center gap-2 mb-4">
              <DollarSign className="w-4 h-4 text-yellow-400" />
              <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Funding Rates</h3>
              {fundingRates?.has_opportunities && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 font-medium animate-pulse">
                  ARB OPPORTUNITY
                </span>
              )}
            </div>
            <div className="space-y-2">
              {Object.entries(fr).map(([symbol, data]) => (
                <div key={symbol} className="flex items-center justify-between p-2 rounded bg-[#0A0A0A] border border-white/5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold w-16">{symbol.replace("USDT", "")}</span>
                    <span className={`text-[10px] font-mono ${data.current_rate > 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {data.current_rate > 0 ? "+" : ""}{data.current_rate}%
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-[10px] ${sentimentColor[data.sentiment]}`}>{data.sentiment}</span>
                    {data.arb_opportunity && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-yellow-500/20 text-yellow-400">ARB</span>
                    )}
                    <span className="text-[10px] text-zinc-600 font-mono w-16 text-right">{data.annualized_yield}% APR</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[9px] text-zinc-600 mt-3">Positive rate = longs pay shorts. Extreme rates signal potential reversals.</p>
          </div>

          {/* Whale Activity */}
          <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="whale-activity-section">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Whale Activity</h3>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold tracking-wider ${
                wa.whale_signal === "ACCUMULATION" ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" :
                wa.whale_signal === "DISTRIBUTION" ? "bg-red-500/20 text-red-400 border border-red-500/30" :
                "bg-zinc-700/50 text-zinc-400 border border-zinc-600"
              }`}>
                {wa.whale_signal}
              </span>
            </div>

            {/* Summary */}
            <div className="grid grid-cols-3 gap-2 mb-4">
              <div className="bg-emerald-500/5 border border-emerald-500/10 rounded p-2 text-center">
                <p className="text-[9px] text-zinc-500">Whale Buys</p>
                <p className="text-sm font-mono text-emerald-400">${(wa.total_whale_buys || 0).toLocaleString()}</p>
                <p className="text-[9px] text-zinc-600">{wa.buy_count} trades</p>
              </div>
              <div className="bg-red-500/5 border border-red-500/10 rounded p-2 text-center">
                <p className="text-[9px] text-zinc-500">Whale Sells</p>
                <p className="text-sm font-mono text-red-400">${(wa.total_whale_sells || 0).toLocaleString()}</p>
                <p className="text-[9px] text-zinc-600">{wa.sell_count} trades</p>
              </div>
              <div className={`border rounded p-2 text-center ${(wa.net_flow || 0) > 0 ? "bg-emerald-500/5 border-emerald-500/10" : "bg-red-500/5 border-red-500/10"}`}>
                <p className="text-[9px] text-zinc-500">Net Flow</p>
                <p className={`text-sm font-mono ${(wa.net_flow || 0) > 0 ? "text-emerald-400" : "text-red-400"}`}>
                  ${Math.abs(wa.net_flow || 0).toLocaleString()}
                </p>
                <p className="text-[9px] text-zinc-600">{(wa.net_flow || 0) > 0 ? "Inflow" : "Outflow"}</p>
              </div>
            </div>

            {/* Per Symbol */}
            {wa.symbol_breakdown && (
              <div className="space-y-1.5 mb-3">
                {Object.entries(wa.symbol_breakdown).map(([sym, data]) => (
                  <div key={sym} className="flex items-center justify-between p-1.5 rounded bg-[#0A0A0A]">
                    <span className="text-[10px] font-bold w-16">{sym.replace("USDT", "")}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-emerald-400/70 font-mono">${data.buy_volume.toLocaleString()}</span>
                      <span className="text-[10px] text-zinc-600">/</span>
                      <span className="text-[10px] text-red-400/70 font-mono">${data.sell_volume.toLocaleString()}</span>
                    </div>
                    <span className={`text-[9px] font-bold ${
                      data.signal === "ACCUMULATION" ? "text-emerald-400" : data.signal === "DISTRIBUTION" ? "text-red-400" : "text-zinc-500"
                    }`}>{data.signal}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Recent Whale Trades */}
            <div>
              <p className="text-[9px] text-zinc-500 mb-1.5">Recent Large Trades (&gt;${(wa.min_trade_usdt || 50000).toLocaleString()})</p>
              <div className="max-h-32 overflow-y-auto space-y-1">
                {(wa.whale_trades || []).slice(0, 8).map((t, i) => (
                  <div key={i} className="flex items-center justify-between text-[10px] p-1 rounded bg-[#0A0A0A]">
                    <span className="font-bold w-14">{t.symbol.replace("USDT", "")}</span>
                    <span className={t.side === "BUY" ? "text-emerald-400" : "text-red-400"}>{t.side}</span>
                    <span className="font-mono text-zinc-400">${t.usdt_value.toLocaleString()}</span>
                    <span className="text-zinc-600 w-14 text-right">{new Date(t.time).toLocaleTimeString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
