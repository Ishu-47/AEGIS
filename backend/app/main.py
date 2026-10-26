import hashlib
import json
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
from sqlalchemy import select, UniqueConstraint
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Application, LogEvent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Importing app.models registers the tables with Base.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AEGIS API",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=2000)


class LogEventInput(BaseModel):
    timestamp: datetime | str | None = None
    severity: str = "INFO"
    service: str = "unknown"
    message: str
    raw_event: dict[str, Any] | None = None


class IngestRequest(BaseModel):
    application_id: str
    events: list[LogEventInput] = Field(max_length=500)


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

    return {
        "timestamp": parse_timestamp(timestamp),
        "severity": severity,
        "service": service,
        "message": message,
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

    # Otherwise, parse plain-text logs one line at a time.
    pattern = re.compile(
        r"^\s*(?P<timestamp>\S+)\s+"
        r"(?P<severity>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)"
        r"\s+(?P<service>[\w.$-]+)\s*[-:]\s*"
        r"(?P<message>.*)$",
        re.IGNORECASE,
    )

    events = []

    for line in content.splitlines():
        line = line.strip()

        if not line:
            continue

        match = pattern.match(line)

        if match:
            events.append(normalize_event(match.groupdict()))
        else:
            severity_match = re.search(
                r"\b(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)\b",
                line,
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
                        "message": line,
                    },
                    fallback_message=line,
                )
            )

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
            raw_event=event.get("raw_event"),
        )
        for event in events
    ]

    db.add_all(records)
    db.commit()

    for record in records:
        db.refresh(record)

    return records


def serialize_event(event: LogEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "application_id": event.application_id,
        "timestamp": event.timestamp,
        "severity": event.severity,
        "service": event.service,
        "message": event.message,
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "aegis-api"}


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

    return {
        "accepted": len(records),
        "events": [serialize_event(item) for item in records],
    }


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

    return {
        "accepted": len(records),
        "investigation_started": False,
    }


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
