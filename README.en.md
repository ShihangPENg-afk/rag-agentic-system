# rag-agentic-system

> **Chinese README:** [README.md](README.md)

---

## Project Overview

**rag-agentic-system** turns technical manuals into an **interactive Agentic RAG assistant**.

The project targets manufacturing documentation—operation manuals, SOPs, equipment specs, and other technical PDFs. Users upload documents, the system chunks and indexes them for retrieval, and a LangGraph Agent answers questions with tool calling, multi-step reasoning, and multi-turn memory.

This is an engineering **proof of concept (POC)**: FastAPI backend, Streamlit demo UI, PostgreSQL logging, Docker deployment, and offline RAGAS evaluation. It is suitable for demos and local experimentation, not production deployment as-is.

---

## Key Features

| Feature | What it does |
|---------|----------------|
| **PDF upload & chunking** | Upload PDFs, validate format, parse with pypdf, split into chunks |
| **FAISS vector retrieval** | DashScope embeddings + in-process FAISS similarity search |
| **LangGraph Agent workflow** | Planner → agent ⇄ tools → evaluator → answer |
| **Tool calling** | `retrieve_chunks`, `list_headings`, `count_tables`, `check_machine_health` |
| **Multi-turn memory** | Client sends `history`; server keeps the last 3 turns |
| **Debug trace visualization** | `debug: true` returns `tool_trace`, reasoning snapshot, evidence preview |
| **Streamlit UI** | Browser-based upload, chat, debug panels, and QA history |
| **PostgreSQL logging** | Document metadata and QA logs persist; vectors stay in FAISS |
| **Docker deployment** | `docker-compose` for API + PostgreSQL |
| **RAGAS evaluation** | Offline script scores faithfulness and answer relevancy |

**Q&A endpoints:** `POST /ask/` (Agent, default) · `POST /ask_rag/` (classic RAG baseline)

---

## Architecture

```mermaid
flowchart TB
    User([User])

    subgraph client["Client layer"]
        Streamlit["Streamlit UI<br/>:8501"]
    end

    subgraph backend["rag-agentic-system"]
        FastAPI["FastAPI<br/>:8000"]
        LangGraph["LangGraph Agent<br/>planner · tools · evaluator"]
        FAISS["FAISS index<br/>in-process"]
        PG[("PostgreSQL<br/>documents · qa_logs")]
    end

    subgraph external["External services"]
        DashScope["DashScope<br/>qwen-plus · TextEmbedding"]
    end

    User --> Streamlit
    Streamlit -->|"HTTP REST"| FastAPI
    FastAPI --> LangGraph
    LangGraph --> FAISS
    LangGraph -->|"LLM & embeddings"| DashScope
    FastAPI --> PG
    FastAPI -->|"upload: chunk & embed"| FAISS
```

**Hybrid persistence:** PostgreSQL stores document metadata and QA logs only. Vector indexes and chunk text live in **process memory** (FAISS). After a restart, history is queryable but retrieval requires re-uploading PDFs.

More detail: [docs/architecture.md](docs/architecture.md)

---

## Quick Start

**Requirements:** Python 3.10+, network access to Alibaba Cloud DashScope.

### 1. Clone and install

```bash
git clone https://github.com/ShihangPENg-afk/rag-agentic-system.git
cd rag-agentic-system
make install
```

### 2. Configure `.env`

```bash
make env-init    # copies .env.example → .env only if missing
```

Edit `.env` and set a real API key:

```env
DASHSCOPE_API_KEY=your_api_key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

POSTGRES_USER=ragagent
POSTGRES_PASSWORD=ragagent_secret
POSTGRES_DB=ragagent
DATABASE_URL=postgresql+psycopg2://ragagent:ragagent_secret@localhost:5432/ragagent
```

Verify configuration:

```bash
make env-check
```

> Do not overwrite an existing `.env` with `.env.example`—you will lose your API key.

### 3. Start with Docker

```bash
make docker-up
```

Starts PostgreSQL and the FastAPI API. API docs: http://127.0.0.1:8000/docs

### 4. Smoke test

```bash
make smoke
```

End-to-end check (health, upload, Agent Q&A, classic RAG). A full run typically takes **2–4 minutes** (DashScope embedding). Success: `Smoke Test 全部通过 (4/4)`.

