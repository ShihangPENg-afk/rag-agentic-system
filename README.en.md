# rag-agentic-system

> **Chinese README:** [README.md](README.md)

An **Agentic RAG** PDF Q&A system with **industrial equipment health prediction**: upload a PDF, chunk and embed text, build an in-process FAISS index, and run a LangGraph Agent with tool calling, multi-step reasoning, and conversational memory. The `check_machine_health` tool calls a separate industrial prediction service over HTTP, enabling dual pipelines for document Q&A and sensor risk prediction.

The project includes a **FastAPI** backend, **Streamlit** UI, **PostgreSQL** structured logging, **Docker** deployment, **RAGAS** offline evaluation, and **dual-service integration** acceptance—suitable as an engineering POC for RAG + Agent + industrial AI scenarios.

See [docs/architecture.md](docs/architecture.md) for architecture details and [docs/industrial_demo_guide.md](docs/industrial_demo_guide.md) for the industrial integration demo.

---

## Related GitHub Repositories

| Repository | GitHub | Description |
|------------|--------|-------------|
| **rag-agentic-system** | https://github.com/ShihangPENg-afk/rag-agentic-system | This repo: Agentic RAG, Streamlit, PostgreSQL |
| **predictive-maintenance-mini** | https://github.com/ShihangPENg-afk/predictive-maintenance-mini | Industrial ML training & inference API (`:8010`) |
| **llm-finetune-for-manufacturing** | https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing | LoRA fine-tuning experiment (**not integrated** yet) |

