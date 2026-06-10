#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
PLACEHOLDER="your_dashscope_api_key_here"

if [ ! -f "${ENV_FILE}" ]; then
  echo "❌ 未找到 ${ENV_FILE}"
  echo "   请先运行: make env-init"
  echo "   然后编辑 .env，填入真实 DASHSCOPE_API_KEY"
  exit 1
fi

KEY="$(grep -E '^DASHSCOPE_API_KEY=' "${ENV_FILE}" | head -1 | cut -d= -f2- | tr -d '\r' || true)"
KEY="$(echo -n "${KEY}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

if [ -z "${KEY}" ]; then
  echo "❌ .env 中 DASHSCOPE_API_KEY 为空"
  exit 1
fi

if [ "${KEY}" = "${PLACEHOLDER}" ]; then
  echo "❌ .env 中仍是占位符: ${PLACEHOLDER}"
  echo "   请编辑 .env 填入真实 Key，不要使用 .env.example 里的示例值"
  exit 1
fi

echo "✅ .env 检查通过（DASHSCOPE_API_KEY 已配置）"
