# Rabia

Streaming chat app with a LangChain Deep Agents backend, Groq, and Supabase checkpointing.

## Stack

- Next.js + Tailwind + shadcn/ui
- FastAPI (`api/`)
- `deepagents` (`create_deep_agent`)
- Groq (`ChatGroq`)
- Supabase Postgres (`AsyncPostgresSaver`)

## Setup

1. Copy `.env.example` to `.env.local` and fill in:

```bash
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-20b
DATABASE_URL=
```

Use a Supabase **session pooler** URI (port `5432`) when possible.

2. Install and run locally:

```bash
npm install
pip install -r api/requirements.txt

# terminal 1 (from repository root)
uvicorn api.index:app --reload --host 127.0.0.1 --port 8000

# terminal 2
PYTHON_API_URL=http://127.0.0.1:8000 npm run dev
```

Or use `npx vercel dev` with the same env vars.

## Deploy (Vercel)

1. Import this repo in Vercel.
2. Set `GROQ_API_KEY` and `DATABASE_URL` in project environment variables.
3. Deploy. The Python function is `api/index.py` (`maxDuration: 60`).

## API

`POST /api`

```json
{ "message": "Hello", "thread_id": "uuid" }
```

SSE events: `status`, `token`, `error`, `done`.
