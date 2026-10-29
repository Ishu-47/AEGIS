import hashlib
import json
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import (
    Application,
    LogEvent,
    Incident,
    IncidentEvent,
    InvestigationReport,
)
from app.grouping import group_events
from app.investigation import investigate_incident


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Importing app.models registers the tables with Base.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AEGIS API",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=2000)


class LogEventInput(BaseModel):
    timestamp: datetime | str | None = None
    severity: str = "INFO"
    service: str = "unknown"
    message: str
    correlation_id: str | None = None
    raw_event: dict[str, Any] | None = None


class IngestRequest(BaseModel):
    application_id: str
    events: list[LogEventInput] = Field(max_length=500)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )
        except ValueError:
            result = datetime.now(timezone.utc)
    else:
        result = datetime.now(timezone.utc)

    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)

    return result


def normalize_event(
    raw: dict[str, Any],
    fallback_message: str = "",
) -> dict[str, Any]:
    timestamp = (
        raw.get("timestamp")
        or raw.get("@timestamp")
        or raw.get("time")
    )

    severity = str(
        raw.get("severity")
        or raw.get("level")
        or raw.get("log_level")
        or "INFO"
    ).upper()

    if severity == "WARNING":
        severity = "WARN"

    service = str(
        raw.get("service")
        or raw.get("logger")
        or raw.get("source")
        or "unknown"
    )

    message = str(
        raw.get("message")
        or raw.get("msg")
        or fallback_message
        or json.dumps(raw, default=str)
    )

    correlation_id = (
        raw.get("correlation_id")
        or raw.get("correlationId")
        or raw.get("trace_id")
        or raw.get("traceId")
        or raw.get("request_id")
        or raw.get("requestId")
    )

    return {
        "timestamp": parse_timestamp(timestamp),
        "severity": severity,
        "service": service,
        "message": message,
        "correlation_id": str(correlation_id) if correlation_id else None,
        "raw_event": raw,
    }


def parse_logs(content: str) -> list[dict[str, Any]]:
    content = content.strip()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="No log content provided.",
        )

    # First, try parsing the entire input as JSON.
    try:
        parsed = json.loads(content)

        if isinstance(parsed, dict):
            parsed = parsed.get("events", [parsed])

        if isinstance(parsed, list):
            if not all(isinstance(item, dict) for item in parsed):
                raise HTTPException(
                    status_code=400,
                    detail="JSON logs must contain objects.",
                )

            return [normalize_event(item) for item in parsed]

    except json.JSONDecodeError:
        pass

    # Try JSON-Lines (one JSON object per line)
    lines = content.splitlines()
    if lines and lines[0].strip().startswith("{"):
        json_events = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    json_events.append(normalize_event(obj))
            except json.JSONDecodeError:
                break

        if json_events:
            return json_events

    # Otherwise, parse plain-text logs one line at a time.
    pattern = re.compile(
        r"^\s*(?P<timestamp>\S+)\s+"
        r"(?P<severity>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)"
        r"\s+(?P<service>[\w.$-]+)\s*[-:]\s*"
        r"(?P<message>.*)$",
        re.IGNORECASE,
    )

    events = []
    current_multiline: dict | None = None

    for line in content.splitlines():
        line_stripped = line.strip()

        if not line_stripped:
            continue

        match = pattern.match(line_stripped)

        if match:
            # Save any accumulated multiline event
            if current_multiline:
                events.append(normalize_event(current_multiline))

            current_multiline = match.groupdict()
        elif current_multiline:
            # Append to current multiline (stack trace continuation)
            current_multiline["message"] += "\n" + line_stripped
        else:
            severity_match = re.search(
                r"\b(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)\b",
                line_stripped,
                re.IGNORECASE,
            )

            severity = (
                severity_match.group(1).upper()
                if severity_match
                else "INFO"
            )

            if severity == "WARNING":
                severity = "WARN"

            events.append(
                normalize_event(
                    {
                        "severity": severity,
                        "service": "unknown",
                        "message": line_stripped,
                    },
                    fallback_message=line_stripped,
                )
            )

    # Don't forget the last multiline event
    if current_multiline:
        events.append(normalize_event(current_multiline))

    if not events:
        raise HTTPException(
            status_code=400,
            detail="No valid log entries found.",
        )

    return events


