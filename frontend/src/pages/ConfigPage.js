import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { AppLayout } from "@/components/AppLayout";
import { Save, RotateCcw, AlertTriangle, Check, Settings, Bell, Shield, Zap, Key, Wifi, WifiOff } from "lucide-react";
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
  const [binanceKeys, setBinanceKeys] = useState({ api_key: "", api_secret: "" });
  const [savingKeys, setSavingKeys] = useState(false);
  const [testingConn, setTestingConn] = useState(false);
  const [connTestResult, setConnTestResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingTg, setSavingTg] = useState(false);
  const [modeInfo, setModeInfo] = useState({ mode: "DRY", binance_connected: false, binance_keys_configured: false, api_key_preview: "" });
  const [showLiveConfirm, setShowLiveConfirm] = useState(false);
  const [switchingMode, setSwitchingMode] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const [configRes, modeRes] = await Promise.all([
        api.get("/bot/config"),
        api.get("/bot/mode")
      ]);
      setConfig(configRes.data);
      setModeInfo(modeRes.data);
      setTelegram({
        telegram_token: configRes.data.telegram_token || "",
        telegram_chat_id: configRes.data.telegram_chat_id || ""
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
        allow_short: config.allow_short,
        max_trades_per_hour: config.max_trades_per_hour,
        max_trades_per_day: config.max_trades_per_day,
        min_risk_reward_ratio: config.min_risk_reward_ratio,
        cooldown_after_loss_scans: config.cooldown_after_loss_scans,
        min_confidence_score: config.min_confidence_score,
        spread_max_percent: config.spread_max_percent,
        min_24h_volume_usdt: config.min_24h_volume_usdt,
        max_slippage_percent: config.max_slippage_percent,
        require_trend_alignment: config.require_trend_alignment,
        ml_min_win_probability: config.ml_min_win_probability,
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

  const handleSaveBinanceKeys = async () => {
    if (!binanceKeys.api_key || !binanceKeys.api_secret) {
      toast.error("Both API Key and Secret are required");
      return;
    }
    setSavingKeys(true);
    setConnTestResult(null);
    try {
      const res = await api.put("/bot/binance-keys", binanceKeys);
      setModeInfo((prev) => ({ ...prev, binance_connected: res.data.connected, binance_keys_configured: true, api_key_preview: res.data.api_key_preview }));
      setBinanceKeys({ api_key: "", api_secret: "" });
      if (res.data.connected) {
        toast.success(res.data.message);
        setConnTestResult({ ok: true, message: res.data.message });
      } else {
        const errMsg = res.data.error || res.data.message || "Connection failed";
        toast.error(errMsg);
        setConnTestResult({ connected: false, error: errMsg });
      }
    } catch (err) {
      toast.error("Failed to save API keys");
    } finally {
      setSavingKeys(false);
    }
  };

  const handleTestConnection = async () => {
    setTestingConn(true);
    setConnTestResult(null);
    try {
      const res = await api.get("/bot/binance-test");
      setConnTestResult(res.data);
      setModeInfo((prev) => ({ ...prev, binance_connected: res.data.connected }));
      if (res.data.connected) {
        toast.success(res.data.message);
      } else {
        toast.error(res.data.error || "Connection failed");
      }
    } catch {
      setConnTestResult({ ok: false, error: "Test request failed — check backend" });
    } finally {
      setTestingConn(false);
    }
  };

  const handleModeToggle = async (newMode) => {
    if (newMode === "LIVE") {
      setShowLiveConfirm(true);
      return;
    }
    await switchMode("DRY");
  };

  const switchMode = async (mode) => {
    setSwitchingMode(true);
    try {
      const res = await api.put("/bot/mode", { mode });
      setModeInfo((prev) => ({ ...prev, mode: res.data.mode }));
      toast.success(res.data.message);
      setShowLiveConfirm(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to switch mode");
    } finally {
      setSwitchingMode(false);
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

  const isLive = modeInfo.mode === "LIVE";

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

        {/* Exchange Connection */}
        <div
          data-testid="exchange-connection-section"
          className={`relative overflow-hidden rounded-lg border p-5 ${
            modeInfo.binance_connected
              ? "bg-emerald-500/5 border-emerald-500/20"
              : "bg-zinc-800/30 border-white/5"
          }`}
        >
          <div className="flex items-center gap-2 mb-4">
            <Key className="w-4 h-4 text-yellow-400" />
            <h3 className="text-sm font-semibold">Binance API Connection</h3>
            <span
              data-testid="binance-connection-badge"
              className={`text-[10px] px-2 py-0.5 rounded-full font-bold tracking-wider flex items-center gap-1 ${
                modeInfo.binance_connected
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                  : "bg-red-500/20 text-red-400 border border-red-500/30"
              }`}
            >
              {modeInfo.binance_connected ? <Wifi className="w-2.5 h-2.5" /> : <WifiOff className="w-2.5 h-2.5" />}
              {modeInfo.binance_connected ? "CONNECTED" : "DISCONNECTED"}
            </span>
            {modeInfo.api_key_preview && (
              <span className="text-[10px] text-zinc-500 font-mono ml-1">Key: {modeInfo.api_key_preview}</span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="overline block mb-2">API Key</label>
              <input
                data-testid="binance-api-key-input"
                type="password"
                value={binanceKeys.api_key}
                onChange={(e) => setBinanceKeys((prev) => ({ ...prev, api_key: e.target.value }))}
                placeholder={modeInfo.api_key_preview ? `Current: ${modeInfo.api_key_preview}` : "Paste your Binance API key"}
                className="w-full h-9 px-3 rounded-sm bg-[#0A0A0A] border border-[#27272A] text-sm font-mono text-white placeholder:text-zinc-600 focus:outline-none focus:border-yellow-500 focus:ring-1 focus:ring-yellow-500/20 transition-colors"
              />
            </div>
            <div>
              <label className="overline block mb-2">API Secret</label>
              <input
                data-testid="binance-api-secret-input"
                type="password"
                value={binanceKeys.api_secret}
                onChange={(e) => setBinanceKeys((prev) => ({ ...prev, api_secret: e.target.value }))}
                placeholder="Paste your Binance API secret"
                className="w-full h-9 px-3 rounded-sm bg-[#0A0A0A] border border-[#27272A] text-sm font-mono text-white placeholder:text-zinc-600 focus:outline-none focus:border-yellow-500 focus:ring-1 focus:ring-yellow-500/20 transition-colors"
              />
            </div>
          </div>

          <div className="flex items-center justify-between">
            <p className="text-[10px] text-zinc-600 max-w-xs leading-relaxed">
              Keys are stored securely in your database. Enable <strong className="text-zinc-400">Spot Trading</strong> and optionally <strong className="text-zinc-400">Futures</strong> permissions on your Binance key.{" "}
              <strong className="text-yellow-500/80">Set IP restriction to "Unrestricted"</strong> — Render uses dynamic IPs.
              <a href="https://www.binance.com/en/my/settings/api-management" target="_blank" rel="noopener noreferrer" className="text-yellow-500/70 ml-1 hover:text-yellow-400">Manage API keys →</a>
            </p>
            <div className="flex gap-2 flex-shrink-0">
              {modeInfo.binance_keys_configured && (
                <button
                  data-testid="test-binance-conn-btn"
                  onClick={handleTestConnection}
                  disabled={testingConn}
                  className="h-9 px-4 rounded-sm bg-zinc-700 text-white text-xs font-semibold hover:bg-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5 whitespace-nowrap"
                >
                  <Wifi className="w-3 h-3" />
                  {testingConn ? "Testing..." : "Test Connection"}
                </button>
              )}
              <button
                data-testid="save-binance-keys-btn"
                onClick={handleSaveBinanceKeys}
                disabled={savingKeys || (!binanceKeys.api_key && !binanceKeys.api_secret)}
                className="h-9 px-5 rounded-sm bg-yellow-500 text-black text-xs font-bold hover:bg-yellow-400 disabled:opacity-40 disabled:cursor-not-allowed shadow-[0_0_15px_rgba(234,179,8,0.3)] transition-colors flex items-center gap-1.5 whitespace-nowrap"
              >
                <Zap className="w-3 h-3" />
                {savingKeys ? "Connecting..." : "Save & Connect"}
              </button>
            </div>
          </div>

          {/* Connection test result */}
          {connTestResult && (
            <div
              data-testid="conn-test-result"
              className={`mt-3 px-3 py-2 rounded text-[11px] font-mono border ${
                connTestResult.connected
                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                  : "bg-red-500/10 border-red-500/20 text-red-400"
              }`}
            >
              {connTestResult.connected
                ? `✓ ${connTestResult.message}`
                : `✗ ${connTestResult.error}`}
            </div>
          )}
        </div>

        {/* Trading Mode Toggle */}
        <div
          data-testid="mode-toggle-section"
          className={`relative overflow-hidden rounded-lg border p-5 ${
            isLive
              ? "bg-red-500/5 border-red-500/30"
              : "bg-emerald-500/5 border-emerald-500/20"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {isLive ? (
                <Zap className="w-5 h-5 text-red-400" />
              ) : (
                <Shield className="w-5 h-5 text-emerald-400" />
              )}
              <div>
                <div className="text-sm font-semibold flex items-center gap-2">
                  Trading Mode
                  <span
                    data-testid="mode-badge"
                    className={`text-[10px] px-2 py-0.5 rounded-full font-bold tracking-wider ${
                      isLive
                        ? "bg-red-500/20 text-red-400 border border-red-500/30"
                        : "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    }`}
                  >
                    {modeInfo.mode}
                  </span>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {isLive
                    ? "LIVE MODE — Real orders are being placed on Binance with real funds."
                    : "DRY MODE — All trades are simulated. No real funds are used."}
                </p>
                {!modeInfo.binance_keys_configured && (
                  <p className="text-[10px] text-yellow-500 mt-1">
                    Binance API keys not configured. Add them in the Exchange Connection section above.
                  </p>
                )}
                {modeInfo.binance_keys_configured && !modeInfo.binance_connected && (
                  <p className="text-[10px] text-yellow-500 mt-1">
                    Binance client not connected. Re-enter your keys above and click "Save &amp; Connect".
                  </p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                data-testid="mode-dry-btn"
                onClick={() => handleModeToggle("DRY")}
                disabled={!isLive || switchingMode}
                className={`h-8 px-4 rounded-sm text-xs font-medium transition-colors ${
                  !isLive
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                    : "bg-zinc-800 text-zinc-400 border border-zinc-700 hover:bg-zinc-700"
                }`}
              >
                DRY
              </button>
              <button
                data-testid="mode-live-btn"
                onClick={() => handleModeToggle("LIVE")}
                disabled={isLive || switchingMode || !modeInfo.binance_keys_configured}
                className={`h-8 px-4 rounded-sm text-xs font-medium transition-colors ${
                  isLive
                    ? "bg-red-500/20 text-red-400 border border-red-500/40"
                    : "bg-zinc-800 text-zinc-400 border border-zinc-700 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed"
                }`}
              >
                LIVE
              </button>
            </div>
          </div>
        </div>

        {/* LIVE Mode Confirmation Dialog */}
        {showLiveConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" data-testid="live-confirm-overlay">
            <div className="bg-[#121212] border border-red-500/30 rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl shadow-red-500/10" data-testid="live-confirm-dialog">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full bg-red-500/15 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-red-400" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-red-400">Switch to LIVE Trading?</h3>
                  <p className="text-[11px] text-zinc-500">This action requires your confirmation</p>
                </div>
              </div>
              <div className="space-y-2 mb-5 p-3 bg-red-500/5 rounded border border-red-500/10">
                <p className="text-xs text-zinc-300 leading-relaxed">
                  <strong className="text-red-400">Warning:</strong> Switching to LIVE mode will cause AgoBot to place{" "}
                  <strong className="text-white">real buy and sell orders</strong> on Binance using your API keys.
                </p>
                <ul className="text-[11px] text-zinc-400 space-y-1 ml-3 list-disc">
                  <li>Real USDT will be spent on trades</li>
                  <li>Profits and losses will be real</li>
                  <li>Safety limits (daily loss, drawdown) still apply</li>
                  <li>You can switch back to DRY mode at any time</li>
                </ul>
              </div>
              <div className="flex gap-3">
                <button
                  data-testid="live-confirm-cancel"
                  onClick={() => setShowLiveConfirm(false)}
                  className="flex-1 h-9 rounded-sm border border-zinc-700 text-zinc-400 text-xs font-medium hover:bg-zinc-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  data-testid="live-confirm-proceed"
                  onClick={() => switchMode("LIVE")}
                  disabled={switchingMode}
                  className="flex-1 h-9 rounded-sm bg-red-500 text-white text-xs font-bold hover:bg-red-600 disabled:opacity-50 transition-colors shadow-[0_0_20px_rgba(239,68,68,0.3)]"
                >
                  {switchingMode ? "Switching..." : "Confirm — Go LIVE"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Short Selling Toggle */}
        <div
          data-testid="short-toggle-section"
          className={`relative overflow-hidden rounded-lg border p-5 ${
            config?.allow_short
              ? "bg-orange-500/5 border-orange-500/20"
              : "bg-zinc-800/50 border-white/5"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${config?.allow_short ? "bg-orange-500/15" : "bg-zinc-700/50"}`}>
                <span className="text-sm font-bold" style={{ fontFamily: "monospace" }}>{config?.allow_short ? "S" : "L"}</span>
              </div>
              <div>
                <div className="text-sm font-semibold flex items-center gap-2">
                  Short Selling
                  <span
                    data-testid="short-badge"
                    className={`text-[10px] px-2 py-0.5 rounded-full font-bold tracking-wider ${
                      config?.allow_short
                        ? "bg-orange-500/20 text-orange-400 border border-orange-500/30"
                        : "bg-zinc-700/50 text-zinc-500 border border-zinc-600"
                    }`}
                  >
                    {config?.allow_short ? "ENABLED" : "LONG ONLY"}
                  </span>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {config?.allow_short
                    ? "Bot will open SHORT positions in downtrends. Higher risk, profits in both directions."
                    : "Bot only opens LONG positions. Safer — profits when market goes up."}
                </p>
              </div>
            </div>
            <button
              data-testid="short-toggle-btn"
              onClick={() => handleChange("allow_short", !config?.allow_short)}
              className={`relative w-12 h-6 rounded-full transition-colors ${
                config?.allow_short ? "bg-orange-500" : "bg-zinc-700"
              }`}
            >
              <span
                className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                  config?.allow_short ? "translate-x-6" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>
          {config?.allow_short && (
            <div className="mt-3 p-2.5 bg-orange-500/5 rounded border border-orange-500/10 flex items-start gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-orange-400 mt-0.5 flex-shrink-0" />
              <p className="text-[10px] text-zinc-400 leading-relaxed">
                Short selling has <strong className="text-orange-300">unlimited loss potential</strong> — price can rise indefinitely. 
                Safety limits (SL, daily loss cap) still apply. Save config to activate.
              </p>
            </div>
          )}
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

        {/* Smart Filters Section */}
        <div className="bg-[#121212] border border-white/5 rounded-lg p-6" data-testid="smart-filters-config">
          <div className="flex items-center gap-2 mb-5">
            <Shield className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold">Smart Filters</h3>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-medium">Phase 1</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            <InputField label="Max Trades / Hour" name="max_trades_per_hour" value={config?.max_trades_per_hour || 2} onChange={handleChange} step={1} min={1} max={20} description="Prevent overtrading per hour" />
            <InputField label="Max Trades / Day" name="max_trades_per_day" value={config?.max_trades_per_day || 8} onChange={handleChange} step={1} min={1} max={50} description="Daily trade cap" />
            <InputField label="Min Risk:Reward" name="min_risk_reward_ratio" value={config?.min_risk_reward_ratio || 2.5} onChange={handleChange} step={0.1} min={1} max={10} description="Minimum R:R ratio to enter" />
            <InputField label="Loss Cooldown (scans)" name="cooldown_after_loss_scans" value={config?.cooldown_after_loss_scans || 6} onChange={handleChange} step={1} min={0} max={100} description="Wait N scans after a loss" />
            <InputField label="Min Confidence Score" name="min_confidence_score" value={config?.min_confidence_score || 0.6} onChange={handleChange} step={0.05} min={0.1} max={1} description="Composite score threshold (0-1)" />
            <InputField label="Max Spread (%)" name="spread_max_percent" value={config?.spread_max_percent || 0.15} onChange={handleChange} step={0.01} min={0.01} max={1} description="Reject trades with high spread" />
            <InputField label="Min 24h Volume (USDT)" name="min_24h_volume_usdt" value={config?.min_24h_volume_usdt || 1000000} onChange={handleChange} step={100000} min={0} description="Minimum liquidity requirement" />
            <InputField label="Max Slippage (%)" name="max_slippage_percent" value={config?.max_slippage_percent || 0.1} onChange={handleChange} step={0.01} min={0.01} max={1} description="Reject if estimated slippage too high" />
            <InputField label="ML Min Win Prob" name="ml_min_win_probability" value={config?.ml_min_win_probability || 0.55} onChange={handleChange} step={0.05} min={0.3} max={0.95} description="ML model gate threshold (Phase 2)" />
            <div className="flex items-center justify-between bg-[#0A0A0A] border border-[#27272A] rounded-sm px-3 py-2.5">
              <div>
                <label className="overline block text-[10px]">Trend Alignment</label>
                <p className="text-[10px] text-zinc-600 mt-0.5">Require multi-TF trend match</p>
              </div>
              <button
                data-testid="trend-alignment-toggle"
                onClick={() => handleChange("require_trend_alignment", !config?.require_trend_alignment)}
                className={`relative w-10 h-5 rounded-full transition-colors ${config?.require_trend_alignment ? "bg-cyan-500" : "bg-zinc-700"}`}
              >
                <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${config?.require_trend_alignment ? "translate-x-5" : "translate-x-0.5"}`} />
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
