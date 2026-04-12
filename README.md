# NexusCore

NexusCore is a multi-agent enterprise productivity assistant:

> A multi-agent AI system that helps users manage tasks, schedules, and information by interacting with multiple tools and data sources.

It combines a React demo UI with a FastAPI backend that models agent orchestration, workflow execution, structured data retrieval, meetings intelligence, and MCP-style tool integrations.

## What It Demonstrates

- a primary orchestration agent coordinating specialist sub-agents
- persistent conversation, agent task, run, handoff, and tool invocation records
- JWT-based API authentication with refresh-token sessions
- workflow orchestration for task routing, approvals, onboarding, and escalations
- meetings analysis and extracted action items
- MCP-style tool integration boundaries for calendar, task, notes, knowledge, and compliance systems
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
- meeting scheduling and meeting analysis
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

Best UI demo flow:

1. Log in from the frontend.
2. Open `Agent Chat`.
3. Send a workflow or compliance prompt.
4. Show:
   - the response message
   - `Agent Collaboration`
   - `Tool Activity`
   - `API Activity`
5. Switch to `Live Simulator` or `Workflows` to show backend-backed workflow state.

## API Surface

Current backend includes production-shaped Phase 1 endpoints for:

- auth
- chat and conversations
- workflows
- agents
- meetings
- metrics
- audit logs
- MCP tool status/connectivity

OpenAPI docs are available at `/docs` when the backend is running.

## Tech Stack

- Frontend: React, Vite, Tailwind CSS
- Backend: python, FastAPI, SQLAlchemy, SQLite
- Auth: JWT bearer tokens + refresh session records
- AI: Vertex AI with Gemini 2.5 Flash
- Deployment target: Cloud Run

## Notes

- The current multi-agent system is orchestrator-led and persistence-backed.
- MCP is represented through a registry boundary today and can be upgraded to real MCP SDK-based integrations next.
- This repository serves as the initial version of this iteration and is intended for demonstration purposes, including API and UI walkthroughs.
