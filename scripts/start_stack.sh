#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PREDICTIVE_MAINTENANCE_MINI_DIR="${PREDICTIVE_MAINTENANCE_MINI_DIR:-${PROJECT_ROOT}/../predictive-maintenance-mini}"
RAG_BASE_URL="${RAG_BASE_URL:-http://127.0.0.1:8000}"
HEALTH_BASE_URL="${HEALTH_API_URL:-http://127.0.0.1:8010}"

if [ ! -d "${PREDICTIVE_MAINTENANCE_MINI_DIR}" ]; then
  echo "❌ 未找到 predictive-maintenance-mini 目录: ${PREDICTIVE_MAINTENANCE_MINI_DIR}"
  echo "   可通过环境变量 PREDICTIVE_MAINTENANCE_MINI_DIR 指定路径。"
  exit 1
fi

echo "============================================================"
echo "启动双服务栈"
echo "============================================================"
echo "predictive-maintenance-mini: ${PREDICTIVE_MAINTENANCE_MINI_DIR}"
echo "rag-agentic-system             : ${PROJECT_ROOT}"
echo

bash scripts/check_env.sh

echo
echo "[1/2] 启动 predictive-maintenance-mini (Docker, :8010) ..."
(cd "${PREDICTIVE_MAINTENANCE_MINI_DIR}" && make docker-up)

echo
echo "[2/2] 启动 rag-agentic-system (Docker, :8000) ..."
docker compose up --build -d

echo
echo "等待服务就绪 ..."
sleep 3
bash scripts/verify_health_stack.sh "${RAG_BASE_URL}" "${HEALTH_BASE_URL}"
