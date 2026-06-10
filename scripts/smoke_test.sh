#!/usr/bin/env bash
set -euo pipefail

# 切换到项目根目录，确保相对路径 (test.pdf) 可用
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

BASE_URL="${1:-http://127.0.0.1:8000}"
PDF_PATH="${2:-test.pdf}"
QUESTION="${SMOKE_QUESTION:-这份文档主要讲什么？}"

TOTAL_STEPS=4
STEP=0

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
  exit 1
}

echo "============================================================"
echo "Smoke Test / Agentic RAG"
echo "============================================================"
echo "BASE_URL : ${BASE_URL}"
echo "PDF_PATH : ${PDF_PATH}"
echo "QUESTION : ${QUESTION}"
echo "PYTHON   : ${PYTHON_BIN}"

if [ ! -f "${PDF_PATH}" ]; then
  step_fail "PDF 文件不存在: ${PDF_PATH}"
fi

# ---------------------------------------------------------------------------
# 1. API 文档可达性
# ---------------------------------------------------------------------------
step_header "检查 API 文档是否可访问 (/openapi.json 或 /docs)..."

DOCS_OK=0
if curl -fsS "${BASE_URL}/openapi.json" -o /tmp/rag_openapi.json; then
  step_ok "/openapi.json 可访问"
  DOCS_OK=1
elif curl -fsS "${BASE_URL}/docs" -o /tmp/rag_docs.html; then
  step_ok "/docs 可访问（/openapi.json 不可用，已回退）"
  DOCS_OK=1
fi

if [ "${DOCS_OK}" -ne 1 ]; then
  step_fail "无法访问 ${BASE_URL}/openapi.json 或 ${BASE_URL}/docs，请确认服务已启动"
fi

# ---------------------------------------------------------------------------
# 2. 上传 PDF
# ---------------------------------------------------------------------------
step_header "上传 PDF 到 /upload_pdf/ ..."

if ! UPLOAD_RESP="$(curl -fsS -X POST "${BASE_URL}/upload_pdf/" \
  -H "accept: application/json" \
  -F "file=@${PDF_PATH}")"; then
  step_fail "上传 PDF 失败"
fi

step_ok "PDF 上传成功"
echo "${UPLOAD_RESP}"

# ---------------------------------------------------------------------------
# 3. 提取 knowledge_base_id
# ---------------------------------------------------------------------------
step_header "从上传结果提取 knowledge_base_id ..."

if ! KB_ID="$(printf '%s' "${UPLOAD_RESP}" | "${PYTHON_BIN}" -c '
import json, sys

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)

kb_id = data.get("knowledge_base_id")
if not kb_id:
    sys.exit(2)
print(kb_id)
')"; then
  step_fail "无法从上传响应中解析 knowledge_base_id"
fi

step_ok "knowledge_base_id=${KB_ID}"

# ---------------------------------------------------------------------------
# 4. Agent 问答
# ---------------------------------------------------------------------------
step_header "调用 /ask/ (debug=true) ..."

ASK_PAYLOAD=$("${PYTHON_BIN}" -c '
import json, os, sys
print(json.dumps({
    "question": sys.argv[1],
    "knowledge_base_id": sys.argv[2],
    "history": [],
    "debug": True,
}, ensure_ascii=False))
' "${QUESTION}" "${KB_ID}")

if ! ASK_RESP="$(curl -fsS -X POST "${BASE_URL}/ask/" \
  -H "Content-Type: application/json" \
  -d "${ASK_PAYLOAD}")"; then
  step_fail "调用 /ask/ 失败"
fi

if ! printf '%s' "${ASK_RESP}" | "${PYTHON_BIN}" -c '
import json, sys

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)

if not data.get("answer"):
    sys.exit(2)
if data.get("mode") != "agent":
    sys.exit(3)
print(data["answer"][:200])
' >/tmp/rag_ask_preview.txt; then
  step_fail "/ask/ 响应缺少 answer 或 mode 不是 agent"
fi

step_ok "Agent 问答成功"
echo "${ASK_RESP}"
echo
echo "回答预览: $(cat /tmp/rag_ask_preview.txt)..."
echo
echo "============================================================"
echo "✅ Smoke Test 全部通过 (${TOTAL_STEPS}/${TOTAL_STEPS})"
echo "============================================================"
