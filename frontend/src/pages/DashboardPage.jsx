import { useEffect, useState } from "react";
import { useApp } from "../App";
import { Link } from "react-router-dom";
import { fetchStats, fetchIncidents } from "../api/aegis";
import {
  AlertTriangle,
  CheckCircle2,
  Search,
  Activity,
  ArrowRight,
} from "lucide-react";

function StatCard({ label, value, icon: Icon, color = "ink" }) {
  return (
    <div className="rounded-xl border border-ink/8 bg-white/40 p-5 transition hover:border-ink/15">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-widest text-ink/45">
          {label}
        </p>
        <Icon size={16} className={`text-${color}`} />
      </div>
      <p className="mt-3 text-3xl font-bold tracking-tight">{value}</p>
    </div>
  );
}

function IncidentRow({ incident, applicationName }) {
  const statusClass = `status-${incident.status}`;

  return (
    <Link
      to={`/incidents/${incident.id}`}
      className="flex items-center gap-4 rounded-xl border border-ink/8 bg-white/30 p-4 transition hover:border-ink/15 hover:bg-white/50"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-oxblood/10">
        <AlertTriangle size={16} className="text-oxblood" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">{incident.title}</p>
        <p className="mt-0.5 text-xs text-ink/50">
          {applicationName ? `${applicationName} · ` : ""}{incident.service} · {incident.event_count} events
        </p>
      </div>
      <div className="flex items-center gap-2">
        <span
          className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase ${statusClass}`}
        >
          {incident.status}
        </span>
        <ArrowRight size={14} className="text-ink/30" />
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const { selected, applications, allApplicationsSelected } = useApp();
  const [stats, setStats] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (allApplicationsSelected) {
      setLoading(true);
      Promise.all(
        applications.map(async (app) => {
          const [appStats, appIncidents] = await Promise.all([
            fetchStats(app.id).catch(() => null),
            fetchIncidents(app.id).catch(() => ({ incidents: [] })),
          ]);
          return { appStats, incidents: appIncidents?.incidents || [] };
        }),
      )
        .then((results) => {
          const totals = {
            total_events: 0,
            total_incidents: 0,
            open_incidents: 0,
            investigated_incidents: 0,
            resolved_incidents: 0,
          };
          for (const result of results) {
            for (const key of Object.keys(totals)) {
              totals[key] += Number(result.appStats?.[key] || 0);
            }
          }
          setStats(totals);
          setIncidents(
            results.flatMap((result) => result.incidents)
              .sort((a, b) => new Date(b.last_seen) - new Date(a.last_seen)),
          );
        })
        .finally(() => setLoading(false));
      return;
    }

    if (!selected) {
      setStats(null);
      setIncidents([]);
      return;
    }

    setLoading(true);
    Promise.all([
      fetchStats(selected.id).catch(() => null),
      fetchIncidents(selected.id).catch(() => ({ incidents: [] })),
    ])
      .then(([appStats, appIncidents]) => {
        setStats(appStats);
        setIncidents(appIncidents?.incidents || []);
      })
      .finally(() => setLoading(false));
  }, [selected?.id, allApplicationsSelected, applications]);

  if (!selected && !allApplicationsSelected) {
    const hasApps = applications.length > 0;
    return (
      <div className="flex flex-col items-center justify-center py-20 animate-fade-in">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-oxblood/10">
          <Activity size={28} className="text-oxblood" />
        </div>
        <h2 className="mt-6 text-xl font-semibold">
          {hasApps ? "Choose an application" : "Welcome to AEGIS"}
        </h2>
        <p className="mt-2 max-w-md text-center text-sm text-ink/55">
          {hasApps
            ? "Select an application from the header. AEGIS will keep your selection when you refresh."
            : "Register an application to begin. Upload logs, and let AEGIS identify errors, investigate root causes, and suggest fixes."}
        </p>
        {hasApps && (
          <Link to="/applications" className="mt-5 text-sm font-semibold text-oxblood hover:underline">
            Manage applications →
          </Link>
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton h-24 rounded-xl" />
          ))}
        </div>
        <div className="skeleton h-48 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Section header */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-oxblood">
          Overview
        </p>
        <h2 className="mt-2 text-xl font-semibold">
          {allApplicationsSelected ? "All applications" : selected.name}
        </h2>
        <p className="mt-1 text-sm text-ink/55">
          {allApplicationsSelected
            ? `Aggregated diagnostics across ${applications.length} applications.`
            : selected.description || "Application diagnostics at a glance."}
        </p>
      </div>

      {/* Stats grid */}
      {stats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Total events"
            value={stats.total_events}
            icon={Activity}
          />
          <StatCard
            label="Open incidents"
            value={stats.open_incidents}
            icon={AlertTriangle}
            color="oxblood"
          />
          <StatCard
            label="Investigated"
            value={stats.investigated_incidents}
            icon={Search}
            color="warning"
          />
          <StatCard
            label="Resolved"
            value={stats.resolved_incidents}
            icon={CheckCircle2}
            color="success"
          />
        </div>
      )}

      {/* Quick actions */}
      <div className="flex gap-3">
        <Link
          to="/ingest"
          className="rounded-lg bg-oxblood px-5 py-2.5 text-sm font-semibold text-ivory transition hover:bg-oxblood-dark"
        >
          Upload logs
        </Link>
        <Link
          to="/incidents"
          className="rounded-lg border border-ink/12 px-5 py-2.5 text-sm font-medium transition hover:bg-ink/5"
        >
          View incidents
        </Link>
      </div>

      {/* Recent incidents */}
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-widest text-ink/45">
          Recent incidents
        </h3>
        {incidents.length === 0 ? (
          <div className="mt-4 rounded-xl border border-ink/8 bg-white/30 px-6 py-12 text-center">
            <p className="text-sm text-ink/50">
              No incidents yet. Upload diagnostic data to get started.
            </p>
          </div>
        ) : (
          <div className="mt-4 space-y-2">
            {incidents.slice(0, 8).map((inc) => (
              <IncidentRow
                key={inc.id}
                incident={inc}
                applicationName={applications.find((app) => app.id === inc.application_id)?.name}
              />
            ))}
            {incidents.length > 8 && (
              <Link
                to="/incidents"
                className="block text-center text-sm font-medium text-oxblood hover:underline"
              >
                View all {incidents.length} incidents →
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
