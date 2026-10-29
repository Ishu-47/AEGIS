"""
AEGIS Investigation Engine — AI-powered root cause analysis.

Uses Google Gemini for LLM reasoning. The engine is application-agnostic:
it receives normalized diagnostic events and produces structured investigation
reports without any hardcoded knowledge of specific microservices.

LangGraph orchestrates the investigation as a multi-step workflow:
  1. Collect evidence — gather all events for the incident
  2. Analyze patterns — deterministic pattern extraction
  3. LLM reasoning — interpret evidence, identify root cause
  4. Produce report — structured output

RAG is used to enrich the investigation with historical incident data.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Incident,
    IncidentEvent,
    InvestigationReport,
    LogEvent,
)

# ---------------------------------------------------------------------------
# Gemini LLM integration
# ---------------------------------------------------------------------------

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def _get_gemini_client():
    """Get a configured Gemini client."""
    if not GEMINI_AVAILABLE:
        return None
    if not GEMINI_API_KEY:
        return None
    return genai.Client(api_key=GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Evidence collection (deterministic)
# ---------------------------------------------------------------------------

def collect_evidence(
    db: Session,
    incident: Incident,
) -> dict[str, Any]:
    """
    Gather all events and contextual data for an incident.
    Pure database queries — no LLM involved.
    """
    # Get linked log events
    event_ids = db.scalars(
        select(IncidentEvent.log_event_id)
        .where(IncidentEvent.incident_id == incident.id)
    ).all()

    events = db.scalars(
        select(LogEvent)
        .where(LogEvent.id.in_(event_ids))
        .order_by(LogEvent.timestamp.asc())
    ).all()

    # Build timeline
    timeline = []
    for event in events:
        timeline.append({
            "timestamp": event.timestamp.isoformat(),
            "severity": event.severity,
            "service": event.service,
            "message": event.message,
            "correlation_id": event.correlation_id,
        })

    # Extract unique services
    services = list(set(e.service for e in events))

    # Extract stack traces
    stack_traces = []
    for event in events:
        if _looks_like_stack_trace(event.message):
            stack_traces.append({
                "service": event.service,
                "trace": event.message,
                "locations": _extract_stack_locations(event.message),
            })

    # Extract exception types
    exception_types = []
    for event in events:
        exc = _extract_exception_type(event.message)
        if exc and exc not in exception_types:
            exception_types.append(exc)

    # Get recent historical incidents for RAG context
    historical = _get_historical_context(db, incident)

    return {
        "incident_id": incident.id,
        "incident_title": incident.title,
        "incident_severity": incident.severity,
        "application_id": incident.application_id,
        "services": services,
        "event_count": len(events),
        "timeline": timeline,
        "stack_traces": stack_traces,
        "exception_types": exception_types,
        "first_seen": incident.first_seen.isoformat(),
        "last_seen": incident.last_seen.isoformat(),
        "historical_incidents": historical,
    }


def _looks_like_stack_trace(message: str) -> bool:
    """Check if a message contains a stack trace."""
    indicators = [
        r"\bat\s+[\w.$]+\([\w.]+:\d+\)",          # Java: at com.Foo.bar(Foo.java:42)
        r"File\s+\"[^\"]+\",\s+line\s+\d+",        # Python: File "foo.py", line 42
        r"at\s+[\w./<>]+\s+\([\w./:]+\)",           # Node: at func (/path:line:col)
        r"Traceback\s*\(most recent call",           # Python traceback header
        r"^\s+at\s+",                                # Generic "at" lines
    ]
    return any(re.search(p, message, re.MULTILINE) for p in indicators)


def _extract_stack_locations(trace: str) -> list[str]:
    """Extract file:line references from stack traces."""
    locations = []

    # Java: at com.example.Service.method(Service.java:42)
    for m in re.finditer(r"at\s+([\w.$]+)\(([\w.]+:\d+)\)", trace):
        locations.append(f"{m.group(1)} ({m.group(2)})")

    # Python: File "path/to/file.py", line 42
    for m in re.finditer(r'File\s+"([^"]+)",\s+line\s+(\d+)', trace):
        locations.append(f"{m.group(1)}:{m.group(2)}")

    # Node: at function (/path/to/file.js:42:10)
    for m in re.finditer(r"at\s+[\w./<>]+\s+\(([^)]+:\d+:\d+)\)", trace):
        locations.append(m.group(1))

    return locations


def _extract_exception_type(message: str) -> str | None:
    """Extract exception class name from a message."""
    m = re.search(r"([\w.]+(?:Exception|Error|Fault|Timeout))\b", message)
    return m.group(1) if m else None


def _get_historical_context(
    db: Session,
    incident: Incident,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    RAG-style retrieval: find similar past incidents for the same application
    based on fingerprint and service.
    """
    # Find resolved incidents with the same fingerprint
    similar = db.scalars(
        select(Incident)
        .where(
            Incident.application_id == incident.application_id,
            Incident.id != incident.id,
            Incident.fingerprint == incident.fingerprint,
        )
        .order_by(Incident.last_seen.desc())
        .limit(limit)
    ).all()

    # Also find incidents from the same service
    if len(similar) < limit:
        service_incidents = db.scalars(
            select(Incident)
            .where(
                Incident.application_id == incident.application_id,
                Incident.id != incident.id,
                Incident.service == incident.service,
            )
            .order_by(Incident.last_seen.desc())
            .limit(limit - len(similar))
        ).all()
        similar.extend(service_incidents)

    results = []
    for inc in similar:
        report = db.scalars(
            select(InvestigationReport)
            .where(InvestigationReport.incident_id == inc.id)
            .limit(1)
        ).first()

        entry = {
            "title": inc.title,
            "service": inc.service,
            "severity": inc.severity,
            "status": inc.status,
            "first_seen": inc.first_seen.isoformat(),
        }
        if report:
            entry["root_cause"] = report.probable_root_cause
            entry["remediation"] = report.remediation_steps

        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Pattern analysis (deterministic)
