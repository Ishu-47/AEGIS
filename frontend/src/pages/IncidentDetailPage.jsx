import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useApp } from "../App";
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
  Layers,
  GitBranch,
  ShieldCheck,
  ListChecks,
  BarChart3,
  MessageCircle,
} from "lucide-react";

// Reports persisted before and after the evidence-grounding upgrade can have
// different JSON shapes. Never render an arbitrary API object as a React child.
function displayText(value, fallback = "Not available") {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((item) => displayText(item, "")).filter(Boolean).join(", ") || fallback;
  if (typeof value === "object") return displayText(value.description ?? value.message ?? value.evidence ?? value.text ?? value.name ?? value.service, fallback);
  return fallback;
}

function cleanListItem(value) {
  const text = displayText(value, "");
  return text.replace(/^\s*(?:\d+[.)]\s*|[-*]\s*)/, "").trim();
}

function EvidenceItem({ item }) {
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    return <span className="font-mono text-xs leading-5 break-words">{displayText(item)}</span>;
  }
  const eventId = item.event_id ?? item.id;
  const date = item.timestamp ? new Date(item.timestamp) : null;
  const timestamp = date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : null;
  return (
    <div className="min-w-0 space-y-1">
      <div className="flex flex-wrap items-center gap-2 text-[10px] text-ink/50">
        {eventId != null && <span className="font-mono font-semibold">Event {displayText(eventId)}</span>}
        {item.service && <span>{displayText(item.service)}</span>}
        {item.severity && <SeverityBadge severity={displayText(item.severity)} />}
        {timestamp && <span>{timestamp}</span>}
      </div>
      <p className="font-mono text-xs leading-5 text-ink/75 break-words">
        {displayText(item.evidence ?? item.message ?? item.description ?? item.text)}
      </p>
    </div>
  );
}

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

