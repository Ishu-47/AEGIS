import hashlib
import os
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
    Request,
    Response,
    Cookie,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError

from app.database import Base, engine, get_db
from app.models import (
    Application,
    LogEvent,
    Incident,
    IncidentEvent,
    InvestigationReport,
    KnowledgeDocument,
    EvaluationCase,
    User,
    UserSession,
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
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if item.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ApplicationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(default="", max_length=500)
    platform: str = Field(default="Other", max_length=50)


class DashboardAuthPayload(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


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


class KnowledgeDocCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    doc_type: str = Field(
        pattern=r"^(runbook|postmortem|architecture|sop)$",
    )
    tags: list[str] = Field(default_factory=list)


class KnowledgeIndexRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    source_type: str = Field(default="runbook", max_length=50)
    source_uri: str | None = Field(default=None, max_length=2000)
    replace_existing: bool = False


class KnowledgeDocUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    doc_type: str | None = None
    tags: list[str] | None = None


class EvalCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    events_json: list[dict]
    expected_root_cause: str
    expected_services: list[str]
    expected_severity: str


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
        or raw.get("order_id")
        or raw.get("orderId")
        or raw.get("transaction_id")
        or raw.get("transactionId")
    )
    if not correlation_id:
        # Plain-text logs commonly carry request/order/trace identifiers in
        # their message rather than in a structured field. Extract only
        # explicitly named identifiers; never guess from arbitrary numbers.
        identifier_match = re.search(
            r"\b(?:trace|request|correlation|order|transaction|session)_?id\s*[=: ]\s*[\'\"]?([A-Za-z0-9._:-]+)",
            message,
            re.IGNORECASE,
        )
        if identifier_match:
            correlation_id = identifier_match.group(1)

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
        r"^\s*(?P<timestamp>(?:\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?|\S+))\s+"
        r"(?P<severity>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)\s+"
        r"(?:\[(?P<bracket_service>[\w.$-]+)\]|(?P<service>[\w.$-]+))"
        r"\s+(?:[-:]\s*)?(?P<message>.*)$",
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
            current_multiline["service"] = (
                current_multiline.get("bracket_service")
                or current_multiline.get("service")
                or "unknown"
            )
            current_multiline.pop("bracket_service", None)
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


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

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
        # 11-section report
        "incident_summary": report.incident_summary,
        "observed_error": report.observed_error,
        "affected_service": report.affected_service,
        "downstream_services": report.downstream_services,
        "timeline_summary": report.timeline_summary,
        "probable_root_cause": report.probable_root_cause,
        "alternative_hypotheses": report.alternative_hypotheses,
        "supporting_evidence": report.supporting_evidence,
        "evidence_mapping": report.evidence_mapping,
        "stack_trace_locations": report.stack_trace_locations,
        "confidence": report.confidence,
        "confidence_factors": report.confidence_factors,
        "historical_context_summary": (
            ((report.raw_llm_response or {}).get("report") or {}).get("historical_context_summary", [])
            if isinstance((report.raw_llm_response or {}).get("report") if isinstance(report.raw_llm_response, dict) else None, dict)
            else []
        ),
        "uncertainty_notes": report.uncertainty_notes,
        "remediation_steps": report.remediation_steps,
        "verification_steps": report.verification_steps,
        # Metadata
        "investigation_steps": report.investigation_steps,
        "events_analyzed": report.events_analyzed,
        "events_cited": report.events_cited,
        "model_used": report.model_used,
        "created_at": report.created_at,
    }


def serialize_knowledge_doc(doc: KnowledgeDocument) -> dict[str, Any]:
    return {
        "id": doc.id,
        "application_id": doc.application_id,
        "title": doc.title,
        "content": doc.content,
        "doc_type": doc.doc_type,
        "tags": doc.tags,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def serialize_eval_case(case: EvaluationCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "name": case.name,
        "description": case.description,
        "events_json": case.events_json,
        "expected_root_cause": case.expected_root_cause,
        "expected_services": case.expected_services,
        "expected_severity": case.expected_severity,
        "last_score": case.last_score,
        "last_result": case.last_result,
        "last_run_at": case.last_run_at,
        "created_at": case.created_at,
    }


# ---------------------------------------------------------------------------
# Dashboard authentication (opaque server-side sessions + CSRF protection)
# ---------------------------------------------------------------------------

SESSION_COOKIE = "aegis_session"
CSRF_COOKIE = "aegis_csrf"
SESSION_TTL = timedelta(days=14)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return "pbkdf2_sha256$310000$" + salt.hex() + "$" + derived.hex()


def _verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt_hex, digest = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)).hex()
        return secrets.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False


def current_dashboard_user(
    request: Request,
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    if not session_cookie:
        raise HTTPException(status_code=401, detail="Please sign in.")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == _hash_secret(session_cookie)))
    now = datetime.now(timezone.utc)
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    request.state.aegis_session = session
    return user