def get_authorized_application(
    db: Session,
    application_id: str,
    api_key: str | None,
) -> Application:
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header.",
        )

    application = db.get(Application, application_id)

    if application is None:
        raise HTTPException(
            status_code=404,
            detail="Application not found.",
        )

    supplied_hash = hash_api_key(api_key)

    if not secrets.compare_digest(
        supplied_hash,
        application.api_key_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
        )

    return application


def save_events(
    db: Session,
    application_id: str,
    events: list[dict[str, Any]],
) -> list[LogEvent]:
    records = [
        LogEvent(
            application_id=application_id,
            timestamp=parse_timestamp(event.get("timestamp")),
            severity=str(event.get("severity", "INFO")).upper(),
            service=str(event.get("service", "unknown")),
            message=str(event.get("message", "")),
            correlation_id=event.get("correlation_id"),
            raw_event=event.get("raw_event"),
        )
        for event in events
    ]

    try:

        db.add_all(records)
        db.commit()

        for record in records:
            db.refresh(record)

        return records
    except Exception:
        db.rollback()
        raise


def serialize_event(event: LogEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "application_id": event.application_id,
        "timestamp": event.timestamp,
        "severity": event.severity,
        "service": event.service,
        "message": event.message,
        "correlation_id": event.correlation_id,
    }


def serialize_incident(incident: Incident) -> dict[str, Any]:
    return {
        "id": incident.id,
        "application_id": incident.application_id,
        "fingerprint": incident.fingerprint,
        "title": incident.title,
        "service": incident.service,
        "severity": incident.severity,
        "status": incident.status,
        "first_seen": incident.first_seen,
        "last_seen": incident.last_seen,
        "event_count": incident.event_count,
        "has_report": incident.report is not None,
    }


def serialize_report(report: InvestigationReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "incident_id": report.incident_id,
        "observed_error": report.observed_error,
        "affected_service": report.affected_service,
        "probable_root_cause": report.probable_root_cause,
        "supporting_evidence": report.supporting_evidence,
        "remediation_steps": report.remediation_steps,
        "stack_trace_locations": report.stack_trace_locations,
        "confidence": report.confidence,
        "uncertainty_notes": report.uncertainty_notes,
        "created_at": report.created_at,
    }


# ---------------------------------------------------------------------------
# Routes — Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "aegis-api"}


# ---------------------------------------------------------------------------
# Routes — Applications
# ---------------------------------------------------------------------------

@app.post("/api/applications")
def register_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
):
    api_key = secrets.token_urlsafe(32)

    application = Application(
        name=payload.name.strip(),
        description=payload.description.strip(),
        api_key_hash=hash_api_key(api_key),
    )

    db.add(application)
    db.commit()
    db.refresh(application)

    # Return the secret only at registration time.
    return {
        "id": application.id,
        "name": application.name,
        "description": application.description,
        "created_at": application.created_at,
        "api_key": api_key,
    }


@app.get("/api/applications")
def list_applications(
    db: Session = Depends(get_db),
):
    applications = db.scalars(
        select(Application).order_by(Application.created_at.desc())
    ).all()

    return [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "created_at": item.created_at,
        }
        for item in applications
    ]


# ---------------------------------------------------------------------------
# Routes — Log upload / paste
# ---------------------------------------------------------------------------

@app.post("/api/applications/{application_id}/logs")
async def upload_logs(
    application_id: str,
    content: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    get_authorized_application(db, application_id, x_api_key)

    if file is not None:
        filename = (file.filename or "").lower()

        if not filename.endswith((".log", ".txt", ".json")):
            raise HTTPException(
                status_code=400,
                detail="Upload a .log, .txt, or .json file.",
            )

        data = await file.read(1_000_001)

        if len(data) > 1_000_000:
            raise HTTPException(
                status_code=413,
                detail="Maximum upload size is 1 MB.",
            )

        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file must be UTF-8 text.",
            )

    if not content or not content.strip():
        raise HTTPException(
            status_code=400,
            detail="Paste logs or select a file.",
        )

    
    events = parse_logs(content)
    records = save_events(db, application_id, events)

    grouping_result = group_events(
        db,
        application_id,
        records,
    )

    return {
        "accepted": len(records),
        "events": [serialize_event(item) for item in records],
        "incidents_created": grouping_result.created_count,
        "incidents_updated": grouping_result.updated_count,
        "incidents_touched": len(grouping_result.incidents),
    }



# ---------------------------------------------------------------------------
# Routes — Structured ingestion API
# ---------------------------------------------------------------------------

