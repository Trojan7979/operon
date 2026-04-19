# NexusCore

NexusCore is a multi-agent enterprise productivity assistant:

> A multi-agent AI system that helps users manage tasks, schedules, and information by interacting with multiple tools and data sources.

It combines a React demo UI with a FastAPI backend that models agent orchestration, workflow execution, structured data retrieval, meetings intelligence, and MCP-style tool integrations.

## The Problem

Enterprise work is fragmented across chat, calendars, approvals, notes, compliance checks, and internal systems. NexusCore is designed to reduce the overhead of switching between those systems by giving users a single multi-agent interface that can:

- route requests to the right specialist agent
- retrieve context before actions are taken
- coordinate approvals, follow-ups, and workflow steps
- summarize meetings and extract actions without losing auditability

In short, it addresses the pain point of operational work being spread across too many disconnected tools and handoffs.

## What It Demonstrates

- a primary orchestration agent coordinating specialist sub-agents
- persistent conversation, agent task, run, handoff, and tool invocation records
- JWT-based API authentication with refresh-token sessions
- workflow orchestration for task routing, approvals, onboarding, and escalations
- meetings analysis with Vertex AI extraction and heuristic fallback
- **real Google Meet scheduling** via the MCP Python SDK when `ENABLE_GOOGLE_CALENDAR_MCP=true` — wired into both the REST endpoint and the orchestrator chat path
- LLM-powered intent routing with a strict typed JSON schema, relative date conversion, and deterministic fallback
- frontend-to-backend API interaction through a live demo interface

## Multi-Agent Model

The backend uses an orchestrator-led collaboration model:

- `Nexus Orchestrator`
  Handles planning, routing, and final responses
- `MeetIntel Core`
  Handles meeting and transcript-oriented analysis
- `Data Fetcher v4`
  Retrieves operational context and records
- `Action Exec Alpha`
  Executes workflow and scheduling actions
- `Shield Verifier`
  Performs validation, audit, and compliance checks

The orchestrator persists:

- conversations
- conversation messages
- agent tasks
- agent runs
- agent handoffs
- tool invocations

This makes the collaboration visible both in backend APIs and in the frontend chat demo.

## Current Demo Highlights

- login from the frontend against the FastAPI backend
- live command center dashboard backed by seeded enterprise data
- workflow execution with steps, agent ownership, and audit logs
- agent chat that shows:
  - assistant response
  - agent collaboration handoffs
  - invoked tools
  - frontend API activity trace
- meeting scheduling via chat or REST — Google Meet events created with real Calendar invites when MCP is enabled
- transcript analysis and action item extraction (Vertex AI + heuristic fallback)
- RBAC and SLA demo views

## Repo Layout

- `frontend/`
  React + Vite demo UI
- `backend/`
  FastAPI backend, SQLite persistence, seeded demo data, orchestration logic
- `DEPLOYMENT.md`
  deployment notes

## Local Run

Backend:

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open:

- Frontend: `http://localhost:5173/`
- Backend OpenAPI docs: `http://127.0.0.1:8000/docs`

Default frontend API base:

- `http://127.0.0.1:8000/api/v1`

If needed, set `VITE_API_BASE_URL` for the frontend runtime.

## Demo Credentials

- `admin@nexuscore.ai` / `admin123`
- `sarah@nexuscore.ai` / `sarah123`
- `james@nexuscore.ai` / `james123`
- `rupam@nexuscore.ai` / `rupam123`
- `maria@nexuscore.ai` / `maria123`

## Demo Script

Good prompts for showing agent collaboration in the UI:

- `Start a new workflow for vendor approval and schedule a follow-up`
- `Run a compliance check for the procurement request`
- `Find employee onboarding status for Priya Nair`
- `Summarize the latest meeting and extract action items`
- `Schedule a Google Meet called Q2 Planning on 2026-04-20 at 3:00 PM with sarah@nexuscore.ai`

Best UI demo flow:

1. Log in from the frontend.
2. Open `Agent Chat`.
3. Send a workflow or compliance prompt.
4. Show:
   - the response message
   - `Agent Collaboration`
   - `Tool Activity`
   - `API Activity`
5. Switch to `Meetings` — schedule a Google Meet from chat and verify the Calendar invite.
6. Run `Analyze` on a meeting to show Vertex AI transcript extraction.
7. Switch to `Live Simulator` or `Workflows` to show backend-backed workflow state.

## API Surface

Current backend includes production-shaped endpoints for:

- auth (`POST /api/v1/auth/login`, `POST /api/v1/auth/token`, `GET /api/v1/auth/me`)
- chat and conversations (`POST /api/v1/chat/message`, `GET /api/v1/chat/conversations`)
- workflows (`GET /api/v1/workflows`, `POST /api/v1/workflows/{id}/advance`)
- agents (`GET /api/v1/agents`, `GET /api/v1/agents/{id}/metrics`, `POST /api/v1/agents/{id}/task`)
- meetings (`GET /api/v1/meetings`, `POST /api/v1/meetings`, `POST /api/v1/meetings/{id}/analyze`)
- metrics, audit logs, RBAC, SLA
- MCP tool status/connectivity (`GET /api/v1/mcp/tools`, `POST /api/v1/mcp/tools/{name}/connect`)

> The primary chat endpoint is `POST /api/v1/chat/message`. A silent alias at `POST /api/v1/chat` also works but is hidden from Swagger (`include_in_schema=False`).

OpenAPI docs are available at `http://127.0.0.1:8000/docs` when the backend is running.

## Tech Stack

- Frontend: React, Vite, Tailwind CSS
- Backend: python, FastAPI, SQLAlchemy, SQLite
- Auth: JWT bearer tokens + refresh session records
- AI: Vertex AI with Gemini 2.5 Flash
- Deployment target: Cloud Run

## Agent's Toolkit

This implementation uses a custom multi-agent orchestration layer instead of a framework like LangChain, AutoGen, or CrewAI.

- Orchestration: custom `AgentCoordinator` service for typed intent routing, handoffs, workflow creation, specialist-agent coordination, and draft-state continuation
- LLM gateway: Vertex AI via `google-cloud-aiplatform` and `google-generativeai`
- API layer: FastAPI
- Data modeling and persistence: Pydantic, SQLAlchemy, SQLite
- Auth and sessions: `python-jose`, `passlib`, JWT access tokens, refresh-session records
- Agent observability: persisted conversations, agent runs, tasks, handoffs, tool invocations, and audit logs exposed through the agent API
- Tool integrations: MCP Python SDK (`mcp[cli]`) plus a database-backed MCP-style tool registry for demo-scoped tools
- External scheduling path: Google Calendar APIs via `google-api-python-client` and OAuth helpers; Calendar sends attendee invites when `sendUpdates=all`
- Employee directory: SQLAlchemy-backed employee records used to resolve group meeting attendees such as `@all_employees` and `@dept:Engineering`
- Frontend demo client: React, Vite, Tailwind CSS

## Assumptions & Guardrails

- The system uses a fixed agent catalog and fixed allowed intents, so the model cannot invent arbitrary agent roles or routing targets.
- LLM-based routing uses a typed JSON schema prompt (field types, `YYYY-MM-DD` date format, `HH:MM` / `H:MM AM/PM` time format, boolean flags). If the response is malformed or Vertex AI is unavailable, the backend falls back to deterministic rule-based routing with no degradation.
- The final response prompt explicitly tells the model to ground answers in tool outcomes and collaboration history and not invent IDs, data, or completed actions.
- When available context is incomplete, the backend asks for clarification before proceeding — enforced for meeting scheduling (title, provider, date, time all required), onboarding, workflows, compliance checks, and retrieval requests.
- Actions are bounded by registered tools and persisted tool invocations rather than open-ended execution. The agent can only act through known MCP-style integrations exposed by the backend, and agent-task assignment rejects unavailable agents.
- Conversation-scoped access checks prevent users from assigning agent tasks into conversations they do not own.
- Safe fallback behavior is built in: if Vertex AI is unavailable, chat falls back to deterministic orchestration copy; meeting analysis falls back to heuristic keyword extraction.
- Real external side effects are currently limited to Google Calendar / Google Meet scheduling. This path is active in **both** the orchestrator chat flow and the direct REST API when `ENABLE_GOOGLE_CALENDAR_MCP=true`; SMTP meeting-email settings are configuration-only until a separate notification sender is wired in. The rest of the tool surface (Task Manager, Notes Workspace, Compliance Vault, Knowledge Base) remains demo-scoped with stub registry responses.
- Meeting attendee guardrails filter invite targets to real-looking email addresses, add the requester as organizer/attendee when needed, and resolve group markers from active employee records before creating Calendar events.
- Employee updates enforce unique lowercased emails and allowed status transitions (`onboarding -> active/terminated`, `active -> terminated`, `terminated -> terminated`) unless an explicit force override is used.
- On MCP failure the backend logs a `warning` audit entry and continues with a DB-only meeting record — the booking is never silently dropped.

## Notes

- The multi-agent system is orchestrator-led and fully persistence-backed (conversations, runs, tasks, handoffs, tool invocations, audit logs).
- The Google Calendar MCP path uses the MCP Python SDK (`stdio_client`) to spawn `app.mcp_servers.google_calendar` as a subprocess — the same pattern that would be used to connect any future real MCP server.
- Other tool servers (`mcp_task_server`, `mcp_notes_server`, etc.) are registered in `config.py` and ready to be connected using the same stdio pattern once the server modules are built.
- This repository is the initial iteration and is intended for demonstration and continued development.