def require_csrf(request: Request, user: User = Depends(current_dashboard_user), db: Session = Depends(get_db)) -> User:
    session = getattr(request.state, "aegis_session", None)
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token")
    if not session or not cookie_token or not header_token:
        raise HTTPException(status_code=403, detail="CSRF validation failed. Refresh and try again.")
    if not secrets.compare_digest(cookie_token, header_token) or not secrets.compare_digest(_hash_secret(cookie_token), session.csrf_token_hash):
        raise HTTPException(status_code=403, detail="CSRF validation failed. Refresh and try again.")
    return user


def _issue_session(db: Session, user: User, response: Response) -> None:
    raw_session = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    db.add(UserSession(
        user_id=user.id,
        token_hash=_hash_secret(raw_session),
        csrf_token_hash=_hash_secret(csrf),
        expires_at=datetime.now(timezone.utc) + SESSION_TTL,
    ))
    db.commit()
    secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    response.set_cookie(SESSION_COOKIE, raw_session, httponly=True, secure=secure, samesite="lax", max_age=int(SESSION_TTL.total_seconds()), path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=secure, samesite="lax", max_age=int(SESSION_TTL.total_seconds()), path="/")


@app.get("/api/auth/status")
def auth_status(db: Session = Depends(get_db), session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if session_cookie:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == _hash_secret(session_cookie)))
        if session:
            expires = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
            account = db.get(User, session.user_id) if expires > datetime.now(timezone.utc) else None
            if account:
                return {"authenticated": True, "email": account.email, "registration_available": True}
    return {"authenticated": False, "email": None, "registration_available": True}


@app.post("/api/auth/register")
def register_dashboard_user(payload: DashboardAuthPayload, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if len(payload.password) < 10:
        raise HTTPException(status_code=422, detail="Password must contain at least 10 characters.")
    existing = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")
    user = User(email=email, password_hash=_password_hash(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")
    db.refresh(user)
    _issue_session(db, user, response)
    return {"authenticated": True, "email": user.email}


@app.post("/api/auth/login")
def login_dashboard_user(payload: DashboardAuthPayload, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    _issue_session(db, user, response)
    return {"authenticated": True, "email": user.email}


@app.post("/api/auth/logout")
def logout_dashboard_user(response: Response, request: Request, db: Session = Depends(get_db)):
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == _hash_secret(raw)))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"authenticated": False}


def owned_application(db: Session, application_id: str, user: User) -> Application:
    app_record = db.get(Application, application_id)
    if app_record is None or app_record.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Application not found.")
    return app_record


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
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    api_key = secrets.token_urlsafe(32)
    application = Application(
        name=payload.name.strip(),
        description=payload.description.strip(),
        platform=payload.platform.strip() or "Other",
        owner_user_id=user.id,
        api_key_hash=hash_api_key(api_key),
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return {
        "id": application.id,
        "name": application.name,
        "description": application.description,
        "platform": application.platform,
        "created_at": application.created_at,
        "api_key": api_key,
    }


@app.get("/api/applications")
def list_applications(
    user: User = Depends(current_dashboard_user),
    db: Session = Depends(get_db),
):
    applications = db.scalars(
        select(Application).where(Application.owner_user_id == user.id)
        .order_by(Application.created_at.desc())
    ).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "platform": item.platform,
            "created_at": item.created_at,
        }
        for item in applications
    ]