@app.post("/api/ingest/logs")
def ingest_structured_logs(
    payload: IngestRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    get_authorized_application(
        db,
        payload.application_id,
        x_api_key,
    )

    
    events = [
        normalize_event(item.model_dump(mode="json"))
        for item in payload.events
    ]

    records = save_events(db, payload.application_id, events)

    grouping_result = group_events(
        db,
        payload.application_id,
        records,
    )

    return {
        "accepted": len(records),
        "incidents_created": grouping_result.created_count,
        "incidents_updated": grouping_result.updated_count,
        "incidents_touched": len(grouping_result.incidents),
        "investigation_started": False,
    }



# ---------------------------------------------------------------------------
# Routes — Log retrieval
# ---------------------------------------------------------------------------

@app.get("/api/applications/{application_id}/logs")
def get_application_logs(
    application_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    get_authorized_application(db, application_id, x_api_key)

    records = db.scalars(
        select(LogEvent)
        .where(LogEvent.application_id == application_id)
        .order_by(LogEvent.timestamp.desc())
    ).all()

    return {"events": [serialize_event(item) for item in records]}


# ---------------------------------------------------------------------------
# Routes — Incidents
# ---------------------------------------------------------------------------

@app.get("/api/applications/{application_id}/incidents")
def list_incidents(
    application_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    get_authorized_application(db, application_id, x_api_key)

    incidents = db.scalars(
        select(Incident)
        .where(Incident.application_id == application_id)
        .order_by(Incident.last_seen.desc())
    ).all()

    return {
        "incidents": [serialize_incident(inc) for inc in incidents],
    }


@app.get("/api/incidents/{incident_id}")
def get_incident(
    incident_id: int,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    incident = db.get(Incident, incident_id)

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    get_authorized_application(db, incident.application_id, x_api_key)

    # Get linked events
    event_ids = db.scalars(
        select(IncidentEvent.log_event_id)
        .where(IncidentEvent.incident_id == incident_id)
    ).all()

    events = db.scalars(
        select(LogEvent)
        .where(LogEvent.id.in_(event_ids))
        .order_by(LogEvent.timestamp.asc())
    ).all()

    result = serialize_incident(incident)
    result["events"] = [serialize_event(e) for e in events]

    # Include report if available
    if incident.report:
        result["report"] = serialize_report(incident.report)

    return result


@app.post("/api/incidents/{incident_id}/investigate")
def trigger_investigation(
    incident_id: int,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    incident = db.get(Incident, incident_id)

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    get_authorized_application(db, incident.application_id, x_api_key)

    report = investigate_incident(db, incident)

    return {
        "status": "completed",
        "report": serialize_report(report),
    }


@app.patch("/api/incidents/{incident_id}/status")
def update_incident_status(
    incident_id: int,
    status: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    valid_statuses = {"open", "investigating", "investigated", "resolved", "dismissed"}

    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Use one of: {', '.join(valid_statuses)}",
        )

    incident = db.get(Incident, incident_id)

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    get_authorized_application(db, incident.application_id, x_api_key)

    incident.status = status
    db.commit()

    return serialize_incident(incident)


# ---------------------------------------------------------------------------
# Routes — Dashboard stats
# ---------------------------------------------------------------------------

@app.get("/api/applications/{application_id}/stats")
def get_application_stats(
    application_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    get_authorized_application(db, application_id, x_api_key)

    total_events = db.scalar(
        select(func.count(LogEvent.id))
        .where(LogEvent.application_id == application_id)
    ) or 0

    total_incidents = db.scalar(
        select(func.count(Incident.id))
        .where(Incident.application_id == application_id)
    ) or 0

    open_incidents = db.scalar(
        select(func.count(Incident.id))
        .where(
            Incident.application_id == application_id,
            Incident.status == "open",
        )
    ) or 0

    investigated = db.scalar(
        select(func.count(Incident.id))
        .where(
            Incident.application_id == application_id,
            Incident.status == "investigated",
        )
    ) or 0

    resolved = db.scalar(
        select(func.count(Incident.id))
        .where(
            Incident.application_id == application_id,
            Incident.status == "resolved",
        )
    ) or 0

    return {
        "total_events": total_events,
        "total_incidents": total_incidents,
        "open_incidents": open_incidents,
        "investigated_incidents": investigated,
        "resolved_incidents": resolved,
    }