# ---------------------------------------------------------------------------

def analyze_patterns(evidence: dict[str, Any]) -> dict[str, Any]:
    """
    Deterministic pattern analysis on the evidence.
    Extracts error frequency, temporal patterns, service correlations.
    """
    timeline = evidence.get("timeline", [])

    # Error frequency by service
    service_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}

    for event in timeline:
        svc = event.get("service", "unknown")
        sev = event.get("severity", "INFO")
        service_counts[svc] = service_counts.get(svc, 0) + 1
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Detect cascading failures (errors in multiple services)
    is_cascading = len(service_counts) > 1

    # Detect repeated errors (same message pattern)
    message_counts: dict[str, int] = {}
    for event in timeline:
        msg_key = event.get("message", "")[:100]
        message_counts[msg_key] = message_counts.get(msg_key, 0) + 1

    repeated_patterns = {
        k: v for k, v in message_counts.items() if v > 1
    }

    # Identify correlation IDs linking events
    correlation_ids = list(set(
        e.get("correlation_id") for e in timeline
        if e.get("correlation_id")
    ))

    return {
        "service_counts": service_counts,
        "severity_counts": severity_counts,
        "is_cascading": is_cascading,
        "repeated_patterns": repeated_patterns,
        "correlation_ids": correlation_ids,
        "total_events": len(timeline),
    }


# ---------------------------------------------------------------------------
# LLM investigation step
# ---------------------------------------------------------------------------

INVESTIGATION_PROMPT = """You are AEGIS, an AI incident investigation engine. Your role is to analyze diagnostic data from software applications and produce structured investigation reports.

## Rules
1. Only state conclusions that are directly supported by the evidence provided.
2. If the evidence is insufficient to determine a root cause, say so explicitly.
3. Do NOT invent causes or present hypotheses as confirmed facts.
4. If you identify multiple possible causes, rank them by likelihood and explain why.
5. Be specific about which log entries, stack traces, or patterns support your conclusions.

## Evidence

### Incident
- Title: {incident_title}
- Severity: {incident_severity}
- Services involved: {services}
- First seen: {first_seen}
- Last seen: {last_seen}
- Total events: {event_count}

### Event Timeline
{timeline_text}

### Stack Traces
{stack_traces_text}

### Exception Types Found
{exception_types_text}

### Pattern Analysis
- Cascading failure detected: {is_cascading}
- Repeated error patterns: {repeated_patterns}
- Correlation IDs: {correlation_ids}
- Error distribution by service: {service_counts}

### Historical Context (similar past incidents)
{historical_text}

## Required Output Format
Respond with a JSON object containing exactly these fields:
{{
  "observed_error": "Clear description of what error was observed",
  "affected_service": "Primary service affected",
  "probable_root_cause": "Most likely root cause based on evidence",
  "supporting_evidence": ["List of specific evidence items supporting the root cause"],
  "remediation_steps": ["Ordered list of recommended actions to fix the issue"],
  "stack_trace_locations": ["Relevant source code locations from stack traces"],
  "confidence": 0.0 to 1.0,
  "uncertainty_notes": "What evidence is missing or what assumptions were made"
}}

Respond ONLY with the JSON object, no additional text."""


