import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { AppLayout } from "@/components/AppLayout";
import { Save, RotateCcw, AlertTriangle, Check, Settings, Bell } from "lucide-react";
import { toast } from "sonner";

const InputField = ({ label, name, value, onChange, type = "number", step, min, max, description }) => (
  <div>
    <label className="overline block mb-2">{label}</label>
    <input
      data-testid={`config-${name}`}
      type={type}
      value={value}
      onChange={(e) => onChange(name, type === "number" ? parseFloat(e.target.value) || 0 : e.target.value)}
      step={step}
      min={min}
      max={max}
      className="w-full h-9 px-3 rounded-sm bg-[#0A0A0A] border border-[#27272A] text-sm font-mono text-white placeholder:text-zinc-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-colors"
    />
    {description && <p className="text-[10px] text-zinc-600 mt-1.5">{description}</p>}
  </div>
);

export default function ConfigPage({ user, onLogout }) {
  const [config, setConfig] = useState(null);
  const [telegram, setTelegram] = useState({ telegram_token: "", telegram_chat_id: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingTg, setSavingTg] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await api.get("/bot/config");
      setConfig(res.data);
      setTelegram({
        telegram_token: res.data.telegram_token || "",
        telegram_chat_id: res.data.telegram_chat_id || ""
      });
    } catch (err) {
      console.error("Failed to fetch config:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleChange = (field, value) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        symbols: config.symbols,
        base_usdt_per_trade: config.base_usdt_per_trade,
        risk_per_trade_percent: config.risk_per_trade_percent,
        max_daily_loss_usdt: config.max_daily_loss_usdt,
        max_total_drawdown_percent: config.max_total_drawdown_percent,
        rsi_period: config.rsi_period,
        rsi_overbought: config.rsi_overbought,
        rsi_oversold: config.rsi_oversold,
        min_entry_probability: config.min_entry_probability,
        trailing_stop_activate_pips: config.trailing_stop_activate_pips,
        trailing_stop_distance_pips: config.trailing_stop_distance_pips,
      };
      await api.put("/bot/config", payload);
      toast.success("Configuration saved");
    } catch (err) {
      toast.error("Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveTelegram = async () => {
    setSavingTg(true);
    try {
      await api.put("/bot/telegram", telegram);
      toast.success("Telegram settings saved");
    } catch (err) {
      toast.error("Failed to save Telegram settings");
    } finally {
      setSavingTg(false);
    }
  };

  const handleReset = () => {
    setConfig({
      ...config,
      base_usdt_per_trade: 50,
      risk_per_trade_percent: 0.5,
      max_daily_loss_usdt: 20,
      max_total_drawdown_percent: 5,
      rsi_period: 14,
      rsi_overbought: 70,
      rsi_oversold: 30,
      min_entry_probability: 0.65,
      trailing_stop_activate_pips: 2.4,
      trailing_stop_distance_pips: 1.2,
    });
    toast.info("Reset to defaults (unsaved)");
  };

  if (loading) {
    return (
      <AppLayout user={user} onLogout={onLogout}>
        <div className="flex items-center justify-center min-h-screen">
          <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout user={user} onLogout={onLogout}>
      <div className="p-5 lg:p-8 space-y-6" data-testid="config-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Configuration</h1>
            <p className="text-sm text-zinc-500 mt-1">
              Manage bot trading parameters
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              data-testid="reset-config"
              onClick={handleReset}
              className="h-8 px-3 rounded-sm border border-white/10 text-zinc-400 text-xs font-medium hover:bg-white/5 transition-colors flex items-center gap-1.5"
            >
              <RotateCcw className="w-3 h-3" /> Reset
            </button>
            <button
              data-testid="save-config"
              onClick={handleSave}
              disabled={saving}
              className="h-8 px-3 rounded-sm bg-blue-500 text-white text-xs font-medium hover:bg-blue-600 disabled:opacity-50 shadow-[0_0_15px_rgba(59,130,246,0.3)] transition-colors flex items-center gap-1.5"
            >
              <Save className="w-3 h-3" /> {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>

        {/* DRY Mode Banner */}
        <div className="flex items-center gap-3 p-4 bg-yellow-500/5 border border-yellow-500/20 rounded-lg" data-testid="dry-mode-banner">
          <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0" />
          <div>
            <div className="text-xs font-semibold text-yellow-400">DRY MODE ACTIVE</div>
            <div className="text-[11px] text-zinc-500 mt-0.5">
              No real funds are being traded. All orders are simulated.
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Trading Parameters */}
          <div className="bg-[#121212] border border-white/5 rounded-lg p-6 space-y-5">
            <div className="flex items-center gap-2 mb-2">
              <Settings className="w-4 h-4 text-blue-400" />
              <h3 className="text-sm font-semibold">Trading Parameters</h3>
            </div>
            
            <InputField
              label="Base USDT per Trade"
              name="base_usdt_per_trade"
              value={config?.base_usdt_per_trade || 0}
              onChange={handleChange}
              step={10}
              min={10}
              description="Amount of USDT to allocate per trade"
            />
            <InputField
              label="Risk per Trade (%)"
              name="risk_per_trade_percent"
              value={config?.risk_per_trade_percent || 0}
              onChange={handleChange}
              step={0.1}
              min={0.1}
              max={10}
              description="Percentage of account to risk per trade"
            />
            <InputField
              label="Max Daily Loss (USDT)"
              name="max_daily_loss_usdt"
              value={config?.max_daily_loss_usdt || 0}
              onChange={handleChange}
              step={5}
              min={1}
              description="Bot pauses when daily loss exceeds this"
            />
            <InputField
              label="Max Total Drawdown (%)"
              name="max_total_drawdown_percent"
              value={config?.max_total_drawdown_percent || 0}
              onChange={handleChange}
              step={0.5}
              min={1}
              max={50}
              description="Maximum allowed drawdown from peak balance"
            />
            <InputField
              label="Min Entry Probability"
              name="min_entry_probability"
              value={config?.min_entry_probability || 0}
              onChange={handleChange}
              step={0.05}
              min={0.1}
              max={1}
              description="Minimum signal score (0-1) required to enter a trade"
            />
          </div>

          {/* Indicator Settings */}
          <div className="space-y-6">
            <div className="bg-[#121212] border border-white/5 rounded-lg p-6 space-y-5">
              <div className="flex items-center gap-2 mb-2">
                <Settings className="w-4 h-4 text-purple-400" />
                <h3 className="text-sm font-semibold">Indicator Settings</h3>
              </div>
              
              <InputField
                label="RSI Period"
                name="rsi_period"
                value={config?.rsi_period || 0}
                onChange={handleChange}
                step={1}
                min={2}
                max={50}
              />
              <div className="grid grid-cols-2 gap-4">
                <InputField
                  label="RSI Overbought"
                  name="rsi_overbought"
                  value={config?.rsi_overbought || 0}
                  onChange={handleChange}
                  step={1}
                  min={50}
                  max={100}
                />
                <InputField
                  label="RSI Oversold"
                  name="rsi_oversold"
                  value={config?.rsi_oversold || 0}
                  onChange={handleChange}
                  step={1}
                  min={0}
                  max={50}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <InputField
                  label="Trail Activate (ATR x)"
                  name="trailing_stop_activate_pips"
                  value={config?.trailing_stop_activate_pips || 0}
                  onChange={handleChange}
                  step={0.1}
                  min={0.5}
                />
                <InputField
                  label="Trail Distance (ATR x)"
                  name="trailing_stop_distance_pips"
                  value={config?.trailing_stop_distance_pips || 0}
                  onChange={handleChange}
                  step={0.1}
                  min={0.1}
                />
              </div>
            </div>

            {/* Telegram */}
            <div className="bg-[#121212] border border-white/5 rounded-lg p-6 space-y-5">
              <div className="flex items-center gap-2 mb-2">
                <Bell className="w-4 h-4 text-[#00F090]" />
                <h3 className="text-sm font-semibold">Telegram Notifications</h3>
              </div>
              
              <div>
                <label className="overline block mb-2">Bot Token</label>
                <input
                  data-testid="config-telegram-token"
                  type="password"
                  value={telegram.telegram_token}
                  onChange={(e) => setTelegram(prev => ({ ...prev, telegram_token: e.target.value }))}
                  placeholder="Enter Telegram bot token"
                  className="w-full h-9 px-3 rounded-sm bg-[#0A0A0A] border border-[#27272A] text-sm font-mono text-white placeholder:text-zinc-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-colors"
                />
              </div>
              <div>
                <label className="overline block mb-2">Chat ID</label>
                <input
                  data-testid="config-telegram-chat-id"
                  type="text"
                  value={telegram.telegram_chat_id}
                  onChange={(e) => setTelegram(prev => ({ ...prev, telegram_chat_id: e.target.value }))}
                  placeholder="Enter Telegram chat ID"
                  className="w-full h-9 px-3 rounded-sm bg-[#0A0A0A] border border-[#27272A] text-sm font-mono text-white placeholder:text-zinc-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-colors"
                />
              </div>
              <button
                data-testid="save-telegram"
                onClick={handleSaveTelegram}
                disabled={savingTg}
                className="w-full h-9 rounded-sm bg-[#00F090]/10 text-[#00F090] text-xs font-medium hover:bg-[#00F090]/20 disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5"
              >
                <Check className="w-3 h-3" />
                {savingTg ? "Saving..." : "Save Telegram Settings"}
              </button>
            </div>
          </div>
        </div>

        {/* Active Symbols */}
        <div className="bg-[#121212] border border-white/5 rounded-lg p-6" data-testid="symbols-config">
          <h3 className="text-sm font-semibold mb-4">Active Trading Symbols</h3>
          <div className="flex flex-wrap gap-2">
            {["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT"].map((symbol) => {
              const isActive = config?.symbols?.includes(symbol);
              return (
                <button
                  key={symbol}
                  data-testid={`symbol-toggle-${symbol}`}
                  onClick={() => {
                    const current = config?.symbols || [];
                    const updated = isActive
                      ? current.filter((s) => s !== symbol)
                      : [...current, symbol];
                    handleChange("symbols", updated);
                  }}
                  className={`h-8 px-3 rounded-sm text-xs font-mono font-medium transition-colors ${
                    isActive
                      ? "bg-blue-500/15 text-blue-400 border border-blue-500/30"
                      : "bg-[#0A0A0A] text-zinc-600 border border-[#27272A] hover:text-zinc-400"
                  }`}
                >
                  {symbol.replace("USDT", "/USDT")}
                </button>
              );
            })}
          </div>
          <p className="text-[10px] text-zinc-600 mt-3">
            Click to toggle symbols. Save to apply changes.
          </p>
        </div>
      </div>
    </AppLayout>
  );
}