### 5. Streamlit UI

Run on the host (separate from Docker):

```bash
pip install -r ui/requirements-ui.txt
streamlit run ui/streamlit_app.py
```

Browser: http://127.0.0.1:8501

---

## Evaluation

Offline evaluation uses [RAGAS](https://docs.ragas.io/) against hand-crafted samples in `evals/ragas_samples.json`.

**Staged baseline** (`test.pdf`, 3 of 10 samples, `RAGAS_LIMIT=3`):

| Metric | Score |
|--------|-------|
| **faithfulness** | **0.8750** |
| **answer_relevancy** | **0.8858** |

These scores come from a **small, staged evaluation** (3 samples)—not a production-scale or statistically robust benchmark. Use them as a development checkpoint, not as proof of production quality.

```bash
make eval-ragas
make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600
```

Full snapshot: [docs/ragas_baseline.md](docs/ragas_baseline.md)

---

## Demo

**Written walkthrough:** [docs/ui_demo_guide.md](docs/ui_demo_guide.md) — step-by-step script for PDF upload, Agent Q&A, Debug Trace, multi-turn chat, and PostgreSQL history (~8–12 minutes).

**Industrial integration demo:** [docs/industrial_demo_guide.md](docs/industrial_demo_guide.md) — Agent `check_machine_health` tool calling the predictive service.

### Demo Video

End-to-end screen recording (PDF Q&A, Debug Trace, PostgreSQL history, equipment health tab, Agent tool calls):

| Platform | Link |
|----------|------|
| **Baidu Pan** | [rag-demo.mp4](https://pan.baidu.com/s/1G3FDGbw7h37hDuddjUFpRg) · extraction code `iqcq` |

The written guides cover the same flows and work well when video access is inconvenient.

---

## Industrial Extension

**[predictive-maintenance-mini](https://github.com/ShihangPENg-afk/predictive-maintenance-mini)** is a **separate** industrial prediction service (EDA → RandomForest → FastAPI on `:8010`). It is not bundled inside this repo.

**rag-agentic-system** integrates with it via the Agent tool `check_machine_health`:

```text
User question → LangGraph Agent → check_machine_health(sensor_data)
                               → HTTP POST {HEALTH_API_URL}/predict
                               → predictive-maintenance-mini :8010
```

- The Streamlit **Equipment Health** tab can also call the service directly (bypassing the Agent).
- The two services are **decoupled**: no shared process or database.
- The industrial model is a **demo baseline**, not production-grade.

Dual-service local setup:

```bash
# clone sibling repo, then from rag-agentic-system:
make stack-up
make stack-verify
```

---

## Known Limitations

Be explicit about what is **not** implemented or production-ready:

| Limitation | Detail |
|------------|--------|
| **LoRA not integrated** | Generation uses DashScope `qwen-plus` via API. LoRA weights from [llm-finetune-for-manufacturing](https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing) are **not** wired in. |
| **No production auth** | No authentication, authorization, rate limiting, or tenant isolation. |
| **FAISS built at runtime** | Vector indexes are built in-process on upload; they are **not** persisted to PostgreSQL or disk. Re-upload PDFs after restart. |
| **Streamlit is a demo UI** | Intended for local demos—not a production front end. |

Additional POC constraints:

- PostgreSQL stores metadata and QA logs only; retrieval cannot be restored from the database alone.
- `list_headings` / `count_tables` use heuristic rules on chunk text, not native PDF structure parsing.
- Classic RAG (`/ask_rag/`) does not write to `qa_logs`.
- Industrial prediction is for demonstration only.

---

## Related Repositories

| Repository | Role |
|------------|------|
| [rag-agentic-system](https://github.com/ShihangPENg-afk/rag-agentic-system) | This repo — Agentic RAG, Streamlit, PostgreSQL |
| [predictive-maintenance-mini](https://github.com/ShihangPENg-afk/predictive-maintenance-mini) | Independent industrial ML inference API (`:8010`) |
| [llm-finetune-for-manufacturing](https://github.com/ShihangPENg-afk/llm-finetune-for-manufacturing) | LoRA fine-tuning experiment (**not integrated**) |

---

## License

[MIT License](LICENSE)
