# 🚀 FinAgent: Intelligent Financial Decision Assistant

> An AI-powered personal finance assistant that answers natural-language money questions by securely calling **real backend tools**. It never hallucinates numbers, handles your budget dynamically, and even works offline without an LLM!

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Tech Stack](https://img.shields.io/badge/stack-React%20%7C%20FastAPI%20%7C%20Supabase-blue)
![AI Powered](https://img.shields.io/badge/AI-OpenAI%20SDK-purple)

## 🌟 What is it?
FinAgent is not just another chatbot. It is a highly structured, dual-path agentic system:
- **Agentic Path**: Ask complex questions like *"Can I afford a ₹15,000 phone?"* and the AI will use its tool-calling capabilities to check your balance, your upcoming expenses, and your savings rate to give you a definitive answer.
- **Structured Path**: Say *"I spent ₹500 on dinner,"* and the Intent Router bypasses the heavy LLM logic, instantly extracting the data and pushing it securely to your database, updating your budget in milliseconds.

The golden rule of FinAgent: **The LLM chooses *which* tools to call, but Python does *all* the maths.**

## ✨ Core Features
- **💬 Conversational Expense Logging**: Just type what you spent. We do the math and categorization.
- **🚨 Real-Time Budget Alerts**: Get instantly notified when a transaction pushes you past a category's budget threshold.
- **🤖 Tool-Calling Agent Loop**: Natively supports any OpenAI-compatible model (HuggingFace, Groq, Together AI) to read live balances, upcoming expenses, and investment goals.
- **🔒 Supabase Auth & RLS**: Secure email/password authentication. Row Level Security ensures that even if an API endpoint is compromised, users can only ever access their own financial data.
- **⚡ Deterministic Fallback**: No API key? No problem. The backend seamlessly falls back to a deterministic, regex-based router that simulates the AI perfectly for local testing and demos.

---

## 🛠️ Tech Stack
- **Frontend**: React, TypeScript, Vite, TailwindCSS
- **Backend**: FastAPI, SQLAlchemy (PostgreSQL/SQLite)
- **Authentication & DB**: Supabase (Postgres with RLS)
- **AI Integration**: Open-source friendly `openai` Python SDK (currently configured for high-speed inference via Groq/HuggingFace)

---

## 🚀 Quickstart

### 1. Backend Setup (FastAPI)
Navigate to the backend directory and set up your Python environment:
```bash
cd backend
python -m venv .venv 
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Set up your environment variables:
```bash
cp .env.example .env
```
Inside `.env`, you can optionally add your `LLM_API_KEY` (e.g., from Groq, HuggingFace, or OpenAI). If you leave it blank, the system will use the **Deterministic Fallback mode**.

Seed the database and start the server:
```bash
python -m app.seed            # Creates finagent.db with demo data
uvicorn app.main:app --reload --port 8000
```
*API Docs available at http://127.0.0.1:8000/docs*

### 2. Frontend Setup (React + Vite)
Open a new terminal and navigate to the frontend:
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser. 
*(If you used the `app.seed` script, you can log in with the demo account provided in your Supabase dashboard or create a new one!)*

---

## 🧠 Architecture Deep Dive

```text
User Question
   │
   ▼ POST /api/ai/chat
   │
┌──▼─────────────────────────────┐
│ 1. Intent Router (LLM Call #1) │
│ Classifies: Expense vs Query   │
└─┬────────────────────────────┬─┘
  │                            │
  ▼                            ▼
STRUCTURED PATH          AGENTIC PATH
(Fast, Deterministic)    (Tool-Calling Loop)
- Extracts values        - Fetches User Profile
- Writes to DB           - Runs Budget Tools
- Recomputes Budget      - Calculates affordability
- Triggers Alerts        - Analyzes spending history
  │                            │
  ▼                            ▼
┌─┴────────────────────────────┴─┐
│       STRUCTURED JSON          │
│ {answer, metrics, insights}    │
└──────────────┬─────────────────┘
               │
               ▼
     Beautiful React Dashboard
```

## 🛡️ Security & Privacy
Financial data is highly sensitive. We ensure security through:
1. **Delegated Authentication**: We don't store passwords. All authentication is safely handled via Supabase JWTs.
2. **Stateless Backend**: The FastAPI backend validates the JWT signature on *every* request.
3. **Database RLS**: In production, Supabase Row Level Security ensures `user_id = auth.uid()` is enforced at the database level.
4. **No PII to LLMs**: The AI only sees category totals and amounts, never your name, email, or credentials.

---
*Built with ❤️ for intelligent financial planning.*
