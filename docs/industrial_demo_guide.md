# 工业设备健康预测 Tool 演示指南

> 适用版本：rag-agentic-system + predictive-maintenance-mini 双服务联动  
> 关联文档：[README.md](../README.md) · [architecture.md](architecture.md)

本文档说明 `predictive-maintenance-mini` 如何作为本仓库的 Tool 服务参与 Agent 工作流。

## 1. 服务边界

| 服务 | 默认端口 | 职责 |
| --- | --- | --- |
| `rag-agentic-system` | `8000` | FastAPI、RAG、LangGraph Agent、PostgreSQL + pgvector、Redis |
| `predictive-maintenance-mini` | `8010` | 接收传感器特征，返回 `prediction`、`risk_level`、`recommendation` |

两个服务分仓库、分进程、分端口部署。本仓库不内嵌预测模型，也不共享预测服务的数据库或训练代码。

## 2. Tool 调用链路

```text
User question
  -> FastAPI /ask or /agent/invoke
  -> LangGraph Agent
  -> check_machine_health(sensor_data)
  -> POST {HEALTH_API_URL}/predict
  -> predictive-maintenance-mini
  -> Agent summarizes risk and maintenance suggestion
```

相关实现：

- 通用 Agent 工具绑定：`app/agent/nodes.py`
- 工具 HTTP 客户端：`app/tools/machine_health_tool.py`
- 工业运维 Agent 工具：`app/agents/maintenance_agent/tools.py`
- 环境变量：`HEALTH_API_URL=http://127.0.0.1:8010`

## 3. 启动方式

推荐两个仓库放在同级目录：

```text
pythonProject1/
  rag-agentic-system/
  predictive-maintenance-mini/
```

### 一键双服务栈

在本仓库根目录：

```bash
make stack-up
make stack-verify
```

### 手动启动

预测服务：

```bash
cd ../predictive-maintenance-mini
make docker-up
make docker-verify
```

本仓库后端：

```bash
cd ../rag-agentic-system
make env-check
make docker-up
```

Streamlit：

```bash
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
export API_BASE_URL=http://127.0.0.1:8000
export HEALTH_API_URL=http://127.0.0.1:8010
make ui
```

## 4. 演示方式

### Streamlit 直接调用预测服务

1. 打开 `http://127.0.0.1:8501`。
2. 进入“设备健康预测”Tab。
3. 点击“获取模型信息”。
4. 输入传感器特征并点击“预测设备健康状态”。

这条链路用于验证 predictive-maintenance-mini 自身可用，不经过 Agent。

### Agent 调用 Tool

1. 在 Streamlit 侧边栏登录。
2. 上传任意 PDF 或选择已有文档。
3. 在“聊天”Tab 输入：

```text
请根据以下传感器读数判断设备健康状态：temperature=75, pressure=1.2, vibration=0.6
```

4. 展开 Debug Trace，确认工具轨迹中出现 `check_machine_health`。

## 5. 预期返回

predictive-maintenance-mini 的 `/predict` 通常返回：

- `prediction`
- `prediction_label`
- `risk_level`
- `recommendation`
- `probabilities`

Agent 不应只复述 JSON，而应把结果整理为结论、风险解释和维护建议。

## 6. 边界说明

| 边界项 | 说明 |
| --- | --- |
| 预测模型 | 传统机器学习 baseline，用于本地联调和工程 Demo |
| 决策边界 | 输出不应直接作为真实设备维护决策依据 |
| 服务解耦 | 预测服务可独立替换，只要保持 `/predict` 协议即可 |
| LoRA | LoRA 实验未接入本仓库默认问答链路 |
| fallback | 预测服务不可用时，维护 Agent 可走 deterministic fallback，便于本地流程演示 |

## 7. 常见问题

| 现象 | 处理 |
| --- | --- |
| `make stack-verify` 失败 | 分别检查 `http://127.0.0.1:8000/health` 和 `http://127.0.0.1:8010/health` |
| Agent 未调用 `check_machine_health` | 问题中明确包含传感器字段和值 |
| Streamlit 健康预测 Tab 可用但聊天无工具调用 | Tab 是直连预测服务；聊天链路需要 Agent 根据问题意图选择工具 |
| `/predict` 失败 | 查看 predictive-maintenance-mini 日志，确认模型 schema 与请求 payload 匹配 |