@app.delete("/api/applications/{application_id}")
def delete_application(application_id: str, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    item = owned_application(db, application_id, user)
    db.delete(item)
    db.commit()
    return {"status": "deleted"}


@app.post("/api/applications/{application_id}/rotate-key")
def rotate_application_key(application_id: str, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    item = owned_application(db, application_id, user)
    api_key = secrets.token_urlsafe(32)
    item.api_key_hash = hash_api_key(api_key)
    db.commit()
    return {"id": item.id, "api_key": api_key}


# ---------------------------------------------------------------------------
# Dashboard session-protected API
# ---------------------------------------------------------------------------

@app.post("/api/dashboard/applications/{application_id}/logs")
async def dashboard_upload_logs(
    application_id: str,
    content: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    owned_application(db, application_id, user)
    if file is not None:
        filename = (file.filename or "").lower()
        if not filename.endswith((".log", ".txt", ".json")):
            raise HTTPException(status_code=400, detail="Upload a .log, .txt, or .json file.")
        data = await file.read(1_000_001)
        if len(data) > 1_000_000:
            raise HTTPException(status_code=413, detail="Maximum upload size is 1 MB.")
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="The uploaded file must be UTF-8 text.")
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="Paste logs or select a file.")
    events = parse_logs(content)
    records = save_events(db, application_id, events)
    grouped = group_events(db, application_id, records)
    return {
        "accepted": len(records),
        "events": [serialize_event(item) for item in records],
        "incidents_created": grouped.created_count,
        "incidents_updated": grouped.updated_count,
        "incidents_touched": len(grouped.incidents),
    }


@app.get("/api/dashboard/applications/{application_id}/incidents")
def dashboard_list_incidents(application_id: str, user: User = Depends(current_dashboard_user), db: Session = Depends(get_db)):
    owned_application(db, application_id, user)
    items = db.scalars(
        select(Incident)
        .options(selectinload(Incident.report))
        .where(Incident.application_id == application_id)
        .order_by(Incident.last_seen.desc())
    ).all()
    return {"incidents": [serialize_incident(item) for item in items]}


def dashboard_owned_incident(db: Session, incident_id: int, user: User) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    owned_application(db, incident.application_id, user)
    return incident


@app.get("/api/dashboard/incidents/{incident_id}")
def dashboard_get_incident(incident_id: int, user: User = Depends(current_dashboard_user), db: Session = Depends(get_db)):
    incident = db.scalars(
        select(Incident)
        .options(selectinload(Incident.report))
        .where(Incident.id == incident_id)
    ).first()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    owned_application(db, incident.application_id, user)
    event_ids = db.scalars(
        select(IncidentEvent.log_event_id).where(IncidentEvent.incident_id == incident_id)
    ).all()
    events = (
        db.scalars(
            select(LogEvent)
            .where(
                LogEvent.application_id == incident.application_id,
                LogEvent.id.in_(event_ids),
            )
            .order_by(LogEvent.timestamp.asc(), LogEvent.id.asc())
        ).all()
        if event_ids else []
    )

    # Older AEGIS records may have an incident row/event_count but no junction
    # rows (e.g. incidents created before incident_events was populated).
    # Recover a bounded, application-scoped timeline instead of rendering an
    # apparently empty incident. The buffer captures nearby causal context.
    events_recovered = False
    if not events:
        from datetime import timedelta
        first_seen = incident.first_seen
        last_seen = incident.last_seen
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        events = db.scalars(
            select(LogEvent)
            .where(
                LogEvent.application_id == incident.application_id,
                LogEvent.timestamp >= first_seen - timedelta(minutes=5),
                LogEvent.timestamp <= last_seen + timedelta(minutes=5),
            )
            .order_by(LogEvent.timestamp.asc(), LogEvent.id.asc())
            .limit(500)
        ).all()
        events_recovered = bool(events)

    result = serialize_incident(incident)
    result["events"] = [serialize_event(event) for event in events]
    result["events_recovered"] = events_recovered
    result["event_count"] = max(incident.event_count or 0, len(events)) if events_recovered else incident.event_count
    if incident.report:
        result["report"] = serialize_report(incident.report)
    return result


@app.post("/api/dashboard/incidents/{incident_id}/investigate")
def dashboard_investigate(incident_id: int, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    incident = dashboard_owned_incident(db, incident_id, user)
    report = investigate_incident(db, incident)
    return {"status": "completed", "report": serialize_report(report)}


@app.patch("/api/dashboard/incidents/{incident_id}/status")
def dashboard_update_status(incident_id: int, status: str, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    valid = {"open", "investigating", "investigated", "resolved", "dismissed"}
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {', '.join(sorted(valid))}")
    incident = dashboard_owned_incident(db, incident_id, user)
    incident.status = status
    db.commit()
    return serialize_incident(incident)


@app.get("/api/dashboard/applications/{application_id}/stats")
def dashboard_stats(application_id: str, user: User = Depends(current_dashboard_user), db: Session = Depends(get_db)):
    owned_application(db, application_id, user)
    total_events = db.scalar(select(func.count(LogEvent.id)).where(LogEvent.application_id == application_id)) or 0
    total_incidents = db.scalar(select(func.count(Incident.id)).where(Incident.application_id == application_id)) or 0
    open_incidents = db.scalar(select(func.count(Incident.id)).where(Incident.application_id == application_id, Incident.status == "open")) or 0
    investigated = db.scalar(select(func.count(Incident.id)).where(Incident.application_id == application_id, Incident.status == "investigated")) or 0
    resolved = db.scalar(select(func.count(Incident.id)).where(Incident.application_id == application_id, Incident.status == "resolved")) or 0
    knowledge_docs = db.scalar(select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.application_id == application_id)) or 0
    return {"total_events": total_events, "total_incidents": total_incidents, "open_incidents": open_incidents, "investigated_incidents": investigated, "resolved_incidents": resolved, "knowledge_documents": knowledge_docs}


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

    knowledge_docs = db.scalar(
        select(func.count(KnowledgeDocument.id))
        .where(KnowledgeDocument.application_id == application_id)
    ) or 0

    return {
        "total_events": total_events,
        "total_incidents": total_incidents,
        "open_incidents": open_incidents,
        "investigated_incidents": investigated,
        "resolved_incidents": resolved,
        "knowledge_documents": knowledge_docs,
    }


# ---------------------------------------------------------------------------
# Dashboard knowledge-base lifecycle (pgvector, application scoped)
# ---------------------------------------------------------------------------

@app.post("/api/dashboard/applications/{application_id}/knowledge")
def dashboard_index_knowledge(application_id: str, payload: KnowledgeIndexRequest,
                              user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    owned_application(db, application_id, user)
    try:
        from app.rag import index_document
        return index_document(
            db=db, application_id=application_id, title=payload.title.strip(),
            content=payload.content, source_type=payload.source_type.strip() or "runbook",
            source_uri=payload.source_uri, replace_existing=payload.replace_existing,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Knowledge indexing failed: {str(exc)[:300]}")


@app.get("/api/dashboard/applications/{application_id}/knowledge")
def dashboard_list_knowledge(application_id: str, user: User = Depends(current_dashboard_user),
                             db: Session = Depends(get_db)):
    owned_application(db, application_id, user)
    from app.rag import list_documents
    return {"documents": list_documents(db, application_id)}


@app.delete("/api/dashboard/applications/{application_id}/knowledge")
def dashboard_delete_knowledge(application_id: str, title: str,
                               user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    owned_application(db, application_id, user)
    from app.rag import delete_document
    return {"deleted_chunks": delete_document(db, application_id, title), "title": title}


# ---------------------------------------------------------------------------
# Routes — Knowledge Base
# ---------------------------------------------------------------------------

@app.post("/api/applications/{application_id}/knowledge")
def create_knowledge_doc(
    application_id: str,
    payload: KnowledgeDocCreate,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    get_authorized_application(db, application_id, x_api_key)

    from app.knowledge import create_document

    doc = create_document(
        db=db,
        application_id=application_id,
        title=payload.title,
        content=payload.content,
        doc_type=payload.doc_type,
        tags=payload.tags,
    )

    return serialize_knowledge_doc(doc)


@app.get("/api/applications/{application_id}/knowledge")
def list_knowledge_docs(
    application_id: str,
    doc_type: str | None = None,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    get_authorized_application(db, application_id, x_api_key)

    from app.knowledge import list_documents

    docs = list_documents(db, application_id, doc_type=doc_type)
    return {"documents": [serialize_knowledge_doc(d) for d in docs]}


@app.get("/api/knowledge/{doc_id}")
def get_knowledge_doc(
    doc_id: int,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    doc = db.get(KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    get_authorized_application(db, doc.application_id, x_api_key)
    return serialize_knowledge_doc(doc)


@app.put("/api/knowledge/{doc_id}")
def update_knowledge_doc(
    doc_id: int,
    payload: KnowledgeDocUpdate,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    doc = db.get(KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    get_authorized_application(db, doc.application_id, x_api_key)

    from app.knowledge import update_document

    updated = update_document(
        db=db,
        doc=doc,
        title=payload.title,
        content=payload.content,
        doc_type=payload.doc_type,
        tags=payload.tags,
    )

    return serialize_knowledge_doc(updated)


@app.delete("/api/knowledge/{doc_id}")
def delete_knowledge_doc(
    doc_id: int,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    doc = db.get(KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    get_authorized_application(db, doc.application_id, x_api_key)

    from app.knowledge import delete_document
    delete_document(db, doc)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Routes — Evaluation
# ---------------------------------------------------------------------------

@app.post("/api/evaluation/cases")
def create_eval_case(
    payload: EvalCaseCreate,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    from app.evaluation import create_evaluation_case

    case = create_evaluation_case(
        db=db,
        name=payload.name,
        description=payload.description,
        events_json=payload.events_json,
        expected_root_cause=payload.expected_root_cause,
        expected_services=payload.expected_services,
        expected_severity=payload.expected_severity,
    )

    return serialize_eval_case(case)


@app.get("/api/evaluation/cases")
def list_eval_cases(user: User = Depends(current_dashboard_user), db: Session = Depends(get_db)):
    from app.evaluation import list_evaluation_cases

    cases = list_evaluation_cases(db)
    return {"cases": [serialize_eval_case(c) for c in cases]}


@app.get("/api/evaluation/cases/{case_id}")
def get_eval_case(case_id: int, user: User = Depends(current_dashboard_user), db: Session = Depends(get_db)):
    case = db.get(EvaluationCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return serialize_eval_case(case)


@app.delete("/api/evaluation/cases/{case_id}")
def delete_eval_case(case_id: int, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    from app.evaluation import delete_evaluation_case

    case = db.get(EvaluationCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")

    delete_evaluation_case(db, case)
    return {"status": "deleted"}
