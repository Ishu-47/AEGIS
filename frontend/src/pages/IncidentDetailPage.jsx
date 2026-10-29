import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  fetchIncident,
  triggerInvestigation,
  updateIncidentStatus,
} from "../api/aegis";
import {
  ArrowLeft,
  Loader2,
  Search,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Lightbulb,
  FileText,
  MapPin,
  HelpCircle,
  ChevronDown,
  ChevronRight,
} from "lucide-react";

function SeverityBadge({ severity }) {
  return (
    <span
      className={`rounded px-2.5 py-1 text-[10px] font-bold uppercase severity-${severity?.toLowerCase()}`}
    >
      {severity}
    </span>
  );
}

function StatusBadge({ status }) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-semibold capitalize status-${status}`}
    >
      {status}
    </span>
  );
}

function ConfidenceMeter({ value }) {
  const pct = Math.round(value * 100);
  const level =
    pct >= 70 ? "high" : pct >= 40 ? "medium" : "low";

  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-ink/60">Confidence</span>
        <span className="font-bold">{pct}%</span>
      </div>
      <div className="confidence-bar mt-1.5">
        <div
          className={`confidence-fill confidence-${level}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1 text-[10px] text-ink/40">
        {level === "high"
          ? "Strong evidence supports this analysis"
          : level === "medium"
            ? "Moderate evidence — some assumptions made"
            : "Limited evidence — review with caution"}
      </p>
    </div>
  );
}

function TimelineEvent({ event, index }) {
  return (
    <div className="flex gap-3 animate-slide-in" style={{ animationDelay: `${index * 40}ms` }}>
      <div className="flex flex-col items-center">
        <div
          className={`h-2.5 w-2.5 rounded-full ${
            event.severity === "ERROR" ||
            event.severity === "CRITICAL" ||
            event.severity === "FATAL"
              ? "bg-oxblood"
              : event.severity === "WARN"
                ? "bg-warning"
                : "bg-ink/20"
          }`}
        />
        <div className="w-px flex-1 bg-ink/10" />
      </div>
      <div className="pb-4 min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={event.severity} />
          <span className="text-xs font-medium text-ink/60">
            {event.service}
          </span>
          <span className="ml-auto text-[10px] text-ink/40">
            {new Date(event.timestamp).toLocaleString()}
          </span>
        </div>
        <p className="mt-1.5 break-words font-mono text-[11px] leading-5 text-ink/75">
          {event.message?.slice(0, 500)}
          {event.message?.length > 500 && "..."}
        </p>
        {event.correlation_id && (
          <p className="mt-1 text-[10px] text-ink/40">
            Correlation: {event.correlation_id}
          </p>
        )}
      </div>
    </div>
  );
}

function ReportSection({ icon: Icon, title, children }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="border-b border-ink/6 last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2.5 py-4 text-left"
      >
        <Icon size={15} className="text-oxblood" />
        <span className="flex-1 text-sm font-semibold">{title}</span>
        {open ? (
          <ChevronDown size={14} className="text-ink/40" />
        ) : (
          <ChevronRight size={14} className="text-ink/40" />
        )}
      </button>
      {open && <div className="pb-4">{children}</div>}
    </div>
  );
}

