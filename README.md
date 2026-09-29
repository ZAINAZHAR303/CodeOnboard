<div align="center">

# CodeOnboard

### Understand any codebase in minutes, not weeks.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Gemini](https://img.shields.io/badge/Gemini_API-AI_Powered-4285F4?logo=google&logoColor=white)](https://ai.google.dev)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**CodeOnboard** analyzes any public GitHub repository and generates a complete, interactive onboarding package — architecture docs, dependency graphs, learning paths, API maps, and an AI chat that answers questions from the actual source code.

[Features](#features) &bull; [Demo](#demo) &bull; [Architecture](#architecture) &bull; [Quick Start](#quick-start) &bull; [API Reference](#api-reference)

</div>

---

## The Problem

New developers joining an existing project typically need **2-6 weeks** before they ship meaningful changes. Documentation is missing or stale, the architecture lives in senior engineers' heads, and every *"where do I change X?"* question costs a teammate's time.

**CodeOnboard** eliminates that ramp-up.

---

## Features

### Static Analysis Engine (no AI required)
- **Multi-language import graph** — resolves Python, JavaScript/TypeScript, Java/Kotlin, and C/C++ imports into a directed dependency graph
- **API endpoint extraction** — detects routes from FastAPI, Flask, Django, Express, NestJS, Next.js, and Spring Boot
- **Pattern detection** — identifies testing frameworks, ORMs, auth layers, state management, CI/CD, and architecture style
- **File metrics** — LOC, function/class counts, import density, and hotspot scoring per file
- **Tech stack detection** — reads `package.json`, `requirements.txt`, `pom.xml`, `go.mod`, `Cargo.toml`, and 10+ other manifest formats

### 5 Parallel AI Documentation Agents
Each agent receives the full static analysis + relevant source files and generates grounded documentation:

| Agent | What it produces |
|---|---|
| **Architecture** | High-level overview, ASCII architecture diagram, component descriptions, request/data flow |
| **Modules** | Description and "read first" files for every module, plus starter questions |
| **Conventions** | Naming, structure, error handling, and testing conventions — each citing the source file as evidence |
| **How-to Guide** | Step-by-step instructions for the most common change type in *this specific repo* |
| **Learning Path** | Ordered day-1 reading plan with time estimates and progress tracking |

### Ticket Mapper
Paste a Jira/GitHub issue description and get:
- The **exact files** to modify or create (with relevance scores and reasons)
- **Tests** to update, **APIs** affected
- A step-by-step **implementation plan**
- **Risks** and an **effort estimate**
- All file paths are validated against the real repo — hallucinated paths are dropped

### Codebase Q&A Chat
Ask natural-language questions about the repo. The agent retrieves the most relevant files using **BM25 search** over paths and contents before answering, then cites its sources with clickable file links.

### Graceful Degradation
If the AI is unavailable (no API key, rate limited, or all models busy), every section falls back to static-analysis output instead of failing. The app is always usable.

---

## Demo

> Paste a GitHub URL, wait ~60-160 seconds, explore the dashboard.

### Dashboard Sections
| Section | Description |
|---|---|
| **Overview** | Stats, language distribution, architecture summary, entry points, hotspots, detected patterns |
| **Day-1 Reading Plan** | Ordered file list with time estimates and localStorage progress tracking |
| **Modules** | Expandable cards with descriptions, key files, and full file lists |
| **Dependency Graph** | Interactive React Flow visualization with dagre layout, module color coding, filtering |
| **File Explorer** | Recursive tree with search, expand/collapse, entry point and key file tags |
| **API Endpoints** | Filterable table with color-coded HTTP method badges and line-number links |
| **Add a Feature** | AI-generated step-by-step guide for contributing to this specific repo |
| **Conventions** | Coding standards inferred from the source, with cited evidence |
| **Ticket Mapper** | Map any ticket to files, tests, APIs, and an implementation plan |
| **Ask the Codebase** | Chat interface with suggested questions, source citations, and conversation history |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        React + Vite Frontend                        │
│  HomePage ─── DashboardPage (10 sections) ─── FileViewer (drawer)  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ /api/*
┌──────────────────────────────▼──────────────────────────────────────┐
│                        FastAPI Backend                               │
│                                                                      │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────┐  │
│  │ RepoIngester │  │ CodeAnalyzer  │  │     DocGenerator         │  │
│  │ git clone    │  │ import graph  │  │ 5 parallel AI agents     │  │
│  │ file scan    │──▶ modules       │──▶ architecture, modules,   │  │
│  │ tech stack   │  │ API routes    │  │ conventions, how-to,     │  │
│  │ entry points │  │ patterns      │  │ learning path            │  │
│  └──────────────┘  │ hotspots      │  └───────────┬──────────────┘  │
│                    └───────────────┘              │                  │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────▼──────────────┐  │
│  │   QAAgent    │  │ TicketMapper  │  │     GeminiClient         │  │
│  │ chat Q&A     │◀─│ ticket→files  │◀─│ retries, model failover  │  │
│  │ with sources │  │ validated     │  │ 429 cooldown, deadlines  │  │
│  └──────┬───────┘  └───────┬───────┘  │ bounded concurrency (3)  │  │
│         │                  │          └──────────────────────────┘  │
│  ┌──────▼──────────────────▼───────┐  ┌──────────────────────────┐  │
│  │      FileRetriever (BM25)       │  │    AnalysisStore         │  │
│  │ tokenize → stem → index → rank  │  │ JSON on disk + LRU cache │  │
│  └─────────────────────────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **BM25 over vector DB** — no external dependencies, no embedding costs, fast enough for repos up to 1500 files, and the custom tokenizer splits camelCase and applies stemming
- **Bounded concurrency (Semaphore)** — keeps Gemini free-tier quotas happy; 3 parallel calls with per-model 429 cooldown tracking
- **Model failover chain** — primary model → 4 fallbacks, tried in order, with deadline enforcement (no hanging requests)
- **Static analysis fallback** — every AI agent has a `_fallback_*` method that produces useful output from code analysis alone
- **Lazy-loaded dependency graph** — React Flow + dagre is 231KB; lazy-loaded so the main bundle stays at 365KB

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.11, FastAPI, httpx (async HTTP), Pydantic v2 |
| **AI** | Google Gemini API (gemini-3.8-flash + 4 fallback models) |
| **Frontend** | React 18, Vite, React Router v6, React Flow + dagre, react-markdown |
| **Search** | Custom BM25 implementation (tokenizer with camelCase splitting + stemming) |
| **Analysis** | Regex-based import resolution, API route extraction, pattern detection |

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Git
- [Gemini API key](https://ai.google.dev) (free tier works — optional, app works without it)

### 1. Clone & set up backend

```bash
git clone https://github.com/ZAINAZHAR303/CodeOnboard.git
cd CodeOnboard/backend
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # Windows: copy .env.example .env
# edit .env → set GEMINI_API_KEY
python main.py                 # → http://127.0.0.1:8000
```

### 2. Start frontend (development)

```bash
cd frontend
npm install
npm run dev                    # → http://localhost:5173 (proxies /api → :8000)
```

### 3. Single-server mode (production)

```bash
cd frontend && npm run build
cd ../backend && python main.py   # serves UI + API at http://127.0.0.1:8000
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Required for AI features (app works without it using static analysis) |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Primary Gemini model |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.6-flash,...` | Fallback chain for quota/overload errors |
| `LLM_MAX_CONCURRENCY` | `3` | Max parallel Gemini calls |
| `LLM_TIMEOUT_SECONDS` | `75` | Per-call timeout |
| `MAX_FILES` | `1500` | Max files to ingest per repo |
| `MAX_FILE_BYTES` | `200000` | Skip files larger than ~200KB |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/analyze` | Start analysis job `{repo_url, branch?, force?}` |
| `GET` | `/api/jobs/{job_id}` | Poll job status, stage, progress, and logs |
| `GET` | `/api/analyses` | List cached analyses |
| `GET` | `/api/analysis/{repo_id}` | Full onboarding package |
| `GET` | `/api/analysis/{repo_id}/file?path=` | File content + imports/imported-by |
| `POST` | `/api/chat` | `{repo_id, question, history}` → answer + sources |
| `POST` | `/api/map-ticket` | `{repo_id, ticket_description}` → files, tests, plan |
| `GET` | `/api/health` | Server status and configuration |

---

## Project Structure

```
CodeOnboard/
├── backend/
│   ├── main.py                  # FastAPI app, routes, SPA fallback
│   ├── config.py                # Settings from .env
│   ├── models/schemas.py        # Pydantic request/response models
│   └── services/
│       ├── repo_ingester.py     # Git clone, file scan, tech stack detection
│       ├── code_analyzer.py     # Import graph, modules, metrics, routes, patterns
│       ├── doc_generator.py     # 5 parallel AI documentation agents + fallbacks
│       ├── llm_client.py        # Gemini client: retries, failover, cooldowns
│       ├── retrieval.py         # BM25 file retriever with custom tokenizer
│       ├── qa_agent.py          # Grounded Q&A with source citations
│       ├── ticket_mapper.py     # Ticket → files/tests/APIs/plan mapper
│       ├── pipeline.py          # Async job orchestration with progress streaming
│       └── store.py             # JSON persistence + LRU workspace cache
├── frontend/src/
│   ├── pages/                   # HomePage, DashboardPage
│   ├── sections/                # 10 dashboard sections (see Features)
│   ├── components/              # FileViewer, Markdown, TechStackBadges, Icons
│   └── api/client.js            # API client functions
├── .env.example                 # Environment template
└── README.md
```

---

## How It Works

1. **You paste a GitHub URL** → the backend clones it (shallow, depth=1)
2. **File scanning** → reads up to 1500 source files across 40+ extensions, skips binaries and minified files
3. **Static analysis** → builds import graph, identifies modules, extracts API routes, computes complexity metrics, detects patterns
4. **AI documentation** → 5 agents run in parallel with bounded concurrency, each receiving the analysis + relevant source code
5. **Results cached** → subsequent visits load instantly from disk
6. **Interactive dashboard** → every file name is clickable, opening a viewer with syntax-highlighted source, imports, and imported-by lists

---

## License

[MIT](LICENSE)
