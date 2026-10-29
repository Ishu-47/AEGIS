
"""
AEGIS Incident Grouping Module.

Groups error and warning log events using deterministic fingerprints.
Grouping is scoped to an application and uses event timestamps rather
than the time at which the server processes a batch.
"""

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentEvent, LogEvent


GROUPING_WINDOW = timedelta(hours=1)

INCIDENT_SEVERITIES = {"WARN", "ERROR", "CRITICAL", "FATAL"}


@dataclass
class GroupingResult:
    incidents: list[Incident]
    created_count: int
    updated_count: int


def _as_utc(value: datetime) -> datetime:
    """Normalize timestamps so comparisons are timezone-safe."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _extract_error_signature(message: str) -> str:
    """Remove variable values to produce a stable error signature."""
    signature = message.strip()

    signature = re.sub(
        r"\b0x[0-9a-fA-F]+\b",
        "<HEX>",
        signature,
    )

    signature = re.sub(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{12}\b",
        "<UUID>",
        signature,
    )

    # Replace ISO-like timestamps embedded in messages.
    signature = re.sub(
        r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
        r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b",
        "<TIMESTAMP>",
        signature,
    )

    # Replace numeric identifiers, but preserve single digits.
    signature = re.sub(r"\b\d{2,}\b", "<N>", signature)

    signature = re.sub(r"\s+", " ", signature).strip()

    return signature[:500]


def _compute_fingerprint(
    application_id: str,
    service: str,
    signature: str,
    correlation_id: str | None = None,
) -> str:
    """Compute a stable fingerprint scoped to an application."""
    if correlation_id:
        # The same request/trace can connect events across services.
        raw = (
            f"{application_id.lower()}|"
            f"correlation|{correlation_id.strip()}"
        )
    else:
        raw = (
            f"{application_id.lower()}|"
            f"{service.strip().lower()}|"
            f"{signature.lower()}"
        )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_exception_type(message: str) -> str | None:
    match = re.search(
        r"([\w.]+(?:Exception|Error|Fault|Timeout))\b",
        message,
    )
    return match.group(1) if match else None


def _build_title(service: str, message: str) -> str:
    exception_type = _extract_exception_type(message)

    if exception_type:
        return f"{exception_type} in {service}"[:300]

    first_line = message.strip().splitlines()[0] if message.strip() else "Unknown error"
    return f"{service}: {first_line[:200]}"[:300]


def _severity_rank(severity: str) -> int:
    return {
        "DEBUG": 0,
        "INFO": 1,
        "WARN": 2,
        "ERROR": 3,
        "CRITICAL": 4,
        "FATAL": 5,
    }.get(severity.upper(), 1)


def group_events(
    db: Session,
    application_id: str,
    records: list[LogEvent],
) -> GroupingResult:
    """
    Group each eligible event independently.

    Events with the same fingerprint can share an open incident when their
    timestamps are within GROUPING_WINDOW of the incident's latest event.
    """
    eligible = [
        event
        for event in records
        if event.application_id == application_id
        and event.severity.upper() in INCIDENT_SEVERITIES
    ]

    eligible.sort(key=lambda event: _as_utc(event.timestamp))

    touched: dict[int, Incident] = {}
    created_count = 0
    updated_count = 0

    try:
        for event in eligible:
            event_time = _as_utc(event.timestamp)
            
            already_linked = db.scalar(
                select(Incident)
                .join(
                    IncidentEvent,
                    IncidentEvent.incident_id == Incident.id,
                )
                .where(
                    Incident.application_id == application_id,
                    IncidentEvent.log_event_id == event.id,
                )
                .limit(1)
            )

            if already_linked is not None:
                touched[already_linked.id] = already_linked
                continue

            signature = _extract_error_signature(event.message)

            fingerprint = _compute_fingerprint(
                application_id=application_id,
                service=event.service,
                signature=signature,
                correlation_id=event.correlation_id,
            )

            lower_bound = event_time - GROUPING_WINDOW
            upper_bound = event_time + GROUPING_WINDOW

            # Find the closest open incident by event time, not wall-clock time.
            candidates = db.scalars(
                select(Incident)
                .where(
                    Incident.application_id == application_id,
                    Incident.fingerprint == fingerprint,
                    Incident.status == "open",
                    Incident.last_seen >= lower_bound,
                    Incident.last_seen <= upper_bound,
                )
                .order_by(Incident.last_seen.desc())
            ).all()

            incident = None

            for candidate in candidates:
                # Ignore a candidate if this exact event is already linked.
                existing_link = db.get(
                    IncidentEvent,
                    (candidate.id, event.id),
                )
                if existing_link is None:
                    incident = candidate
                    break

            if incident is None:
                incident = Incident(
                    application_id=application_id,
                    fingerprint=fingerprint,
                    title=_build_title(event.service, event.message),
                    service=event.service,
                    severity=event.severity.upper(),
                    status="open",
                    first_seen=event_time,
                    last_seen=event_time,
                    event_count=0,
                )
                db.add(incident)
                db.flush()
                created_count += 1
            else:
                updated_count += 1

            # Avoid duplicate links and incorrect event counts.
            existing_link = db.get(
                IncidentEvent,
                (incident.id, event.id),
            )

            if existing_link is None:
                db.add(
                    IncidentEvent(
                        incident_id=incident.id,
                        log_event_id=event.id,
                    )
                )
                incident.event_count += 1

            current_first = _as_utc(incident.first_seen)
            current_last = _as_utc(incident.last_seen)

            if event_time < current_first:
                incident.first_seen = event_time

            if event_time > current_last:
                incident.last_seen = event_time

            if _severity_rank(event.severity) > _severity_rank(incident.severity):
                incident.severity = event.severity.upper()

            touched[incident.id] = incident

        db.commit()

        for incident in touched.values():
            db.refresh(incident)

        return GroupingResult(
            incidents=list(touched.values()),
            created_count=created_count,
            updated_count=updated_count,
        )

    except Exception:
        db.rollback()
        raise
