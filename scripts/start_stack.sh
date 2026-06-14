#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

INDUSTRIAL_HEALTH_DEMO_DIR="${INDUSTRIAL_HEALTH_DEMO_DIR:-${PROJECT_ROOT}/../industrial-health-demo}"
RAG_BASE_URL="${RAG_BASE_URL:-http://127.0.0.1:8000}"
HEALTH_BASE_URL="${HEALTH_API_URL:-http://127.0.0.1:8010}"

if [ ! -d "${INDUSTRIAL_HEALTH_DEMO_DIR}" ]; then
  echo "❌ 未找到 industrial-health-demo 目录: ${INDUSTRIAL_HEALTH_DEMO_DIR}"
  echo "   可通过环境变量 INDUSTRIAL_HEALTH_DEMO_DIR 指定路径。"
  exit 1
fi

echo "============================================================"
echo "启动双服务栈"
echo "============================================================"
echo "industrial-health-demo: ${INDUSTRIAL_HEALTH_DEMO_DIR}"
echo "rag-agent             : ${PROJECT_ROOT}"
echo

bash scripts/check_env.sh

echo
echo "[1/2] 启动 industrial-health-demo (Docker, :8010) ..."
(cd "${INDUSTRIAL_HEALTH_DEMO_DIR}" && make docker-up)

echo
echo "[2/2] 启动 rag-agent (Docker, :8000) ..."
docker compose up --build -d

echo
echo "等待服务就绪 ..."
sleep 3
bash scripts/verify_health_stack.sh "${RAG_BASE_URL}" "${HEALTH_BASE_URL}"