The three repositories are **independent in code and deployment**. For local dual-service testing, clone them as **sibling directories** (e.g. `pythonProject1/rag-agentic-system` next to `pythonProject1/predictive-maintenance-mini`). See [4.1 Dual-service stack](#41-dual-service-stack-rag-agentic-system--predictive-maintenance-mini).

---

## Demo Video

End-to-end demo (PDF Q&A, Debug Trace, PostgreSQL history, equipment health tab, Agent calling `check_machine_health`):

| Platform | Content |
|----------|---------|
| **Baidu Pan** | File `rag-demo.mp4` · [Link](https://pan.baidu.com/s/1G3FDGbw7h37hDuddjUFpRg) · Code `iqcq` |
| **Written walkthrough (no video)** | Follow [docs/ui_demo_guide.md](docs/ui_demo_guide.md) and [docs/industrial_demo_guide.md](docs/industrial_demo_guide.md) |

> The video is a full screen recording. The written guides cover the same capabilities and work well for international viewers or local acceptance without video access.

---

## Highlights

| Area | Implementation |
|------|----------------|
| **RAG / Agent** | LangGraph multi-step reasoning; `retrieve_chunks` / `list_headings` / `count_tables`; `/ask/` vs classic RAG `/ask_rag/` |
| **Web** | FastAPI REST + Streamlit wide layout; four-panel Debug Trace |
| **DevOps** | Docker Compose (API + PostgreSQL); `make smoke` (4 steps); `make stack-up` dual-service stack |
| **RAG evaluation** | RAGAS offline eval (faithfulness **0.875**, answer_relevancy **0.886**, 3/10 sample baseline) |
| **Industrial AI** | [predictive-maintenance-mini](https://github.com/ShihangPENg-afk/predictive-maintenance-mini) (`:8010`); sensor → `prediction` / `risk_level` / ops advice |
| **Agent tools** | `check_machine_health` via HTTP to `/predict`; observable in `debug.tool_trace`; decoupled from PDF Q&A |

**Sibling repositories:**

- **[predictive-maintenance-mini](https://github.com/ShihangPENg-afk/predictive-maintenance-mini)** — EDA, RandomForest training, FastAPI inference, Docker
- **[llm-finetune-for-manufacturing](https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing)** — PDF → LoRA fine-tuning (**not integrated** into this repo)

---

## Core Features

| Feature | Description |
|---------|-------------|
| **PDF upload & chunking** | Single/batch upload, `%PDF` magic check, pypdf parsing, deduplication |
| **FAISS retrieval** | DashScope TextEmbedding + in-process FAISS similarity search |
| **Agent tools** | LangGraph-driven: `retrieve_chunks`, `list_headings`, `count_tables`, **`check_machine_health`** |
| **Industrial integration** | Agent tool + Streamlit tab; HTTP to predictive-maintenance-mini `/predict` |
| **Multi-step reasoning** | `planner` decomposes sub-questions; `evaluator` aggregates evidence |
| **Conversation memory** | Client sends `history`; server keeps last 3 turns |
| **Debug trace** | `debug: true` on `/ask/` returns `tool_trace`, `reasoning_snapshot`, `retrieved_evidence_preview` |
| **Streamlit UI** | PDF upload, multi-turn chat, Debug Trace, QA history, equipment health tab |
| **PostgreSQL hybrid persistence** | Document metadata + QA logs in DB; **vectors stay in FAISS** |
| **Docker** | `Dockerfile` + `docker-compose.yml` with PostgreSQL and healthcheck |
| **RAGAS evaluation** | Offline script scores Agent answers; JSON/Markdown reports |

**Q&A endpoints:**

- `POST /ask/` — LangGraph Agent (default)
- `POST /ask_rag/` — Classic RAG baseline (retrieve → prompt → generate)

---

## Tech Stack

| Category | Technology |
|----------|------------|
| Web | **FastAPI**, Uvicorn |
| UI | **Streamlit** (`ui/streamlit_app.py`, HTTP to backend) |
| Agent | **LangGraph**, LangChain OpenAI-compatible API |
| Vectors | **FAISS**, NumPy (in-process, **not in PostgreSQL**) |
| Metadata / logs | **PostgreSQL 16**, SQLAlchemy (`documents`, `qa_logs`) |
| LLM / embeddings | **DashScope** (`qwen-plus`, TextEmbedding) via OpenAI-compatible API |
| Containers | **Docker**, **Docker Compose** (`rag-agentic-system` + `postgres`) |
| Industrial (external) | **[predictive-maintenance-mini](https://github.com/ShihangPENg-afk/predictive-maintenance-mini)** — scikit-learn, FastAPI `:8010` |
| Quality | **RAGAS** (Faithfulness, ResponseRelevancy) |
| Text | pypdf, langchain-text-splitters |

---

## Architecture Overview

```
Upload PDF → chunk / embed → FAISS index (in-process)
              │                    ↓
              │          POST /ask/ (Agent, default)
              │                    ↓
              │   planner → agent ⇄ tools → evaluator → answer
              │                    ↓
              │    retrieve_chunks / list_headings / count_tables
              │    check_machine_health ──HTTP──► predictive-maintenance-mini :8010
              ↓
     PostgreSQL documents (metadata)
                              ↓
                    qa_logs (QA history + optional debug JSON)

Streamlit UI (:8501) ── API_BASE_URL → rag-agentic-system :8000
                    └── HEALTH_API_URL → predictive-maintenance-mini :8010

                    POST /ask_rag/ (classic RAG fallback)
```

**Hybrid persistence:** Vectors and chunk text live in **process memory** (FAISS + `kb_registry`). PostgreSQL stores only document metadata (`documents`) and Agent QA logs (`qa_logs`). After restart, history is queryable but FAISS is lost—re-upload PDFs to Q&A again. See [docs/architecture.md](docs/architecture.md).

---

## Quick Start

### Requirements

- Python 3.10+
- Network access to Alibaba Cloud DashScope

### 0. Clone (first time)

```bash
git clone https://github.com/ShihangPENg-afk/rag-agentic-system.git
git clone https://github.com/ShihangPENg-afk/predictive-maintenance-mini.git   # dual-service
git clone https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing.git      # optional LoRA experiment
```

### 1. Install dependencies

```bash
cd rag-agentic-system
make install
# or: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

### 2. Environment variables

```bash
make env-init    # copies .env.example → .env only if .env missing
make env-check   # verifies DASHSCOPE_API_KEY is set
```

```env
DASHSCOPE_API_KEY=your_api_key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

POSTGRES_USER=ragagent
POSTGRES_PASSWORD=ragagent_secret
POSTGRES_DB=ragagent
DATABASE_URL=postgresql+psycopg2://ragagent:ragagent_secret@localhost:5432/ragagent

HEALTH_API_URL=http://127.0.0.1:8010
```

> Do not `cp .env.example .env` over an existing `.env`—it will overwrite your real API key.

### 2.1 Start PostgreSQL

PostgreSQL stores metadata and QA logs only—not vectors.

```bash
docker compose up postgres -d
```

Or use `make docker-up` to start PostgreSQL and the API together.

### 3. Run locally

```bash
make run
# or: python main.py
```

API docs: http://127.0.0.1:8000/docs

Core RAG works even if PostgreSQL is temporarily unavailable; metadata and QA logs will not persist.

### 4. Streamlit UI

**Terminal 1 — backend:**

```bash
make env-check && make run
```

**Terminal 2 — Streamlit:**

```bash
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
export API_BASE_URL=http://127.0.0.1:8000
export HEALTH_API_URL=http://127.0.0.1:8010
streamlit run ui/streamlit_app.py
```

Browser: http://127.0.0.1:8501. See [docs/ui_demo_guide.md](docs/ui_demo_guide.md) and [docs/industrial_demo_guide.md](docs/industrial_demo_guide.md).

### 4.1 Dual-service stack (rag-agentic-system + predictive-maintenance-mini)

| Service | Port | Role |
|---------|------|------|
| **rag-agentic-system** | `8000` | PDF upload, Agent Q&A, PostgreSQL metadata |
| **predictive-maintenance-mini** | `8010` | Sensor features → health classification |

```bash
# inside rag-agentic-system repo (requires ../predictive-maintenance-mini)
make stack-up
make stack-verify
```

Or step by step:

```bash
cd ../predictive-maintenance-mini && make docker-up && sleep 5 && make docker-verify
cd ../rag-agentic-system && make env-check && make docker-up && make stack-verify
```

**Streamlit (terminal C):**

```bash
cd rag-agentic-system
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
export API_BASE_URL=http://127.0.0.1:8000
export HEALTH_API_URL=http://127.0.0.1:8010
make ui
```

> **Port conflict:** predictive-maintenance-mini must listen on **8010**, not 8000. If `make smoke` reports the wrong service on 8000, stop conflicting processes.

> **Docker → industrial API:** Default `HEALTH_API_URL=http://host.docker.internal:8010`. On Linux, add `extra_hosts: ["host.docker.internal:host-gateway"]` if needed.

### 5. Docker

```bash
make env-init && make env-check
make docker-up
# or: docker compose up --build
```

FAISS is in-process—re-upload PDFs after container restart. PostgreSQL records persist.

Streamlit runs on the host separately (section 4).

### 6. Smoke test

```bash
make smoke
make smoke BASE_URL=http://127.0.0.1:8000 PDF=test.pdf
```

Full run typically takes 2–4 minutes (DashScope embedding). Success: `Smoke Test 全部通过 (4/4)`.

---

## API Examples

### Upload PDF — `POST /upload_pdf/`

```bash
curl -X POST "http://127.0.0.1:8000/upload_pdf/" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@test.pdf"
```

### Agent Q&A — `POST /ask/`

```bash
curl -X POST "http://127.0.0.1:8000/ask/" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is this document mainly about?",
    "knowledge_base_id": "<ID from upload>",
    "history": [],
    "debug": true
  }'
```

| Field | Type | Description |
|-------|------|-------------|
| `question` | string | Current question |
| `knowledge_base_id` | string | Knowledge base ID |
| `history` | array | Multi-turn history (`user` / `assistant`); last 3 turns kept |
| `debug` | bool | Return tool trace and reasoning snapshot |

### Classic RAG — `POST /ask_rag/`

Same payload as `/ask/` without Agent tools; response `mode` is `"rag"`.

### Equipment health — Agent triggers `check_machine_health`

Requires industrial API on `:8010` (see [4.1](#41-dual-service-stack-rag-agentic-system--predictive-maintenance-mini)).

```bash
curl -X POST "http://127.0.0.1:8000/ask/" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Assess equipment health: temperature=75, pressure=1.2, vibration=0.6, speed=118.0, humidity=48.0",
    "knowledge_base_id": "<KB ID>",
    "history": [],
    "debug": true
  }'
```

### Other endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/upload_pdfs/` | Batch PDF upload |
| `GET` | `/knowledge_bases` | In-memory knowledge bases |
| `GET` | `/documents/` | Recent uploads (PostgreSQL) |
| `GET` | `/qa_logs/?knowledge_base_id=...` | QA history (PostgreSQL) |
| `DELETE` | `/knowledge_base/{kb_id}` | Delete in-memory KB only |
| `DELETE` | `/clear_all_knowledge_bases` | Clear all in-memory KBs |

---

## RAGAS Evaluation

Offline evaluation with [RAGAS](https://docs.ragas.io/). Samples: `evals/ragas_samples.json` (10 hand-crafted Q&A pairs).

### Baseline (`test.pdf`, 2026-06-10, 3/10 samples)

> Full snapshot: [docs/ragas_baseline.md](docs/ragas_baseline.md)

Config: `RAGAS_LIMIT=3`, `RAGAS_METRICS=all`, `RAGAS_TIMEOUT=600`

| Metric | Score |
|--------|-------|
| **faithfulness** | **0.8750** |
| **answer_relevancy** | **0.8858** |

### Run commands

```bash
make eval-ragas
make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600
```

### Report paths

| File | Content |
|------|---------|
| `docs/ragas_baseline.md` | Committed baseline snapshot |
| `evals/out/ragas_report.json` | Full JSON from local runs (gitignored) |
| `evals/out/ragas_report.md` | Markdown from local runs |

---

## Relationship with predictive-maintenance-mini

Independent repo: EDA → RandomForest → FastAPI (`:8010`). **Not production-grade.**

- **Agent tool:** `check_machine_health` → `POST {HEALTH_API_URL}/predict`
- **Streamlit tab:** Direct HTTP to `:8010`
- **Decoupled:** No shared process or database

---

## Relationship with llm-finetune-for-manufacturing

Independent LoRA fine-tuning experiment. **LoRA weights are not integrated**—generation uses DashScope `qwen-plus`. RAGAS baseline scores apply to this repo only.

---

## Known Limitations

- **In-process FAISS only** — Re-upload PDFs after restart; PostgreSQL does not store vectors or chunk text.
- **Hybrid PostgreSQL** — Metadata + QA logs persist; retrieval cannot be restored from DB alone.
- **Industrial model is a demo baseline** — Not for production decisions.
- **LoRA not integrated** — Online DashScope API only.
- **Slow faithfulness eval** — RAGAS Faithfulness uses extra LLM calls; serial mode for large runs.
- **Heuristic structure tools** — `list_headings` / `count_tables` use chunk text rules, not native PDF structure.
- **Request-scoped memory** — Client passes `history`; no automatic cross-session context injection.
- **Classic RAG skips QA logs** — Only `POST /ask/` writes to `qa_logs`.
- **No production auth or cloud deployment** — Local POC only.

---

## Roadmap

- [ ] FAISS / vector persistence
- [ ] Integrate LoRA weights from llm-finetune-for-manufacturing
- [ ] Expand RAGAS sample set
- [x] Basic CI — GitHub Actions offline tests + compile check (`.github/workflows/ci.yml`)
- [ ] Smoke / RAGAS in CI (requires DashScope secret)

---

## Project Structure

```
rag-agentic-system/
├── main.py
├── config.py
├── Makefile
├── Dockerfile / docker-compose.yml
├── LICENSE
├── README.md / README.en.md
├── app/          # API, agent, services, tools, vectordb, db
├── ui/           # Streamlit
├── evals/        # RAGAS scripts & samples
├── tests/        # Offline unit tests (CI)
├── scripts/      # smoke, stack, demo checks
└── docs/         # architecture, guides, baseline report
```

## Common Commands

```bash
make help
make run
make docker-up
make stack-up
make stack-verify
make smoke
make eval-ragas
make ui
```

## License

This project is licensed under the [MIT License](LICENSE).
