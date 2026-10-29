import { NavLink, Outlet } from "react-router-dom";
import { useApp } from "../App";
import {
  Shield,
  Upload,
  AlertTriangle,
  Code2,
  ChevronDown,
} from "lucide-react";
import { useState } from "react";
import RegisterModal from "./RegisterModal";

const navItems = [
  { to: "/", label: "Dashboard", icon: Shield, end: true },
  { to: "/ingest", label: "Ingest", icon: Upload },
  { to: "/incidents", label: "Incidents", icon: AlertTriangle },
  { to: "/api-docs", label: "API", icon: Code2 },
];

export default function Layout() {
  const { applications, selectedId, setSelectedId, selected } = useApp();
  const [showRegister, setShowRegister] = useState(false);

  return (
    <div className="min-h-screen bg-ivory text-ink">
      {/* Header */}
      <header className="border-b border-ink/10 bg-ivory/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 md:px-10">
          <div className="flex items-center gap-8">
            {/* Brand */}
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-oxblood text-ivory">
                <Shield size={16} strokeWidth={2.5} />
              </div>
              <div>
                <p className="text-sm font-bold tracking-tight">AEGIS</p>
                <p className="text-[10px] uppercase tracking-[0.2em] text-ink/45">
                  Incident Intelligence
                </p>
              </div>
            </div>

            {/* Navigation */}
            <nav className="hidden items-center gap-1 md:flex">
              {navItems.map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-oxblood/10 text-oxblood"
                        : "text-ink/60 hover:bg-ink/5 hover:text-ink"
                    }`
                  }
                >
                  <Icon size={15} />
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>

          {/* App selector */}
          <div className="flex items-center gap-3">
            <div className="relative">
              <select
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                className="appearance-none rounded-lg border border-ink/12 bg-ivory pl-3 pr-8 py-2 text-sm font-medium outline-none transition focus:border-oxblood cursor-pointer"
              >
                <option value="">Select application</option>
                {applications.map((app) => (
                  <option key={app.id} value={app.id}>
                    {app.name}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-ink/40"
              />
            </div>
            <button
              onClick={() => setShowRegister(true)}
              className="rounded-lg bg-oxblood px-4 py-2 text-sm font-semibold text-ivory transition hover:bg-oxblood-dark"
            >
              + New
            </button>
          </div>
        </div>

        {/* Mobile nav */}
        <nav className="flex items-center gap-1 overflow-x-auto border-t border-ink/5 px-6 md:hidden">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-3 text-xs font-medium transition ${
                  isActive
                    ? "border-oxblood text-oxblood"
                    : "border-transparent text-ink/50 hover:text-ink"
                }`
              }
            >
              <Icon size={13} />
              {label}
            </NavLink>
          ))}
        </nav>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-7xl px-6 py-8 md:px-10">
        {!selected && (
          <div className="mb-6 rounded-xl border border-oxblood/20 bg-oxblood/5 px-5 py-4 animate-fade-in">
            <p className="text-sm font-medium text-oxblood">
              No application selected
            </p>
            <p className="mt-1 text-sm text-ink/60">
              Register or select an application to start using AEGIS.
            </p>
          </div>
        )}
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t border-ink/8 px-6 py-6 text-center">
        <p className="text-xs text-ink/40">
          AEGIS · Evidence before assumptions
        </p>
      </footer>

      {/* Register modal */}
      {showRegister && (
        <RegisterModal onClose={() => setShowRegister(false)} />
      )}
    </div>
  );
}
