# Pixel AI Office

Pixel AI Office is a web project for a 2D pixel-art workspace where AI agents
will eventually receive tasks, work, and collaborate. TASK 01 establishes only
the frontend and backend foundations.

## Technology Stack

- Frontend: React, Vite, and TypeScript
- Backend: Python 3.12, FastAPI, and Uvicorn
- Styling: Plain CSS

## Project Structure

```text
pixel-ai-office/
|-- frontend/              # React and Vite application
|   |-- public/
|   `-- src/
|       |-- app/           # Root application component
|       |-- components/    # Reusable UI components
|       `-- styles/        # Global styles
|-- backend/
|   `-- app/               # FastAPI application package
|-- .gitignore
`-- README.md
```

## Prerequisites

- Windows 11 and PowerShell
- Node.js LTS with npm
- Python 3.12 via the Windows Python launcher

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

## Backend Setup

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Development URLs

- Frontend: http://localhost:5173
- API health check: http://localhost:8000/health
- API documentation: http://localhost:8000/docs

## Current Development Status

TASK 01 is initialized with a responsive static application shell and a
FastAPI health endpoint. The office engine and future application features are
not implemented yet.

chạy BE
# Terminal 1
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
chạy FE
# Terminal 2
cd frontend
npm run dev