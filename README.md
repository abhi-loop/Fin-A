# Intelligent Financial Decision Agent (FinAgent)

AI-powered personal finance assistant. The AI answers natural-language money
questions by calling **real backend tools** — it never invents numbers.

## Run it

### Backend (FastAPI + SQLite)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY (optional)
python -m app.seed            # creates finagent.db with demo data
uvicorn app.main:app --reload --port 8000
```
Docs at http://localhost:8000/docs

### Frontend (Vite + React + TS + Tailwind)
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```
Open http://localhost:5173 — login with `demo@finagent.in` / `demo1234`.

## Architecture
```
User question
   -> POST /api/ai/chat
   -> agent/agent.py  (LLM with tool calling)
   -> tools/finance_tools.py  (queries the DB, does the arithmetic)
   -> structured JSON {answer, metrics, insights, sources}
   -> frontend renders metric cards + insights
```
The LLM chooses *which* tools to call. Python does *all* the maths.
Without an API key the agent falls back to a deterministic rule-based
router that uses the same tool layer — the demo always works.
