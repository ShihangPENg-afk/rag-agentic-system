# rag-agent Makefile
# ---------------------------------------------------------------------------
# 变量
# ---------------------------------------------------------------------------
PYTHON        := .venv/bin/python
PIP           := .venv/bin/pip
COMPOSE       := docker compose
SERVICE       := rag-agent

PDF           ?= test.pdf
BASE_URL      ?= http://127.0.0.1:8000
SMOKE_SCRIPT  := scripts/smoke_test.sh

RAGAS_LIMIT   ?= 3
RAGAS_TIMEOUT ?= 600
RAGAS_METRICS ?= relevancy
RAGAS_SAMPLES := evals/ragas_samples.json

# ---------------------------------------------------------------------------
# Phony targets
# ---------------------------------------------------------------------------
.PHONY: help install env-init env-check \
        run \
        docker-up docker-down docker-logs \
        test-agent test-retrieval test-doc-tools smoke \
        eval-ragas

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# 帮助与安装
# ---------------------------------------------------------------------------
help: ## 显示常用命令
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  %-18s %s\n", $$1, $$2}'

install: ## 创建虚拟环境并安装依赖
	python3 -m venv .venv
	$(PIP) install -r requirements.txt

env-init: ## 首次创建 .env（不覆盖已有文件）
	@if [ -f .env ]; then \
		echo "⚠️  .env 已存在，跳过复制（避免覆盖真实 API Key）"; \
	else \
		cp .env.example .env; \
		echo "✅ 已创建 .env，请编辑并填入真实 DASHSCOPE_API_KEY"; \
	fi

env-check: ## 检查 .env 是否存在且 API Key 非占位符
	bash scripts/check_env.sh

# ---------------------------------------------------------------------------
# 本地服务
# ---------------------------------------------------------------------------
run: ## 本地启动 FastAPI 服务 (127.0.0.1:8000)
	$(PYTHON) main.py

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
docker-up: env-check ## 构建并后台启动 Docker 服务 (docker compose up --build -d)
	$(COMPOSE) up --build -d

docker-down: ## 停止并移除 Docker 容器
	$(COMPOSE) down

docker-logs: ## 跟踪 Docker 服务日志
	$(COMPOSE) logs -f $(SERVICE)

# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------
test-agent: ## 运行 LangGraph Agent 本地测试
	$(PYTHON) test_langgraph_agent.py $(PDF)

test-retrieval: ## 运行检索工具测试（默认 test.pdf）
	$(PYTHON) test_retrieval_tool.py $(PDF)

test-doc-tools: ## 运行文档结构工具测试
	$(PYTHON) test_document_tools.py $(PDF)

smoke: ## 运行端到端冒烟测试 (BASE_URL + PDF 可覆盖)
	bash $(SMOKE_SCRIPT) $(BASE_URL) $(PDF)

# ---------------------------------------------------------------------------
# 评估
# ---------------------------------------------------------------------------
eval-ragas: ## 运行 RAGAS 默认安全评估 (limit=3, metrics=relevancy)
	$(PYTHON) evals/run_ragas_eval.py \
		--pdf $(PDF) \
		--samples $(RAGAS_SAMPLES) \
		--limit $(RAGAS_LIMIT) \
		--eval-timeout $(RAGAS_TIMEOUT) \
		--metrics $(RAGAS_METRICS)
