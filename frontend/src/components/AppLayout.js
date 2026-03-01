import { useState, useCallback } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  History,
  Settings,
  LogOut,
  TrendingUp,
  Menu,
  X,
  Trophy,
  FlaskConical,
} from "lucide-react";

const navItems = [
  { path: "/", icon: LayoutDashboard, label: "Dashboard" },
  { path: "/trades", icon: History, label: "Trade History" },
  { path: "/leaderboard", icon: Trophy, label: "Leaderboard" },
  { path: "/backtester", icon: FlaskConical, label: "Backtester" },
  { path: "/config", icon: Settings, label: "Configuration" },
];

export const Sidebar = ({ user, onLogout }) => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();

  const handleLogout = useCallback(() => {
    onLogout();
    navigate("/login");
  }, [onLogout, navigate]);

  return (
    <>
      {/* Mobile toggle */}
      <button
        data-testid="sidebar-mobile-toggle"
        onClick={() => setCollapsed(!collapsed)}
        className="lg:hidden fixed top-4 left-4 z-50 w-9 h-9 rounded-sm bg-[#121212] border border-[#27272A] flex items-center justify-center text-zinc-400 hover:text-white transition-colors"
      >
        {collapsed ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
      </button>

      {/* Overlay */}
      {collapsed && (
        <div
          className="lg:hidden fixed inset-0 bg-black/60 z-40"
          onClick={() => setCollapsed(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        data-testid="app-sidebar"
        className={`fixed top-0 left-0 h-screen w-[220px] bg-[#0A0A0A] border-r border-white/5 z-40 flex flex-col transition-transform duration-200 ${
          collapsed ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
      >
        {/* Logo */}
        <div className="h-16 flex items-center gap-3 px-5 border-b border-white/5">
          <div className="w-8 h-8 rounded-sm bg-blue-500 flex items-center justify-center flex-shrink-0">
            <TrendingUp className="w-4 h-4 text-white" />
          </div>
          <span className="text-base font-bold tracking-tight">AgoBot</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-3 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              onClick={() => setCollapsed(false)}
              data-testid={`nav-${item.label.toLowerCase().replace(/\s/g, "-")}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 h-9 rounded-sm text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-blue-500/10 text-blue-400"
                    : "text-zinc-500 hover:text-zinc-200 hover:bg-white/5"
                }`
              }
            >
              <item.icon className="w-4 h-4 flex-shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div className="p-3 border-t border-white/5">
          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-7 h-7 rounded-full bg-[#1A1A1A] border border-[#27272A] flex items-center justify-center text-xs font-bold text-zinc-400">
              {user?.name?.[0]?.toUpperCase() || "U"}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-zinc-300 truncate">
                {user?.name || "User"}
              </div>
              <div className="text-[10px] text-zinc-600 truncate">
                {user?.email}
              </div>
            </div>
            <button
              data-testid="logout-button"
              onClick={handleLogout}
              className="text-zinc-600 hover:text-red-400 transition-colors"
              title="Sign out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
};

export const AppLayout = ({ children, user, onLogout }) => {
  return (
    <div className="min-h-screen bg-[#0A0A0A]">
      <Sidebar user={user} onLogout={onLogout} />
      <main className="lg:pl-[220px] min-h-screen">{children}</main>
    </div>
  );
};
