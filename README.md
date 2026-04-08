# NexusCore

Multi-agent productivity assistant built for the hackathon prompt:

> Build a multi-agent AI system that helps users manage tasks, schedules, and information by interacting with multiple tools and data sources.

NexusCore demonstrates:

- a primary orchestration agent coordinating specialized sub-agents
- structured data storage and retrieval through a backend database
- API-first workflows for onboarding, meetings, RBAC, SLA monitoring, and chat
- MCP-style tool integrations for task routing, calendar operations, notes, HR, and procurement
- Vertex AI integration with Gemini for live agent responses and meeting intelligence

## Repo Layout

- `frontend/`
  React + Vite application used for the live demo UI
- `backend/`
  FastAPI backend with seeded structured data, multi-agent coordination, and Vertex-backed features

## Current Demo Capabilities

- JWT-authenticated login flow from frontend to backend
- live dashboard, workflows, meetings, onboarding, RBAC, and SLA views
- workflow advancement with agent/tool activity and audit logs
- meeting scheduling plus extracted meeting intelligence
- Vertex-powered chat responses with safe fallback behavior
- seeded enterprise demo data for realistic product walkthroughs

## Local Run

Backend:

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app
```

Frontend:

```powershell
cd frontend
npm run dev
```

Open:

- Frontend: `http://localhost:5173/`
- Backend docs: `http://127.0.0.1:8000/docs`

## Demo Credentials

- `admin@nexuscore.ai` / `admin123`
- `sarah@nexuscore.ai` / `admin123`
- `james@nexuscore.ai` / `admin123`

## Tech Stack

- Frontend: React, Vite, Tailwind CSS
- Backend: FastAPI, SQLAlchemy, SQLite
- AI: Vertex AI with Gemini 2.5 Flash
- Deployment target: Cloud Run

## Notes

- Additional backend implementation detail lives in [backend/README.md](./backend/README.md).