export default function IncidentDetailPage() {
  const { id } = useParams();
  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [investigating, setInvestigating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    fetchIncident(parseInt(id))
      .then(setIncident)
      .catch((err) => setError(err.response?.data?.detail || "Could not load incident."))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleInvestigate() {
    setInvestigating(true);
    setError("");

    try {
      await triggerInvestigation(parseInt(id));
      // Refresh
      const updated = await fetchIncident(parseInt(id));
      setIncident(updated);
    } catch (err) {
      setError(
        err.response?.data?.detail || "Investigation failed.",
      );
    } finally {
      setInvestigating(false);
    }
  }

  async function handleStatusChange(newStatus) {
    try {
      await updateIncidentStatus(parseInt(id), newStatus);
      const updated = await fetchIncident(parseInt(id));
      setIncident(updated);
    } catch {
      // silent
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={24} className="animate-spin text-oxblood" />
      </div>
    );
  }

  if (error && !incident) {
    return (
      <div className="py-20 text-center">
        <p className="text-sm text-danger">{error}</p>
        <Link
          to="/incidents"
          className="mt-4 inline-block text-sm font-medium text-oxblood hover:underline"
        >
          ← Back to incidents
        </Link>
      </div>
    );
  }

  if (!incident) return null;

  const report = incident.report;

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            to="/incidents"
            className="mb-3 flex items-center gap-1 text-xs font-medium text-ink/50 transition hover:text-ink"
          >
            <ArrowLeft size={12} />
            All incidents
          </Link>
          <div className="flex items-center gap-3">
            <SeverityBadge severity={incident.severity} />
            <StatusBadge status={incident.status} />
          </div>
          <h1 className="mt-3 text-xl font-bold tracking-tight md:text-2xl">
            {incident.title}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink/50">
            <span className="flex items-center gap-1">
              <Clock size={11} />
              First seen: {new Date(incident.first_seen).toLocaleString()}
            </span>
            <span>·</span>
            <span>
              Last seen: {new Date(incident.last_seen).toLocaleString()}
            </span>
            <span>·</span>
            <span>{incident.event_count} events</span>
            <span>·</span>
            <span>{incident.service}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {incident.status !== "resolved" && (
            <button
              onClick={() => handleStatusChange("resolved")}
              className="flex items-center gap-1.5 rounded-lg border border-success/20 px-4 py-2 text-sm font-medium text-success transition hover:bg-success/5"
            >
              <CheckCircle2 size={14} />
              Resolve
            </button>
          )}
          <button
            onClick={handleInvestigate}
            disabled={investigating}
            className="flex items-center gap-2 rounded-lg bg-oxblood px-5 py-2.5 text-sm font-semibold text-ivory transition hover:bg-oxblood-dark disabled:opacity-50"
          >
            {investigating ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Investigating...
              </>
            ) : (
              <>
                <Search size={14} />
                {report ? "Re-investigate" : "Investigate"}
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-danger/20 bg-danger/5 p-4 text-sm text-danger">
          {error}
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
        {/* Investigation Report */}
        <div>
          {report ? (
            <div className="rounded-2xl border border-ink/8 bg-white/40 p-6 animate-fade-in">
              <div className="flex items-center gap-2 border-b border-ink/8 pb-4">
                <FileText size={16} className="text-oxblood" />
                <h2 className="font-semibold">Investigation Report</h2>
              </div>

              <div className="mt-4 space-y-0">
                {/* Confidence */}
                <div className="pb-4 border-b border-ink/6">
                  <ConfidenceMeter value={report.confidence} />
                </div>

                {/* Observed Error */}
                <ReportSection icon={AlertTriangle} title="Observed Error">
                  <p className="text-sm leading-relaxed text-ink/75">
                    {report.observed_error}
                  </p>
                  <p className="mt-2 text-xs text-ink/50">
                    Affected service:{" "}
                    <span className="font-semibold">
                      {report.affected_service}
                    </span>
                  </p>
                </ReportSection>

                {/* Root Cause */}
                <ReportSection icon={Search} title="Probable Root Cause">
                  <div className="rounded-lg bg-oxblood/5 border border-oxblood/10 p-4">
                    <p className="text-sm leading-relaxed font-medium">
                      {report.probable_root_cause}
                    </p>
                  </div>
                </ReportSection>

                {/* Evidence */}
                {report.supporting_evidence?.length > 0 && (
                  <ReportSection icon={FileText} title="Supporting Evidence">
                    <ul className="space-y-2">
                      {report.supporting_evidence.map((item, i) => (
                        <li
                          key={i}
                          className="flex gap-2 text-sm text-ink/70"
                        >
                          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-oxblood/40" />
                          <span className="font-mono text-xs leading-5">
                            {item}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </ReportSection>
                )}

                {/* Remediation */}
                {report.remediation_steps?.length > 0 && (
                  <ReportSection icon={Lightbulb} title="Recommended Fixes">
                    <ol className="space-y-2">
                      {report.remediation_steps.map((step, i) => (
                        <li
                          key={i}
                          className="flex gap-3 text-sm text-ink/75"
                        >
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-oxblood/10 text-[10px] font-bold text-oxblood">
                            {i + 1}
                          </span>
                          {step}
                        </li>
                      ))}
                    </ol>
                  </ReportSection>
                )}

                {/* Stack Locations */}
                {report.stack_trace_locations?.length > 0 && (
                  <ReportSection icon={MapPin} title="Source Code Locations">
                    <div className="space-y-1">
                      {report.stack_trace_locations.map((loc, i) => (
                        <p
                          key={i}
                          className="rounded bg-ink/5 px-3 py-1.5 font-mono text-xs text-ink/70"
                        >
                          {loc}
                        </p>
                      ))}
                    </div>
                  </ReportSection>
                )}

                {/* Uncertainty */}
                {report.uncertainty_notes && (
                  <ReportSection icon={HelpCircle} title="Uncertainty & Caveats">
                    <p className="text-sm italic text-ink/55">
                      {report.uncertainty_notes}
                    </p>
                  </ReportSection>
                )}
              </div>

              <p className="mt-4 border-t border-ink/6 pt-3 text-[10px] text-ink/35">
                Report generated{" "}
                {new Date(report.created_at).toLocaleString()}
              </p>
            </div>
          ) : (
            <div className="rounded-2xl border border-ink/8 bg-white/30 px-6 py-16 text-center">
              <Search size={32} className="mx-auto text-ink/20" />
              <p className="mt-4 text-sm font-medium text-ink/50">
                No investigation report yet
              </p>
              <p className="mt-1 text-xs text-ink/40">
                Click "Investigate" to analyze this incident with AI.
              </p>
            </div>
          )}
        </div>

        {/* Event Timeline */}
        <div className="rounded-2xl border border-ink/8 bg-white/40 p-6">
          <div className="flex items-center justify-between border-b border-ink/8 pb-4">
            <h2 className="font-semibold flex items-center gap-2">
              <Clock size={15} className="text-oxblood" />
              Event Timeline
            </h2>
            <span className="rounded-full bg-surface px-2.5 py-0.5 text-xs font-medium text-ink/60">
              {incident.events?.length || 0} events
            </span>
          </div>
          <div className="mt-4 max-h-[600px] overflow-y-auto pr-1">
            {incident.events?.length > 0 ? (
              incident.events.map((event, i) => (
                <TimelineEvent key={event.id} event={event} index={i} />
              ))
            ) : (
              <p className="py-8 text-center text-sm text-ink/45">
                No events loaded.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
