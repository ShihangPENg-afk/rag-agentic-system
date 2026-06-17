#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

RAG_BASE_URL="${1:-http://127.0.0.1:8000}"
HEALTH_BASE_URL="${2:-http://127.0.0.1:8010}"

if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "❌ 未找到 Python 解释器"
  exit 1
fi

step_ok() {
  echo "✅ $1"
}

step_fail() {
  echo "❌ $1"
  exit 1
}

echo "============================================================"
echo "双服务联动检查 (rag-agentic-system + predictive-maintenance-mini)"
echo "============================================================"
echo "RAG API    : ${RAG_BASE_URL}"
echo "Health API : ${HEALTH_BASE_URL}"
echo

if ! curl -fsS "${RAG_BASE_URL}/health" -o /dev/null; then
  step_fail "rag-agentic-system /health 不可访问"
fi
step_ok "rag-agentic-system /health"

if ! RAG_OPENAPI="$(curl -fsS "${RAG_BASE_URL}/openapi.json")"; then
  step_fail "rag-agentic-system /openapi.json 不可访问"
fi

RAG_TITLE="$("${PYTHON_BIN}" -c '
import json, sys
data = json.loads(sys.argv[1])
print(data.get("info", {}).get("title", ""))
' "${RAG_OPENAPI}")"

if [ "${RAG_TITLE}" != "RAG PDF 智能问答系统" ]; then
  step_fail "${RAG_BASE_URL} 不是 rag-agentic-system（当前: ${RAG_TITLE:-未知}）。请停止占用 8000 端口的其他 uvicorn 进程，仅保留 Docker 中的 rag-agentic-system。"
fi
step_ok "rag-agentic-system OpenAPI 标题正确"

if ! curl -fsS "${HEALTH_BASE_URL}/health" -o /dev/null; then
  step_fail "predictive-maintenance-mini /health 不可访问（请先 cd ../predictive-maintenance-mini && make docker-up）"
fi
step_ok "predictive-maintenance-mini /health"

if ! MODEL_INFO="$(curl -fsS "${HEALTH_BASE_URL}/model-info")"; then
  step_fail "predictive-maintenance-mini /model-info 不可访问"
fi
step_ok "predictive-maintenance-mini /model-info"

PAYLOAD="$("${PYTHON_BIN}" -c '
import json, sys
info = json.loads(sys.argv[1])
features = info.get("features") or info.get("numeric_features") or []
print(json.dumps({"features": {name: 0 for name in features}}))
' "${MODEL_INFO}")"

if ! curl -fsS -X POST "${HEALTH_BASE_URL}/predict" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" -o /dev/null; then
  step_fail "predictive-maintenance-mini /predict 失败"
fi
step_ok "predictive-maintenance-mini /predict"

echo
echo "============================================================"
echo "✅ 双服务联动检查通过"
echo "============================================================"
echo "下一步: streamlit run ui/streamlit_app.py"
echo "  - 侧边栏 API_BASE_URL=${RAG_BASE_URL}"
echo "  - 「设备健康预测」页 HEALTH_API_URL=${HEALTH_BASE_URL}"
