# AEGIS — AI-Powered Incident Investigation Platform

AEGIS is an incident investigation platform that ingests application logs, groups related events, reconstructs incident timelines, and uses an evidence-grounded AI workflow to investigate probable causes and recommend diagnostic actions.

It is designed to help developers move from a collection of service logs to an explainable incident report. AEGIS distinguishes observed failures from unverified root-cause hypotheses and keeps remediation recommendations advisory; it does not execute fixes.

> **Project status:** Functional MVP / portfolio project. The backend has a deterministic regression suite and an evaluation fixture set. Live Neon, Gemini, LangSmith, browser end-to-end, deployment, load, and penetration testing must be completed in the target environment before describing the system as production-ready.

## Contents

- [What AEGIS does](#what-aegis-does)
- [Architecture](#architecture)
- [Investigation workflow](#investigation-workflow)
- [Evidence and confidence](#evidence-and-confidence)
- [Technology stack](#technology-stack)
- [Project structure](#project-structure)
- [Local setup](#local-setup)
- [Database migrations](#database-migrations)
- [Running the application](#running-the-application)
- [Knowledge base and RAG](#knowledge-base-and-rag)
- [Testing and evaluation](#testing-and-evaluation)
- [Security and data handling](#security-and-data-handling)
- [Known limitations and next steps](#known-limitations-and-next-steps)

## What AEGIS does

- **Application onboarding:** dashboard accounts can register and manage their own applications.
- **Log ingestion:** accepts structured log events and supported plain-text log formats through dashboard and API-key-protected integration routes.
- **Parsing and correlation:** extracts timestamps, severity, service names, and explicit identifiers such as `order_id`, `request_id`, `trace_id`, and `transaction_id` from supported plain-text messages.
- **Incident grouping:** groups related events using explicit correlation identifiers and includes matching contextual events in the incident timeline.
- **Incident investigation:** analyzes the incident's linked events, service patterns, correlation chains, historical incidents, and application-scoped knowledge.
- **Evidence-backed reports:** presents observed errors, a chronological timeline, service impact, ranked hypotheses, supporting event references, confidence factors, remediation suggestions, and verification steps.
- **Knowledge source lifecycle:** supports indexing, listing, replacing, and deleting application-scoped knowledge sources through authenticated dashboard endpoints.
- **Observability:** can send investigation traces to LangSmith when configured.

## Architecture

```mermaid
flowchart TD
    A[Applications / Services] --> B[Log Ingestion API]
    B --> C[Parser and Normalizer]
    C --> D[Incident Correlation]
    D --> E[(PostgreSQL)]
    F[Dashboard User] --> G[React Dashboard]
    G --> H[FastAPI Dashboard API]
    H --> E
    H --> I[LangGraph Investigation]
    I --> J[Event and Pattern Analysis]
    I --> K[Historical Incident Retrieval]
    I --> L[Application-scoped RAG]
    L --> M[(pgvector Knowledge Chunks)]
    J --> N[Gemini Analysis]
    K --> N
    M --> N
    N --> O[Evidence Validation and Guardrails]
    O --> P[Investigation Report]
    P --> E
    I -. optional tracing .-> Q[LangSmith]
    G --> P
```

### Main components

| Component | Responsibility |
|---|---|
| React dashboard | Registration/login, application selection, log ingestion, incident list and detail views, knowledge-source management, investigation reports. |
| FastAPI backend | Authentication, application ownership, ingestion endpoints, incident APIs, knowledge APIs, investigation orchestration. |
| PostgreSQL | Dashboard users, sessions, applications, logs, incidents, incident-event relationships, reports, and knowledge metadata. |
| pgvector | Persistent vector storage and application-scoped semantic retrieval for knowledge chunks. |
| LangGraph | Orchestrates evidence collection, pattern analysis, retrieval, hypothesis generation, evidence validation/refinement, and report generation. |
| Gemini | Generates candidate explanations and remediation suggestions from supplied evidence and context. |
| LangSmith (optional) | Tracing for investigation workflows when credentials and tracing configuration are provided. |

## Investigation workflow

The active dashboard investigation entry point is `backend/app/investigation.py` (called by the API in `backend/app/main.py`). `backend/app/agent.py` is a separate workflow and is not the dashboard's primary investigation entry point.

1. **Collect evidence:** fetches the log events linked to the incident and builds a timestamp-ordered timeline.
2. **Analyze patterns:** extracts severity counts, service participation, repeated messages, stack traces, and explicit correlation chains.
3. **Retrieve context:** retrieves relevant historical incidents and application-scoped knowledge chunks where available.
4. **Generate hypotheses:** asks Gemini to propose ranked possible explanations using the collected evidence and context.
5. **Validate evidence:** checks cited event/document references against the supplied evidence and evaluates whether the explanation is sufficiently supported.
6. **Refine when needed:** performs a bounded refinement/retrieval round when the evidence is insufficient.
7. **Generate and persist report:** produces the incident report, with deterministic reconstruction of event-backed timeline and supporting evidence.

If the provider or retrieval path is unavailable, the backend has a conservative deterministic fallback. A fallback report is not equivalent to a successful live-Gemini investigation.

## Evidence and confidence

AEGIS separates three concepts that should not be conflated:

- **First observed failing service:** the service that emitted the earliest observed error in the collected timeline.
- **Root-cause service/mechanism:** the underlying cause, which may remain unknown without sufficient telemetry.
- **Correlated downstream error services:** later services with error events that share an explicit correlation identifier with the first observed failure. Correlation indicates a related failure sequence; it does not by itself prove causation.

The report tracks distinct event references, citation accuracy, report event coverage, hypothesis evidence coverage, and the proportion of hypotheses with verified citations. Duplicate references should not inflate coverage. Historical incidents are precedent/context, not direct evidence for the current incident.

Confidence is a heuristic assessment based on evidence quality and validation. It is **not a statistically calibrated probability** and should not be marketed as one. A single HTTP 503 or connection timeout without supporting telemetry should produce an appropriately uncertain report rather than an invented definitive cause.

## Technology stack

- **Frontend:** React 19, Vite, React Router, Axios, Tailwind CSS v4, Lucide React.
- **Backend:** Python, FastAPI, Uvicorn, Pydantic.
- **Database:** PostgreSQL (Neon-compatible), SQLAlchemy, Alembic, pgvector.
- **AI / orchestration:** Google Gemini, LangGraph, LangSmith (optional tracing).
- **Testing:** pytest, HTTPX, deterministic evaluation fixtures.

## Project structure

```text
AEGIS/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI routes and application wiring
│   │   ├── investigation.py        # Active dashboard investigation workflow
│   │   ├── agent.py                # Separate evidence-grounding workflow
│   │   ├── models.py               # SQLAlchemy models
│   │   └── ...
│   ├── migrations/                 # Alembic configuration and revisions
│   ├── tests/                      # Backend regression tests
│   ├── evaluation/
│   │   └── sample_dataset.json     # Ten deterministic incident fixtures
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/                        # React application
│   ├── package.json
│   └── ...
├── services/
├── .gitignore
└── README.md
```

## Local setup

### Prerequisites

- Python 3.11+ recommended.
- Node.js and npm compatible with the versions required by the frontend lockfile.
- PostgreSQL with the `vector` extension enabled (the project has been used with Neon PostgreSQL).
- A Gemini API key for provider-backed investigations. The deterministic fallback can run without it, but it does not provide live LLM analysis.
- Optional LangSmith API key for tracing.

### 1. Clone and configure

```powershell
git clone https://github.com/Ishu-47/AEGIS
cd AEGIS
```

Create `backend/.env` locally. Do not commit this file. Example configuration:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
GEMINI_API_KEY=your-gemini-api-key
COOKIE_SECURE=false
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Optional LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-langsmith-api-key
LANGCHAIN_PROJECT=aegis-incident-investigation
```

Use the exact database URL supplied by your PostgreSQL provider. Keep credentials private. For HTTPS deployment, set `COOKIE_SECURE=true` and replace the local CORS origins with the exact deployed frontend origin(s).

The current investigation module uses the Gemini API key from `GEMINI_API_KEY`. The configured model in the current source is `gemini-3.5-flash-lite`.

### 2. Install backend dependencies

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

If PowerShell blocks activation, use the Python executable inside `.venv` directly or adjust the local execution policy according to your environment's security policy.

## Database migrations

Back up the database before applying schema changes. From the `backend` directory with the virtual environment active:

```powershell
python -m alembic current
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
```

The latest migration revision included in this project is `e7f1a2b3c4d5`. It adds missing enhanced investigation-report columns while preserving existing report data. Confirm the actual current revision after migration; do not manually stamp the database or delete/recreate it to bypass migration errors.

The PostgreSQL server must have pgvector available and the database role must have the required extension/table permissions. If `vector` is not enabled, ask the database administrator/provider to enable it before running the relevant migration.

## Running the application

Open two terminals from the repository root.

**Terminal 1 — backend:**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend:**

```powershell
cd frontend
npm ci
npm run dev
```

Open the Vite URL shown in the terminal (normally `http://localhost:5173`). Register at `/register`, then log in at `/login` on subsequent visits.

Useful frontend commands:

```powershell
npm run build
npm run lint
```

## Knowledge base and RAG

AEGIS stores knowledge chunks in PostgreSQL/pgvector and filters retrieval by the current `application_id` so one application's knowledge is not mixed with another application's context.

The dashboard knowledge API supports these operations:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/dashboard/applications/{application_id}/knowledge` | Index a knowledge source. |
| `GET` | `/api/dashboard/applications/{application_id}/knowledge` | List indexed sources and chunk counts. |
| `DELETE` | `/api/dashboard/applications/{application_id}/knowledge?title=...` | Delete a source's chunks. |

To replace an existing source with the same title, include `"replace_existing": true` in the POST JSON body. These dashboard endpoints require an authenticated session, CSRF protection for state-changing requests, and application ownership.

Do not index secrets, access tokens, credentials, or unredacted customer-sensitive data. Review retention and access requirements before using real production logs or documents.

## Testing and evaluation

Run backend tests from `backend`:

```powershell
python -m pytest -q
python -m compileall -q app tests
```

The project archive's final local verification recorded **26 passing backend tests** and successful Python compilation. Re-run these commands on your machine after installing dependencies; results can vary with environment and dependency versions.

The deterministic fixture set is located at `backend/evaluation/sample_dataset.json` and contains ten scenarios:

1. Payment gateway timeout.
2. Database connection-pool exhaustion.
3. Authentication service failure.
4. Cascading multi-service failure.
5. Single-event HTTP 503 with insufficient evidence.
6. Redis outage.
7. Isolation of unrelated requests.
8. Out-of-order log events.
9. Repeated errors.
10. Prompt injection embedded in a log message.

The regression tests validate deterministic collection, attribution, correlation, and evidence-handling behavior. They are **not** ten measured live-Gemini benchmark results. To evaluate provider-backed quality, run each fixture through the configured Gemini/Neon workflow and score root-cause correctness, event coverage, citation precision, false correlations, uncertainty handling, and recommendation usefulness.

## Security and data handling

- Dashboard passwords are stored as salted PBKDF2-SHA256 hashes.
- Dashboard sessions use opaque `HttpOnly` cookies; session tokens are stored hashed server-side and sessions expire after 14 days.
- State-changing dashboard operations use CSRF validation.
- Dashboard application access is scoped to the authenticated owner.
- External ingestion/legacy integration routes use `X-API-Key`; API keys are stored as hashes and should be rotated if lost.
- Set `COOKIE_SECURE=true` behind HTTPS and configure exact CORS origins for deployment.
- Registration is open in this MVP. Before public production exposure, add rate limiting, email verification, password reset/account recovery, and an abuse-prevention strategy.
- Add log redaction, retention controls, and a review process for sensitive data. Treat logs and retrieved documents as untrusted input.
- LangSmith traces may contain prompts and diagnostic context. Enable tracing only after reviewing data-handling requirements.
- Remediation suggestions are advisory; AEGIS does not automatically execute them.

## Known limitations and next steps

The current project is a portfolio/MVP implementation, not a production-certified incident-management platform. Important follow-up work includes:

- Run full live integration tests against the configured Neon database, Gemini API, and LangSmith project.
- Run frontend production build and browser end-to-end tests.
- Measure live-model investigation quality across the ten fixtures and maintain a labeled benchmark.
- Calibrate confidence against labeled outcomes before interpreting it probabilistically.
- Add rate limiting, email verification, password reset, account recovery, and optional team/application sharing.
- Add configurable log redaction, retention/deletion policies, and stronger tenant-isolation/security testing.
- Move long-running embedding/indexing/investigation work to a durable background worker and queue before scaling.
- Perform deployment, load, backup/restore, and penetration testing before production use.

## Contributing

Keep changes small and covered by regression tests. Never commit `.env`, API keys, database credentials, customer logs, or unredacted incident data. When changing SQLAlchemy models, add and test an Alembic migration. When changing report fields or evidence structures, update the API/frontend contract and add tests for both structured and legacy report formats.
