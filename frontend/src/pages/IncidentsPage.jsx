import { useEffect, useState } from "react";
import { useApp } from "../App";
import { Link } from "react-router-dom";
import { fetchIncidents } from "../api/aegis";
import { AlertTriangle, ArrowRight, Loader2 } from "lucide-react";

export default function IncidentsPage() {
  const { selected } = useApp();
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    if (!selected) {
      setIncidents([]);
      return;
    }

    setLoading(true);
    fetchIncidents(selected.id, selected.api_key)
      .then((data) => setIncidents(data?.incidents || []))
      .catch(() => setIncidents([]))
      .finally(() => setLoading(false));
  }, [selected?.id]);

  const filtered =
    filter === "all"
      ? incidents
      : incidents.filter((i) => i.status === filter);

  const counts = {
    all: incidents.length,
    open: incidents.filter((i) => i.status === "open").length,
    investigated: incidents.filter((i) =>
      ["investigating", "investigated"].includes(i.status),
    ).length,
    resolved: incidents.filter((i) => i.status === "resolved").length,
  };

  if (!selected) {
    return (
      <div className="py-20 text-center animate-fade-in">
        <p className="text-sm text-ink/50">
          Select an application to view incidents.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-oxblood">
          Investigation
        </p>
        <h2 className="mt-2 text-xl font-semibold">Incidents</h2>
        <p className="mt-1 text-sm text-ink/55">
          Grouped errors and their investigation status.
        </p>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 overflow-x-auto">
        {[
          { key: "all", label: "All" },
          { key: "open", label: "Open" },
          { key: "investigated", label: "Investigated" },
          { key: "resolved", label: "Resolved" },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`flex items-center gap-1.5 whitespace-nowrap rounded-lg px-4 py-2 text-sm font-medium transition ${
              filter === key
                ? "bg-oxblood text-ivory"
                : "bg-surface/60 text-ink/60 hover:text-ink"
            }`}
          >
            {label}
            <span
              className={`rounded-full px-2 py-0.5 text-xs ${
                filter === key
                  ? "bg-ivory/20 text-ivory"
                  : "bg-ink/8 text-ink/50"
              }`}
            >
              {counts[key]}
            </span>
          </button>
        ))}
      </div>

      {/* Incident list */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={24} className="animate-spin text-oxblood" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-ink/8 bg-white/30 px-6 py-16 text-center">
          <AlertTriangle
            size={28}
            className="mx-auto text-ink/25"
          />
          <p className="mt-4 text-sm text-ink/50">
            {incidents.length === 0
              ? "No incidents found. Upload some logs to get started."
              : "No incidents match this filter."}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((incident) => (
            <Link
              key={incident.id}
              to={`/incidents/${incident.id}`}
              className="group flex items-center gap-4 rounded-xl border border-ink/8 bg-white/30 p-4 transition hover:border-ink/15 hover:bg-white/50"
            >
              <div
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                  incident.severity === "CRITICAL" ||
                  incident.severity === "FATAL"
                    ? "bg-danger/10"
                    : incident.severity === "ERROR"
                      ? "bg-oxblood/10"
                      : "bg-warning/10"
                }`}
              >
                <AlertTriangle
                  size={18}
                  className={
                    incident.severity === "CRITICAL" ||
                    incident.severity === "FATAL"
                      ? "text-danger"
                      : incident.severity === "ERROR"
                        ? "text-oxblood"
                        : "text-warning"
                  }
                />
              </div>

              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-sm group-hover:text-oxblood transition">
                  {incident.title}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink/50">
                  <span>{incident.service}</span>
                  <span>·</span>
                  <span>{incident.event_count} events</span>
                  <span>·</span>
                  <span>
                    {new Date(incident.last_seen).toLocaleDateString()}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <span
                  className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase status-${incident.status}`}
                >
                  {incident.status}
                </span>
                {incident.has_report && (
                  <span className="rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success">
                    Report
                  </span>
                )}
                <ArrowRight
                  size={14}
                  className="text-ink/20 transition group-hover:text-ink/40"
                />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
