# Halosight Knowledge API

AI-agnostic knowledge infrastructure system. A three-layer platform:

1. **Knowledge Capture Wizard** — AI-powered guided interview that structures company knowledge
2. **Knowledge Base + REST API** — Supabase (PostgreSQL + pgvector), multi-tenant, AI-agnostic
3. **AI Platform Connectors** — FastMCP (Claude), Custom GPT Action (ChatGPT), Google Extension (Gemini)

## Tech Stack

- **Frontend/Wizard UI:** Next.js — Vercel
- **Backend/API:** Python + FastAPI — Railway
- **Database:** Supabase (PostgreSQL + pgvector)
- **Auth:** Supabase Auth (per-company isolation)

## Project Structure

```
migrate_obsidian.py       # Phase 1: Obsidian vault → structured JSON
migration_output/         # Output of migration (119 docs, ~45,900 words)
```

## Phase 1: Obsidian Migration

Reads all `.md` files from the Halosight Knowledge Wiki vault and outputs structured JSON ready for Supabase ingestion.

```bash
python3 migrate_obsidian.py
# or with custom paths:
python3 migrate_obsidian.py --vault "/path/to/vault" --out "./migration_output"
```

Output fields per document: `title`, `folder`, `category`, `content`, `word_count`, `tags`, `source_file`
