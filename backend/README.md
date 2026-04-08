# NexusCore Backend

FastAPI backend for the multi-agent productivity assistant hackathon project.

## What It Covers

- Primary orchestrator plus specialized sub-agent service layer
- Structured relational data for workflows, meetings, employees, SLA records, audit logs, RBAC, and tools
- MCP-style tool registry for calendar, task, notes, search, and compliance integrations
- JWT authentication for the demo users already present in the frontend
- Vertex AI hook for meeting extraction with local heuristic fallback

## Run Locally

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open:

- API root docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/healthz`

## Demo Credentials

- `admin@nexuscore.ai` / `admin123`
- `sarah@nexuscore.ai` / `sarah123`
- `james@nexuscore.ai` / `james123`

## Suggested Frontend Integration

- `POST /api/v1/auth/login`
- `GET /api/v1/dashboard/overview`
- `GET /api/v1/workflows`
- `POST /api/v1/workflows/{workflow_id}/advance`
- `GET /api/v1/meetings`
- `POST /api/v1/meetings`
- `POST /api/v1/meetings/{meeting_id}/analyze`
- `GET /api/v1/employees`
- `POST /api/v1/employees`
- `GET /api/v1/rbac/users`
- `PATCH /api/v1/rbac/users/{user_id}`
- `GET /api/v1/sla/overview`
- `POST /api/v1/chat`
- `GET /api/v1/tools`

## Cloud Run Notes

- Replace SQLite with Cloud SQL Postgres via `DATABASE_URL`.
- Set `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_REGION`, and `ENABLE_VERTEX_AI=true`.
- Swap the stub MCP registry backing with real MCP server connectivity for production.
