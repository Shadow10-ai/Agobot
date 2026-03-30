import { useState, useEffect, useCallback } from "react";
import { api } from "@/App";
import { AppLayout } from "@/components/AppLayout";
import { Brain, Database, BarChart3, RefreshCw, Zap, TrendingUp, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const StatBox = ({ label, value, sub, color = "text-white" }) => (
  <div className="bg-[#0A0A0A] border border-white/5 rounded-lg p-4">
    <p className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</p>
    <p className={`text-xl font-bold font-mono mt-1 ${color}`}>{value}</p>
    {sub && <p className="text-[10px] text-zinc-600 mt-1">{sub}</p>}
  </div>
);

const ProgressBar = ({ value, max, label, color = "bg-blue-500" }) => {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-zinc-500">{label}</span>
        <span className="text-[10px] font-mono text-zinc-400">{value}/{max}</span>
      </div>
      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
};

export default function MLPage({ user, onLogout }) {
  const [mlStatus, setMlStatus] = useState(null);
  const [datasetStats, setDatasetStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);
  const [seeding, setSeeding] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [mlRes, dsRes] = await Promise.all([
        api.get("/ml/status"),
        api.get("/dataset/stats")
      ]);
      setMlStatus(mlRes.data);
      setDatasetStats(dsRes.data);
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

  const handleTrain = async () => {
    setTraining(true);
    try {
      const res = await api.post("/ml/train");
      toast.success(res.data.message);
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Training failed");
    } finally {
      setTraining(false);
    }
  };

  const handleSeed = async () => {
    setSeeding(true);
    try {
      const res = await api.post("/ml/seed");
      toast.success(`Seeded ${res.data.seeded} entries. Total: ${res.data.total_labeled}`);
      fetchData();
    } catch (err) {
      toast.error("Seeding failed");
    } finally {
      setSeeding(false);
    }
  };

  if (loading) {
    return (
      <AppLayout user={user} onLogout={onLogout}>
        <div className="flex items-center justify-center min-h-screen">
          <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
        </div>
      </AppLayout>
    );
  }

  const ml = mlStatus || {};
  const ds = datasetStats || {};
  const metrics = ml.metrics || {};
  const training_data = ml.training_data || {};
  const isActive = ml.status === "ACTIVE";

  return (
    <AppLayout user={user} onLogout={onLogout}>
      <div className="p-5 lg:p-8 space-y-6" data-testid="ml-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">ML Intelligence</h1>
            <p className="text-sm text-zinc-500 mt-1">Machine learning signal filter & training dashboard</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              data-testid="seed-btn"
              onClick={handleSeed}
              disabled={seeding}
              className="h-8 px-3 rounded-sm border border-white/10 text-zinc-400 text-xs font-medium hover:bg-white/5 transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              <Database className="w-3 h-3" /> {seeding ? "Seeding..." : "Seed Data"}
            </button>
            <button
              data-testid="train-btn"
              onClick={handleTrain}
              disabled={training}
              className="h-8 px-3 rounded-sm bg-purple-500 text-white text-xs font-medium hover:bg-purple-600 disabled:opacity-50 shadow-[0_0_15px_rgba(168,85,247,0.3)] transition-colors flex items-center gap-1.5"
            >
              <Brain className="w-3 h-3" /> {training ? "Training..." : "Train Model"}
            </button>
            <button
              data-testid="refresh-ml"
              onClick={fetchData}
              className="h-8 px-3 rounded-sm border border-white/10 text-zinc-400 text-xs hover:bg-white/5 transition-colors"
            >
              <RefreshCw className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Model Status Banner */}
        <div
          data-testid="ml-status-banner"
          className={`relative overflow-hidden rounded-lg border p-5 ${
            isActive
              ? "bg-purple-500/5 border-purple-500/20"
              : "bg-yellow-500/5 border-yellow-500/20"
          }`}
        >
          <div className="flex items-center gap-3">
            {isActive ? (
              <Zap className="w-5 h-5 text-purple-400" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-yellow-400" />
            )}
            <div>
              <div className="text-sm font-semibold flex items-center gap-2">
                ML Model
                <span
                  data-testid="ml-status-badge"
                  className={`text-[10px] px-2 py-0.5 rounded-full font-bold tracking-wider ${
                    isActive
                      ? "bg-purple-500/20 text-purple-400 border border-purple-500/30"
                      : ml.status === "TRAINING"
                      ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                      : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
                  }`}
                >
                  {ml.status}
                </span>
                {ml.version > 0 && (
                  <span className="text-[10px] text-zinc-600">v{ml.version}</span>
                )}
              </div>
              <p className="text-[11px] text-zinc-500 mt-0.5">
                {isActive
                  ? `Trained on ${training_data.total_samples} samples. Acts as Gate 12 — rejecting low-probability trades.`
                  : `Collecting data. Need ${ml.min_samples_required} labeled outcomes to activate. Currently: ${training_data.total_samples || 0}.`}
              </p>
            </div>
          </div>
          {!isActive && (
            <div className="mt-3">
              <ProgressBar
                value={training_data.total_samples || ds.outcomes?.wins + ds.outcomes?.losses || 0}
                max={ml.min_samples_required || 30}
                label="Training data progress"
                color="bg-yellow-500"
              />
            </div>
          )}
        </div>

        {/* Model Metrics */}
        {isActive && (
          <div>
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <BarChart3 className="w-3.5 h-3.5" /> Model Performance
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="ml-metrics">
              <StatBox label="Accuracy" value={`${(metrics.accuracy * 100).toFixed(1)}%`} color="text-purple-400" />
              <StatBox label="Precision" value={`${(metrics.precision * 100).toFixed(1)}%`} sub="% of predicted wins that won" color="text-blue-400" />
              <StatBox label="Recall" value={`${(metrics.recall * 100).toFixed(1)}%`} sub="% of actual wins caught" color="text-cyan-400" />
              <StatBox label="F1 Score" value={`${(metrics.f1 * 100).toFixed(1)}%`} sub="Harmonic mean" color="text-emerald-400" />
              <StatBox label="CV Score" value={`${(metrics.cv_score * 100).toFixed(1)}%`} sub="Cross-validation accuracy" color="text-orange-400" />
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Dataset Stats */}
          <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="dataset-stats">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Database className="w-3.5 h-3.5" /> Training Dataset
            </h3>
            <div className="grid grid-cols-2 gap-3 mb-4">
              <StatBox label="Total Signals" value={ds.total_signals || 0} />
              <StatBox label="Trades Taken" value={ds.trades_taken || 0} color="text-blue-400" />
              <StatBox label="Trades Rejected" value={ds.trades_rejected || 0} color="text-zinc-400" />
              <StatBox
                label="Win Rate"
                value={ds.win_rate ? `${ds.win_rate}%` : "N/A"}
                color={ds.win_rate > 50 ? "text-emerald-400" : "text-red-400"}
              />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <StatBox label="Wins" value={ds.outcomes?.wins || 0} color="text-emerald-400" />
              <StatBox label="Losses" value={ds.outcomes?.losses || 0} color="text-red-400" />
              <StatBox label="Pending" value={ds.outcomes?.pending || 0} color="text-yellow-400" />
            </div>
            <div className="mt-4 pt-4 border-t border-white/5">
              <div className="flex justify-between text-[10px] mb-1">
                <span className="text-zinc-500">Avg Confidence (Taken)</span>
                <span className="text-emerald-400 font-mono">{ds.avg_confidence_taken || 0}</span>
              </div>
              <div className="flex justify-between text-[10px]">
                <span className="text-zinc-500">Avg Confidence (Rejected)</span>
                <span className="text-red-400 font-mono">{ds.avg_confidence_rejected || 0}</span>
              </div>
            </div>
          </div>

          {/* Feature Importance & Rejections */}
          <div className="space-y-6">
            {/* Feature Importance */}
            {isActive && ml.feature_importance && Object.keys(ml.feature_importance).length > 0 && (
              <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="feature-importance">
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <TrendingUp className="w-3.5 h-3.5" /> Feature Importance
                </h3>
                <div className="space-y-2">
                  {Object.entries(ml.feature_importance).map(([feat, imp]) => {
                    const maxImp = Math.max(...Object.values(ml.feature_importance));
                    const pct = maxImp > 0 ? (imp / maxImp) * 100 : 0;
                    return (
                      <div key={feat}>
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-[10px] text-zinc-400 font-mono">{feat}</span>
                          <span className="text-[10px] text-purple-400 font-mono">{imp}</span>
                        </div>
                        <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
                          <div className="h-full bg-purple-500/60 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Rejection Reasons */}
            {ds.rejection_reasons && Object.keys(ds.rejection_reasons).length > 0 && (
              <div className="bg-[#121212] border border-white/5 rounded-lg p-5" data-testid="rejection-reasons">
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-4">
                  Top Rejection Reasons (last 100)
                </h3>
                <div className="space-y-2">
                  {Object.entries(ds.rejection_reasons).map(([reason, count]) => (
                    <div key={reason} className="flex items-center justify-between">
                      <span className="text-xs text-zinc-400">{reason}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-24 h-1 bg-zinc-800 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-red-500/50 rounded-full"
                            style={{ width: `${Math.min(100, (count / 100) * 100)}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-mono text-red-400 w-6 text-right">{count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Reinforcement Info */}
        <div className="bg-[#121212] border border-white/5 rounded-lg p-5">
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">Reinforcement Loop</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div>
              <span className="text-zinc-600">Retrain Interval</span>
              <p className="font-mono text-white mt-0.5">Every {ml.retrain_interval || 5} trades</p>
            </div>
            <div>
              <span className="text-zinc-600">Trades Since Retrain</span>
              <p className="font-mono text-white mt-0.5">{ml.trades_since_retrain || 0}</p>
            </div>
            <div>
              <span className="text-zinc-600">Training Samples</span>
              <p className="font-mono text-white mt-0.5">{training_data.total_samples || 0} ({training_data.wins || 0}W / {training_data.losses || 0}L)</p>
            </div>
            <div>
              <span className="text-zinc-600">Last Trained</span>
              <p className="font-mono text-white mt-0.5">{ml.last_trained ? new Date(ml.last_trained).toLocaleString() : "Never"}</p>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