def _format_timeline(timeline: list[dict]) -> str:
    """Format timeline events for the LLM prompt."""
    if not timeline:
        return "No events available."

    lines = []
    for event in timeline[:50]:  # Limit to avoid token overflow
        ts = event.get("timestamp", "?")
        sev = event.get("severity", "?")
        svc = event.get("service", "?")
        msg = event.get("message", "")[:300]
        corr = event.get("correlation_id", "")
        corr_str = f" [corr:{corr}]" if corr else ""
        lines.append(f"  [{ts}] {sev} {svc}{corr_str}: {msg}")

    if len(timeline) > 50:
        lines.append(f"  ... and {len(timeline) - 50} more events")

    return "\n".join(lines)


def _format_stack_traces(traces: list[dict]) -> str:
    """Format stack traces for the LLM prompt."""
    if not traces:
        return "No stack traces found."

    parts = []
    for i, trace in enumerate(traces[:5], 1):
        parts.append(f"  Stack trace #{i} ({trace.get('service', '?')}):")
        parts.append(f"    {trace.get('trace', '')[:500]}")
        if trace.get("locations"):
            parts.append(f"    Locations: {', '.join(trace['locations'][:5])}")

    return "\n".join(parts)


def run_llm_investigation(
    evidence: dict[str, Any],
    patterns: dict[str, Any],
) -> dict[str, Any]:
    """
    Use Google Gemini to reason about the evidence and produce a structured
    investigation report.

    Falls back to a deterministic analysis if the LLM is unavailable.
    """
    client = _get_gemini_client()

    if client is None:
        return _fallback_investigation(evidence, patterns)

    prompt = INVESTIGATION_PROMPT.format(
        incident_title=evidence.get("incident_title", "Unknown"),
        incident_severity=evidence.get("incident_severity", "Unknown"),
        services=", ".join(evidence.get("services", ["unknown"])),
        first_seen=evidence.get("first_seen", "?"),
        last_seen=evidence.get("last_seen", "?"),
        event_count=evidence.get("event_count", 0),
        timeline_text=_format_timeline(evidence.get("timeline", [])),
        stack_traces_text=_format_stack_traces(evidence.get("stack_traces", [])),
        exception_types_text=", ".join(evidence.get("exception_types", [])) or "None found",
        is_cascading=patterns.get("is_cascading", False),
        repeated_patterns=json.dumps(patterns.get("repeated_patterns", {})),
        correlation_ids=", ".join(patterns.get("correlation_ids", [])) or "None",
        service_counts=json.dumps(patterns.get("service_counts", {})),
        historical_text=_format_historical(evidence.get("historical_incidents", [])),
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        text = response.text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        result = json.loads(text)

        # Validate required fields
        required = [
            "observed_error", "affected_service", "probable_root_cause",
            "supporting_evidence", "remediation_steps", "confidence",
        ]
        for field in required:
            if field not in result:
                result[field] = "Not determined"

        result["raw_llm_response"] = {"model": "gemini-2.0-flash", "text": response.text}

        return result

    except Exception as e:
        # If LLM fails, use deterministic fallback
        fallback = _fallback_investigation(evidence, patterns)
        fallback["uncertainty_notes"] = (
            f"LLM investigation failed ({type(e).__name__}: {e}). "
            "This report uses deterministic analysis only."
        )
        return fallback


def _format_historical(historical: list[dict]) -> str:
    """Format historical incidents for the prompt."""
    if not historical:
        return "No similar past incidents found."

    lines = []
    for h in historical:
        line = f"  - {h.get('title', '?')} ({h.get('service', '?')}, {h.get('status', '?')})"
        if h.get("root_cause"):
            line += f"\n    Root cause: {h['root_cause'][:200]}"
        lines.append(line)

    return "\n".join(lines)


def _fallback_investigation(
    evidence: dict[str, Any],
    patterns: dict[str, Any],
) -> dict[str, Any]:
    """
    Deterministic fallback when no LLM is available.
    Produces a basic report from patterns and evidence alone.
    """
    services = evidence.get("services", ["unknown"])
    timeline = evidence.get("timeline", [])
    exceptions = evidence.get("exception_types", [])
    stack_traces = evidence.get("stack_traces", [])

    # Determine the primary error
    error_messages = [
        e["message"] for e in timeline
        if e.get("severity") in ("ERROR", "CRITICAL", "FATAL")
    ][:5]

    observed = "; ".join(error_messages[:3]) if error_messages else evidence.get("incident_title", "Unknown error")

    # Determine probable cause from patterns
    if exceptions:
        cause = f"Exception(s) detected: {', '.join(exceptions)}. Review the throwing code paths."
    elif patterns.get("is_cascading"):
        cause = (
            f"Cascading failure across services: {', '.join(services)}. "
            "The root cause likely originates in the first service to report errors."
        )
    elif patterns.get("repeated_patterns"):
        top_pattern = max(
            patterns["repeated_patterns"].items(),
            key=lambda x: x[1],
        )
        cause = f"Repeated error pattern ({top_pattern[1]} occurrences): {top_pattern[0]}"
    else:
        cause = "Insufficient evidence to determine root cause with certainty."

    # Extract stack locations
    locations = []
    for st in stack_traces:
        locations.extend(st.get("locations", []))

    return {
        "observed_error": observed[:2000],
        "affected_service": services[0] if services else "unknown",
        "probable_root_cause": cause,
        "supporting_evidence": error_messages[:10],
        "remediation_steps": [
            "Review the error messages and stack traces listed above.",
            "Check application logs around the timestamps indicated.",
            f"Investigate the primary service: {services[0] if services else 'unknown'}.",
            "If this is a recurring issue, review past incident resolutions.",
        ],
        "stack_trace_locations": locations[:10],
        "confidence": 0.3 if cause.startswith("Insufficient") else 0.5,
        "uncertainty_notes": (
            "This report was generated using deterministic analysis only "
            "(no LLM available). Confidence is limited."
        ),
        "raw_llm_response": None,
    }


# ---------------------------------------------------------------------------
# Full investigation pipeline
# ---------------------------------------------------------------------------

def investigate_incident(
    db: Session,
    incident: Incident,
) -> InvestigationReport:
    """
    Run the full investigation pipeline for an incident.

    Steps:
      1. Collect evidence (deterministic DB queries)
      2. Analyze patterns (deterministic pattern extraction)
      3. LLM reasoning (Gemini, with fallback)
      4. Store structured report

    Returns the created InvestigationReport.
    """
    # Check if report already exists
    existing = db.scalars(
        select(InvestigationReport)
        .where(InvestigationReport.incident_id == incident.id)
        .limit(1)
    ).first()

    if existing:
        # Delete existing report for re-investigation
        db.delete(existing)
        db.flush()

    # Step 1: Collect evidence
    evidence = collect_evidence(db, incident)

    # Step 2: Analyze patterns
    patterns = analyze_patterns(evidence)

    # Step 3: LLM reasoning
    result = run_llm_investigation(evidence, patterns)

    # Step 4: Store report
    report = InvestigationReport(
        incident_id=incident.id,
        observed_error=str(result.get("observed_error", ""))[:5000],
        affected_service=str(result.get("affected_service", "unknown"))[:150],
        probable_root_cause=str(result.get("probable_root_cause", ""))[:5000],
        supporting_evidence=result.get("supporting_evidence"),
        remediation_steps=result.get("remediation_steps"),
        stack_trace_locations=result.get("stack_trace_locations"),
        confidence=float(result.get("confidence", 0.0)),
        uncertainty_notes=result.get("uncertainty_notes"),
        raw_llm_response=result.get("raw_llm_response"),
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    # Mark incident as investigated
    incident.status = "investigated"
    db.commit()

    return report