function ConfidenceMeter({ value, factors }) {
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

      {/* Confidence factors breakdown */}
      {factors && (
        <div className="mt-3 space-y-1.5">
          <p className="text-[10px] font-semibold text-ink/50 uppercase tracking-wide">
            Calibration Factors
          </p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <FactorRow
              label="Events analysed"
              value={factors.events_analyzed}
            />
            <FactorRow
              label="Events cited"
              value={factors.events_cited}
            />
            <FactorRow
              label="Citation accuracy"
              value={`${Math.round((factors.citation_accuracy || 0) * 100)}%`}
            />
            <FactorRow
              label="Report event coverage"
              value={`${Math.round((factors.evidence_coverage || 0) * 100)}%`}
            />
            <FactorRow
              label="Hypothesis coverage"
              value={`${Math.round((factors.hypothesis_evidence_coverage || 0) * 100)}%`}
            />
            <FactorRow
              label="Hypotheses with evidence"
              value={`${Math.round((factors.claim_coverage || 0) * 100)}%`}
            />
            <FactorRow
              label="Stack traces"
              value={factors.has_stack_traces ? "Yes" : "No"}
            />
            <FactorRow
              label="Correlation chains"
              value={factors.has_correlation_chains ? "Yes" : "No"}
            />
            <FactorRow
              label="Knowledge context"
              value={factors.has_knowledge_context ? "Yes" : "No"}
            />
            <FactorRow
              label="Historical context"
              value={factors.has_historical_context ? "Yes" : "No"}
            />
          </div>
          {factors.events_fabricated > 0 && (
            <p className="mt-1.5 text-[10px] text-danger font-medium">
              ⚠ {factors.events_fabricated} fabricated citation(s) detected and penalised
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function FactorRow({ label, value }) {
  return (
    <div className="flex items-center justify-between text-[10px]">
      <span className="text-ink/45">{label}</span>
      <span className="font-medium">{value}</span>
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
          <span className="rounded bg-ink/5 px-1.5 py-0.5 text-[9px] font-mono text-ink/40">
            id:{event.id || event.event_id}
          </span>
          <span className="ml-auto text-[10px] text-ink/40">
            {new Date(event.timestamp).toLocaleString()}
          </span>
        </div>
        <p className="mt-1.5 break-words font-mono text-[11px] leading-5 text-ink/75">
          {displayText(event.message, "").slice(0, 500)}
          {event.message?.length > 500 && "..."}
        </p>
        {event.correlation_id && (
          <p className="mt-1 text-[10px] text-ink/40">
            Correlation: {displayText(event.correlation_id)}
          </p>
        )}
      </div>
    </div>
  );
}

function ReportSection({ icon: Icon, title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);

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
  const { selected } = useApp();
  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [investigating, setInvestigating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!selected) return;

    setLoading(true);
    fetchIncident(parseInt(id))
      .then(setIncident)
      .catch(() => setError("Could not load incident."))
      .finally(() => setLoading(false));
  }, [id, selected?.id]);

  async function handleInvestigate() {
    setInvestigating(true);
    setError("");

    try {
      await triggerInvestigation(parseInt(id), selected.api_key);
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
      await updateIncidentStatus(parseInt(id), newStatus, selected.api_key);
      const updated = await fetchIncident(parseInt(id));
      setIncident(updated);
    } catch {
      // silent
    }
  }

  if (!selected) {
    return (
      <div className="py-20 text-center text-sm text-ink/50">
        Select an application to view incident details.
      </div>
    );
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
              <div className="flex items-center justify-between border-b border-ink/8 pb-4">
                <div className="flex items-center gap-2">
                  <FileText size={16} className="text-oxblood" />
                  <h2 className="font-semibold">Investigation Report</h2>
                </div>
                <div className="flex items-center gap-2 text-[10px] text-ink/40">
                  <span>{report.events_analyzed} events analysed</span>
                  <span>·</span>
                  <span>{report.events_cited} cited</span>
                  {report.model_used && (
                    <>
                      <span>·</span>
                      <span>{report.model_used}</span>
                    </>
                  )}
                </div>
              </div>

              <div className="mt-4 space-y-0">
                {/* 9. Confidence */}
                <div className="pb-4 border-b border-ink/6">
                  <ConfidenceMeter
                    value={report.confidence}
                    factors={report.confidence_factors}
                  />
                </div>

                {/* 1. Incident Summary */}
                {report.incident_summary && (
                  <ReportSection icon={MessageCircle} title="Incident Summary">
                    <p className="text-sm leading-relaxed text-ink/75">
                      {displayText(report.incident_summary)}
                    </p>
                  </ReportSection>
                )}

                {/* 2. Observed Error */}
                <ReportSection icon={AlertTriangle} title="Observed Error">
                  <p className="text-sm leading-relaxed text-ink/75">
                    {report.observed_error}
                  </p>
                </ReportSection>

                {/* 3 + 4. Affected Services */}
                <ReportSection icon={Layers} title="Affected Services">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-oxblood/10 px-2 py-0.5 text-[10px] font-bold text-oxblood uppercase">
                        First observed failure
                      </span>
                      <span className="text-sm font-semibold">
                        {displayText(report.affected_service, "Unknown")}
                      </span>
                    </div>
                    {report.downstream_services?.length > 0 && (
                      <div className="mt-2">
                        <p className="text-[10px] font-semibold text-ink/45 uppercase tracking-wide mb-1.5">
                          Later correlated error services
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {report.downstream_services.map((svc, i) => (
                            <span
                              key={i}
                              className="rounded-full bg-warning/10 px-2.5 py-0.5 text-xs font-medium text-warning"
                            >
                              {typeof svc === "string" ? svc : String(svc?.service ?? svc?.name ?? "Unknown service")}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </ReportSection>

                {/* 5. Timeline Summary */}
                {report.timeline_summary?.length > 0 && (
                  <ReportSection icon={GitBranch} title="Incident Timeline">
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {report.timeline_summary.map((entry, i) => (
                        <div
                          key={i}
                          className="flex gap-2.5 rounded-lg border border-ink/6 p-2.5"
                        >
                          <div className="shrink-0">
                            <SeverityBadge severity={entry.severity} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 text-[10px] text-ink/45">
                              <span className="font-mono">
                                id:{entry.event_id}
                              </span>
                              <span>{entry.service}</span>
                              <span className="ml-auto">
                                {new Date(entry.timestamp).toLocaleTimeString()}
                              </span>
                            </div>
                            <p className="mt-0.5 text-xs text-ink/70">
                              {displayText(entry.description || entry.message)}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </ReportSection>
                )}

                {/* 6. Root Cause */}
                <ReportSection icon={Search} title="Probable Root Cause">
                  <div className="rounded-lg bg-oxblood/5 border border-oxblood/10 p-4">
                    <p className="text-sm leading-relaxed font-medium">
                      {report.probable_root_cause}
                    </p>
                  </div>
                </ReportSection>

                {/* 7. Alternative Hypotheses */}
                {report.alternative_hypotheses?.length > 0 && (
                  <ReportSection icon={HelpCircle} title="Alternative Hypotheses">
                    <div className="space-y-3">
                      {report.alternative_hypotheses.map((hyp, i) => (
                        <div
                          key={i}
                          className="rounded-lg border border-ink/8 p-3"
                        >
                          <div className="flex items-center gap-2">
                            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                              hyp.probability === "high"
                                ? "bg-oxblood/10 text-oxblood"
                                : hyp.probability === "medium"
                                  ? "bg-warning/10 text-warning"
                                  : "bg-ink/8 text-ink/50"
                            }`}>
                              {hyp.probability || `#${i + 2}`}
                            </span>
                          </div>
                          <p className="mt-1.5 text-sm text-ink/75">
                            {displayText(hyp.hypothesis)}
                          </p>
                          {hyp.reasoning && (
                            <p className="mt-1 text-xs text-ink/50 italic">
                              {displayText(hyp.reasoning)}
                            </p>
                          )}
                          {hyp.supporting_event_ids?.length > 0 && (
                            <p className="mt-1 text-[10px] text-ink/40">
                              Evidence: events{" "}
                              {displayText(hyp.supporting_event_ids)}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </ReportSection>
                )}

                {/* 8. Supporting Evidence */}
                {report.supporting_evidence?.length > 0 && (
                  <ReportSection icon={FileText} title="Supporting Evidence">
                    <ul className="space-y-2">
                      {report.supporting_evidence.map((item, i) => (
                        <li
                          key={i}
                          className="flex gap-2 text-sm text-ink/70"
                        >
                          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-oxblood/40" />
                          <div className="min-w-0 flex-1"><EvidenceItem item={item} /></div>
                        </li>
                      ))}
                    </ul>
                  </ReportSection>
                )}

                {/* 10. Remediation */}
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
                          {cleanListItem(step)}
                        </li>
                      ))}
                    </ol>
                  </ReportSection>
                )}

                {/* 11. Verification Steps */}
                {report.verification_steps?.length > 0 && (
                  <ReportSection icon={ListChecks} title="Verification Steps">
                    <ol className="space-y-2">
                      {report.verification_steps.map((step, i) => (
                        <li
                          key={i}
                          className="flex gap-3 text-sm text-ink/70"
                        >
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success/10 text-[10px] font-bold text-success">
                            ✓
                          </span>
                          {cleanListItem(step)}
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
                          {typeof loc === "string" ? loc : String(loc?.location ?? loc?.file ?? loc?.description ?? "Unknown location")}
                        </p>
                      ))}
                    </div>
                  </ReportSection>
                )}

                {/* Historical precedent is context, not direct evidence */}
                {report.historical_context_summary?.length > 0 && (
                  <ReportSection icon={Layers} title="Related Historical Incidents">
                    <div className="space-y-2">
                      {report.historical_context_summary.map((item, i) => (
                        <div key={`${item.title || "history"}-${i}`} className="rounded-lg border border-ink/8 p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-semibold">{displayText(item.title)}</p>
                            <span className="rounded-full bg-ink/5 px-2 py-0.5 text-[10px] text-ink/50">Precedent only</span>
                          </div>
                          <p className="mt-1 text-xs text-ink/50">
                            {displayText(item.service)} · {displayText(item.status)} · {displayText(item.match_reason)}
                          </p>
                          {item.previous_root_cause && (
                            <p className="mt-2 text-xs leading-relaxed text-ink/70">
                              Previous finding: {displayText(item.previous_root_cause)}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                    <p className="mt-2 text-[10px] text-ink/40">
                      Historical incidents provide precedent for comparison; they are not evidence that the same cause occurred here.
                    </p>
                  </ReportSection>
                )}

                {/* Uncertainty */}
                {report.uncertainty_notes && (
                  <ReportSection icon={ShieldCheck} title="Uncertainty & Caveats">
                    <p className="text-sm italic text-ink/55">
                      {displayText(report.uncertainty_notes)}
                    </p>
                  </ReportSection>
                )}

                {/* Investigation steps log */}
                {report.investigation_steps?.length > 0 && (
                  <ReportSection
                    icon={BarChart3}
                    title="Investigation Trace"
                    defaultOpen={false}
                  >
                    <div className="space-y-1">
                      {report.investigation_steps.map((step, i) => (
                        <p
                          key={i}
                          className="rounded bg-ink/[0.03] px-3 py-1.5 font-mono text-[10px] text-ink/50"
                        >
                          {i + 1}. {displayText(step)}
                        </p>
                      ))}
                    </div>
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
