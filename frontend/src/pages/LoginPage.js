import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/App";
import { toast } from "sonner";
import { Eye, EyeOff, TrendingUp, Lock, Mail, User } from "lucide-react";

export default function LoginPage({ onLogin }) {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const endpoint = isRegister ? "/auth/register" : "/auth/login";
      const payload = isRegister
        ? { email, password, name }
        : { email, password };
      const res = await api.post(endpoint, payload);
      onLogin(res.data.user, res.data.access_token);
      toast.success(isRegister ? "Account created" : "Welcome back");
      navigate("/");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" data-testid="login-page">
      {/* Left: Visual Panel */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden items-center justify-center">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1768330005068-e99a3204e8fe?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxOTB8MHwxfHNlYXJjaHw0fHxjeWJlcnB1bmslMjBhYnN0cmFjdCUyMGRpZ2l0YWwlMjBmaW5hbmNpYWwlMjBuZXR3b3JrJTIwZGFyayUyMGJhY2tncm91bmR8ZW58MHx8fHwxNzcyMzUxMzEyfDA&ixlib=rb-4.1.0&q=85')`,
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/50 to-black/80" />
        <div className="relative z-10 p-16 max-w-lg">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-sm bg-blue-500 flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-white" />
            </div>
            <span className="text-2xl font-bold tracking-tight text-white">
              AgoBot
            </span>
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-white mb-4">
            Automated Crypto Trading
          </h1>
          <p className="text-lg text-zinc-400 leading-relaxed">
            Smart order execution with technical analysis. RSI, MACD, Bollinger
            Bands, and ATR-based position management with trailing stops.
          </p>
          <div className="mt-10 flex gap-6">
            <div>
              <div className="font-mono text-2xl font-bold text-[#00F090]">
                24/7
              </div>
              <div className="overline mt-1">Monitoring</div>
            </div>
            <div className="w-px bg-white/10" />
            <div>
              <div className="font-mono text-2xl font-bold text-blue-400">
                SPOT
              </div>
              <div className="overline mt-1">Trading</div>
            </div>
            <div className="w-px bg-white/10" />
            <div>
              <div className="font-mono text-2xl font-bold text-purple-400">
                DRY
              </div>
              <div className="overline mt-1">Mode</div>
            </div>
          </div>
        </div>
      </div>

      {/* Right: Form Panel */}
      <div className="flex-1 flex items-center justify-center p-8 bg-[#0A0A0A]">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center gap-3 mb-10">
            <div className="w-9 h-9 rounded-sm bg-blue-500 flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-white" />
            </div>
            <span className="text-xl font-bold tracking-tight">AgoBot</span>
          </div>

          <h2 className="text-3xl font-bold tracking-tight mb-2">
            {isRegister ? "Create account" : "Welcome back"}
          </h2>
          <p className="text-zinc-500 mb-10">
            {isRegister
              ? "Set up your trading dashboard"
              : "Sign in to your trading dashboard"}
          </p>

          <form onSubmit={handleSubmit} className="space-y-5">
            {isRegister && (
              <div>
                <label className="overline block mb-2">Name</label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                  <input
                    data-testid="register-name-input"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Your name"
                    className="w-full h-11 pl-10 pr-4 rounded-sm bg-[#121212] border border-[#27272A] text-white placeholder:text-zinc-600 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-colors"
                  />
                </div>
              </div>
            )}

            <div>
              <label className="overline block mb-2">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input
                  data-testid="login-email-input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="trader@example.com"
                  required
                  className="w-full h-11 pl-10 pr-4 rounded-sm bg-[#121212] border border-[#27272A] text-white placeholder:text-zinc-600 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="overline block mb-2">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input
                  data-testid="login-password-input"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  required
                  minLength={6}
                  className="w-full h-11 pl-10 pr-11 rounded-sm bg-[#121212] border border-[#27272A] text-white placeholder:text-zinc-600 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
                  data-testid="toggle-password-visibility"
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            <button
              data-testid="login-submit-button"
              type="submit"
              disabled={loading}
              className="w-full h-11 rounded-sm bg-blue-500 text-white font-medium text-sm hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_0_20px_rgba(59,130,246,0.3)] transition-colors"
            >
              {loading
                ? "Processing..."
                : isRegister
                  ? "Create Account"
                  : "Sign In"}
            </button>
          </form>

          <div className="mt-8 text-center">
            <button
              data-testid="toggle-auth-mode"
              onClick={() => setIsRegister(!isRegister)}
              className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              {isRegister
                ? "Already have an account? Sign in"
                : "Need an account? Create one"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
