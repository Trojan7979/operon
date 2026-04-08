# NexusCore Frontend

React + Vite frontend for the NexusCore multi-agent productivity assistant demo.

## What This UI Covers

- login and session handling
- workflow simulator with decision detail views
- onboarding experience backed by live backend APIs
- meetings intelligence and extracted action items
- RBAC and SLA operational views
- agent chat with tool activity surfaced in the interface
- collaboration graph driven by live backend state

## Local Run

```powershell
cd frontend
npm install
npm run dev
```

Open:

- `http://localhost:5173/`

## Backend Dependency

The frontend is not useful by itself for the demo. It expects the backend API to be running at:

- `http://127.0.0.1:8000/api/v1`

Start the backend separately before testing login or live data flows.

## Main Frontend Files

- `src/App.jsx`
  app shell, auth/session wiring, and view orchestration
- `src/api.js`
  backend API client and session storage helpers
- `src/useBackendData.js`
  dashboard/workflow polling and shared app data hook
- `src/components/`
  primary product surfaces such as chat, onboarding, meetings, RBAC, SLA, and workflows

## Demo Notes

- Demo login: `admin@nexuscore.ai` / `admin123`
- If login shows `Failed to fetch`, the backend is usually not running
- On this Windows setup, `npm run dev` is the safest frontend command to use
