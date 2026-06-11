#!/usr/bin/env bash
set -euo pipefail

# 最终交付检查：API 文档、PostgreSQL 元数据接口、端到端 Smoke Test
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

BASE_URL="${1:-http://127.0.0.1:8000}"
PDF_PATH="${2:-test.pdf}"

TOTAL_STEPS=4
STEP=0
PROBE_KB_ID="00000000-0000-0000-0000-000000000000"

if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "❌ 未找到可用 Python 解释器（.venv/bin/python / python3 / python）"
  exit 1
fi

step_header() {
  STEP=$((STEP + 1))
  echo
  echo "[${STEP}/${TOTAL_STEPS}] $1"
}

step_ok() {
  echo "✅ $1"
}

step_fail() {
  echo "❌ $1"
  echo
  echo "============================================================"
  echo "❌ 最终交付检查失败 (${STEP}/${TOTAL_STEPS})"
  echo "============================================================"
  exit 1
}

echo "============================================================"
echo "Final Demo Check / 最终交付检查"
echo "============================================================"
echo "BASE_URL : ${BASE_URL}"
echo "PDF_PATH : ${PDF_PATH}"
echo "PYTHON   : ${PYTHON_BIN}"

# ---------------------------------------------------------------------------
# 1. OpenAPI 文档
# ---------------------------------------------------------------------------
step_header "检查 /openapi.json 是否可访问..."

if ! OPENAPI_RESP="$(curl -fsS "${BASE_URL}/openapi.json")"; then
  step_fail "无法访问 ${BASE_URL}/openapi.json，请确认 API 服务已启动"
fi

if ! printf '%s' "${OPENAPI_RESP}" | "${PYTHON_BIN}" -c '
import json, sys

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)

if not isinstance(data, dict):
    sys.exit(2)
if "openapi" not in data and "paths" not in data:
    sys.exit(3)
' >/dev/null; then
  step_fail "/openapi.json 响应不是有效的 OpenAPI JSON"
fi

step_ok "/openapi.json 可访问且格式正确"

# ---------------------------------------------------------------------------
# 2. 最近上传文档（PostgreSQL）
# ---------------------------------------------------------------------------
step_header "检查 GET /documents/ 是否可用..."

if ! DOCS_RESP="$(curl -fsS "${BASE_URL}/documents/?limit=5")"; then
  step_fail "无法访问 ${BASE_URL}/documents/"
fi

if ! DOCS_INFO="$(printf '%s' "${DOCS_RESP}" | "${PYTHON_BIN}" -c '
import json, sys

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)

if not isinstance(data, dict):
    sys.exit(2)
if "total" not in data or "documents" not in data:
    sys.exit(3)
if not isinstance(data["documents"], list):
    sys.exit(4)

kb_id = ""
for doc in data["documents"]:
    if isinstance(doc, dict) and doc.get("knowledge_base_id"):
        kb_id = str(doc["knowledge_base_id"])
        break

print(str(data["total"]) + "|" + kb_id)
')"; then
  step_fail "/documents/ 响应缺少 total/documents 或 JSON 无效"
fi

DOCS_TOTAL="${DOCS_INFO%%|*}"
KB_ID_FROM_DOCS="${DOCS_INFO#*|}"

step_ok "/documents/ 可访问（total=${DOCS_TOTAL}）"

# ---------------------------------------------------------------------------
# 3. 历史问答日志（PostgreSQL）
# ---------------------------------------------------------------------------
step_header "检查 GET /qa_logs/ 是否可用..."

QA_KB_ID="${KB_ID_FROM_DOCS:-${PROBE_KB_ID}}"
if [ -z "${KB_ID_FROM_DOCS}" ]; then
  echo "   （无历史文档记录，使用探测 knowledge_base_id 验证接口）"
else
  echo "   （使用最近文档 knowledge_base_id=${QA_KB_ID}）"
fi

if ! QA_LOGS_RESP="$(curl -fsS "${BASE_URL}/qa_logs/?knowledge_base_id=${QA_KB_ID}&limit=5")"; then
  step_fail "无法访问 ${BASE_URL}/qa_logs/?knowledge_base_id=${QA_KB_ID}"
fi

if ! QA_LOGS_TOTAL="$(printf '%s' "${QA_LOGS_RESP}" | "${PYTHON_BIN}" -c '
import json, sys

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)

if not isinstance(data, dict):
    sys.exit(2)
required = ("knowledge_base_id", "total", "qa_logs")
if any(key not in data for key in required):
    sys.exit(3)
if not isinstance(data["qa_logs"], list):
    sys.exit(4)

print(data["total"])
')"; then
  step_fail "/qa_logs/ 响应缺少 knowledge_base_id/total/qa_logs 或 JSON 无效"
fi

step_ok "/qa_logs/ 可访问（total=${QA_LOGS_TOTAL}）"

# ---------------------------------------------------------------------------
# 4. 端到端 Smoke Test
# ---------------------------------------------------------------------------
step_header "运行 scripts/smoke_test.sh ..."

if ! bash "${SCRIPT_DIR}/smoke_test.sh" "${BASE_URL}" "${PDF_PATH}"; then
  step_fail "scripts/smoke_test.sh 未通过"
fi

step_ok "scripts/smoke_test.sh 全部通过"

echo
echo "============================================================"
echo "✅ 最终交付检查全部通过 (${TOTAL_STEPS}/${TOTAL_STEPS})"
echo "============================================================"
