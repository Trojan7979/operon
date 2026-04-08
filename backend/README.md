# NexusCore Backend

FastAPI backend for the hackathon multi-agent productivity assistant. It exposes a seeded, API-first system for workflows, meetings, onboarding, RBAC, SLA monitoring, tool orchestration, and Vertex-powered agent responses.

## Current Status

What is already live:

- JWT-authenticated API for the frontend
- Seeded structured data for workflows, meetings, employees, audit logs, SLA records, users, agents, and MCP-style tool connections
- Primary orchestration layer plus specialized agent personas
- Live workflow advancement endpoint
- Live meetings scheduling and analysis
- Live RBAC and SLA endpoints
- Vertex AI-backed chat responses with safe fallback behavior
- Temporary low-cost Vertex probe endpoint for development testing

What is still demo-oriented:

- The MCP registry is stubbed and not yet connected to real external MCP servers
- SQLite is used locally instead of Cloud SQL / Postgres
- Some workflow intelligence is demo-enriched at serialization time to make the UI stronger for the recording

## Architecture Snapshot

- `app/api/routes`
  REST endpoints for auth, dashboard, workflows, meetings, employees, chat, RBAC, SLA, tools, and the temporary dev probe.
- `app/services/agents.py`
  Multi-agent coordination, tool routing, and Vertex-backed response generation.
- `app/services/workflows.py`
  Workflow advancement logic and tool invocation.
- `app/services/vertex.py`
  Shared Vertex AI gateway for meeting extraction and prompt generation.
- `app/db/models.py`
  SQLAlchemy models for all structured entities.
- `app/db/seed.py`
  Seeded demo data used by the frontend and Swagger flows.

## Local Run

From `backend/`:

```powershell
UV_CACHE_DIR="$PWD\.uv-cache" python -m uv venv .venv --clear
.venv\Scripts\activate
UV_CACHE_DIR="$PWD\.uv-cache" py -3.11 -m uv pip install --python .venv\Scripts\python.exe -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload
```

Open:

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Health check: `http://127.0.0.1:8000/healthz`

## Required Environment

Minimum local config:

```env
APP_ENV=development
DEBUG=true
DATABASE_URL=sqlite+aiosqlite:///./operon.db
SECRET_KEY=replace-this-before-deployment
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

Vertex-enabled local config:

```env
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_REGION=us-central1
VERTEX_AI_MODEL=gemini-2.5-flash
ENABLE_VERTEX_AI=true
ENABLE_DEV_LLM_ENDPOINT=true
```

## Google Auth For Vertex

For local development, use Application Default Credentials:

```powershell
& "C:\Users\taniy\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" auth application-default login
& "C:\Users\taniy\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" auth application-default set-quota-project YOUR_PROJECT_ID
```

If `gcloud` is unavailable or unreliable on the machine, set:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\service-account.json"
```

## Demo Credentials

- `admin@nexuscore.ai` / `admin123`
- `sarah@nexuscore.ai` / `sarah123`
- `james@nexuscore.ai` / `james123`
- `cassandra@nexuscore.ai` / `cassandra123`
- `rupam@nexuscore.ai` / `rupam123`
- `maria@nexuscore.ai` / `maria123`

## Main API Surface

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/token`
- `GET /api/v1/auth/me`
- `GET /api/v1/dashboard/overview`
- `GET /api/v1/workflows`
- `POST /api/v1/workflows/{workflow_id}/advance`
- `GET /api/v1/meetings`
- `POST /api/v1/meetings`
- `POST /api/v1/meetings/{meeting_id}/analyze`
- `GET /api/v1/employees`
- `POST /api/v1/employees`
- `GET /api/v1/rbac/users`
- `POST /api/v1/rbac/users`
- `PATCH /api/v1/rbac/users/{user_id}`
- `GET /api/v1/sla/overview`
- `POST /api/v1/chat`
- `GET /api/v1/tools`

Temporary development-only endpoint:

- `POST /api/v1/dev/llm-probe`

## Vertex Usage Today

Vertex AI is currently used in these places:

- `POST /api/v1/chat`
  Generates the final agent reply after tool routing.
- `POST /api/v1/meetings/{meeting_id}/analyze`
  Extracts actions, decisions, and escalations from the transcript when Vertex is enabled.
- `POST /api/v1/dev/llm-probe`
  Temporary low-cost endpoint for validating model access and response behavior.

If Vertex is unavailable, chat falls back to deterministic orchestration copy and meetings fall back to heuristic extraction.

## Recommended Demo Flow

For the recording, the strongest sequence is:

1. Log in as `admin@nexuscore.ai`
2. Show `Agent Chat` with a workflow or compliance prompt
3. Open `Workflow Simulator` and click into decision details
4. Open `Meetings` and run transcript analysis
5. Flash `SLA Monitor` and `RBAC` for breadth

## Cloud Run Readiness Notes

Before deployment:

- Replace SQLite with Cloud SQL Postgres
- Move `SECRET_KEY` to a secure secret source
- Disable or remove `ENABLE_DEV_LLM_ENDPOINT`
- Remove the temporary `/api/v1/dev/llm-probe` route
- Replace the stub MCP registry with real MCP connectivity
- Set production CORS origins
- Confirm Vertex IAM and quota on the deployment service account

Recommended production env direction:

```env
APP_ENV=production
DEBUG=false
ENABLE_VERTEX_AI=true
ENABLE_DEV_LLM_ENDPOINT=false
DATABASE_URL=postgresql+asyncpg://...
```
