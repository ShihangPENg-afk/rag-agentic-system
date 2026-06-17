# 工业设备健康预测演示指南

> 适用版本：rag-agentic-system + predictive-maintenance-mini 双服务联动  
> 关联文档：[README.md](../README.md) · [ui_demo_guide.md](ui_demo_guide.md)

---

## 1. 架构说明

### 1.1 predictive-maintenance-mini：独立工业预测服务

**predictive-maintenance-mini** 是一个**独立的**工业设备健康预测服务，与 rag-agentic-system **分仓库、分进程、分端口**部署：

| 项目 | 说明 |
|------|------|
| 职责 | 接收传感器特征，返回设备健康分类结果 |
| 默认端口 | `8010` |
| 主要接口 | `GET /health`、`GET /model-info`、`POST /predict` |
| 模型 | 传统机器学习 baseline（如 scikit-learn 分类器），**非生产模型** |

该服务不依赖 rag-agentic-system 的数据库、FAISS 向量库或 Agent 图；可单独启动与验证。

### 1.2 rag-agentic-system：通过 Agent 工具调用预测 API

rag-agentic-system 在 LangGraph Agent 中注册了 **`check_machine_health`** 工具。当用户提问涉及设备健康、传感器读数、故障预警等场景时，Agent 会将传感器数据整理为 `sensor_data` 字典，经工具层 HTTP 调用 predictive-maintenance-mini 的 `/predict` 接口。

调用链路：

```
用户问题（Streamlit / HTTP API）
    → rag-agentic-system Agent（LangGraph）
    → check_machine_health(sensor_data)
    → check_machine_health_tool()
    → POST {HEALTH_API_URL}/predict  （默认 http://127.0.0.1:8010）
    → predictive-maintenance-mini
```

相关实现：

- 工具定义：`app/agent/nodes.py`（`@tool("check_machine_health")`）
- HTTP 客户端：`app/tools/machine_health_tool.py`
- 环境变量：`HEALTH_API_URL`（默认 `http://127.0.0.1:8010`，见 `config.py`）

> **注意**：Streamlit UI 的「设备健康预测」Tab 也可**直接**调用 predictive-maintenance-mini（不经过 Agent），用于独立验证预测 API。本指南重点演示 **Agent 聊天链路** 中的 `check_machine_health` 工具调用。

---

## 2. 启动步骤

演示前请确认：

- Python 3.10+，rag-agentic-system 已执行 `make install` 且 `make env-check` 通过
- `.env` 中 `DASHSCOPE_API_KEY` 为有效值
- 同级目录存在 `predictive-maintenance-mini`（或通过 `PREDICTIVE_MAINTENANCE_MINI_DIR` 指定路径）

**首次请 clone 两个仓库到同级目录：**

```bash
git clone https://github.com/ShihangPENg-afk/rag-agentic-system.git
git clone https://github.com/ShihangPENg-afk/predictive-maintenance-mini.git
```

### 方式 A：一键启动双服务栈（推荐）

在 **rag-agentic-system** 仓库根目录：

```bash
make stack-up       # 先起 predictive-maintenance-mini Docker (:8010)，再起 rag-agentic-system Docker (:8000)
make stack-verify   # 验证两个服务均正常
```

### 方式 B：分终端手动启动

**终端 A — 启动 predictive-maintenance-mini API**

```bash
cd ../predictive-maintenance-mini
make docker-up         # 首次会自动训练 model.pkl（若缺失）
make docker-verify     # 验证 /health、/model-info、/predict
```

确认 `http://127.0.0.1:8010/health` 可访问。

**终端 B — 启动 rag-agentic-system**

本地运行：

```bash
cd ../rag-agentic-system
docker compose up postgres -d   # 若 PostgreSQL 未启动
make env-check && make run
```

或使用 Docker：

```bash
cd ../rag-agentic-system
make env-check && make docker-up
```

确认 `http://127.0.0.1:8000/docs` 可打开。

**终端 C — 启动 Streamlit UI**

```bash
cd rag-agentic-system
source .venv/bin/activate
pip install -r ui/requirements-ui.txt
export API_BASE_URL=http://127.0.0.1:8000
export HEALTH_API_URL=http://127.0.0.1:8010
make ui
# 或: streamlit run ui/streamlit_app.py
```

浏览器访问 `http://127.0.0.1:8501`。

### 启动后自检

```bash
# predictive-maintenance-mini
curl -fsS http://127.0.0.1:8010/health
curl -fsS http://127.0.0.1:8010/model-info

# rag-agentic-system
curl -fsS http://127.0.0.1:8000/health

# 双服务联动（rag-agentic-system 仓库内）
make stack-verify
```

Streamlit 侧边栏应显示绿色 **「后端 /openapi.json 可访问」**。

---

## 3. 演示流程

### 3.1 推荐演示问题

在 Streamlit **「聊天」** 标签中输入（无需先上传 PDF；设备健康问题不依赖知识库）：

```
请根据以下传感器读数判断设备健康状态：temperature=75, pressure=1.2, vibration=0.6
```

### 3.2 预期 Agent 行为

1. Agent 识别为设备健康 / 传感器预测类问题  
2. 调用 **`check_machine_health`**，传入类似 `{"temperature": 75, "pressure": 1.2, "vibration": 0.6}` 的 `sensor_data`  
3. 工具向 predictive-maintenance-mini 发起 `POST /predict`  
4. Agent 基于返回的 `prediction`、`risk_level`、`recommendation`、`probabilities` 组织自然语言回答（含结论、依据与 1～3 条维护建议）

### 3.3 Debug Trace 验收

展开 **「Agent 推理步骤 / Debug Trace」**，在 **工具轨迹** 中应出现：

- 工具名：**`check_machine_health`**
- 输入：含 `sensor_data`（temperature、pressure、vibration 等字段）
- 输出：设备健康预测结果（prediction、risk_level、recommendation、probabilities）

若 Debug Trace 中**未**出现 `check_machine_health`，请检查：

- predictive-maintenance-mini 是否在 `8010` 正常运行（`curl http://127.0.0.1:8010/health`）
- rag-agentic-system 进程是否读取到正确的 `HEALTH_API_URL`
- 问题表述是否明确包含传感器读数或设备健康相关关键词

---

## 4. 边界与限制（演示时务必说明）

| 边界项 | 说明 |
|--------|------|
| **传统 ML baseline** | predictive-maintenance-mini 使用经典机器学习分类模型（如 RandomForest / 逻辑回归等 baseline），用于演示「传感器 → 健康状态」链路，**不代表真实产线精度** |
| **非生产模型** | 模型基于演示/合成数据训练，**不可直接用于生产决策**；预测结果仅供 POC 与联调展示 |
| **LoRA 未接入** | rag-agentic-system 的 LLM 仍走 DashScope `qwen-plus` 在线 API；**LoRA 微调权重尚未接入 rag-agentic-system**，Agent 推理与工具编排不受工业预测模型训练影响 |
| **服务解耦** | predictive-maintenance-mini 与 rag-agentic-system **仅通过 HTTP 松耦合**（`HEALTH_API_URL`）；二者无共享进程、无共享数据库。工业预测服务可独立升级、替换或下线，不影响 PDF 问答主链路 |

---

## 5. 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 工具返回「无法连接设备健康预测 API」 | predictive-maintenance-mini 未启动或端口错误 | 启动 `make docker-up`（predictive-maintenance-mini 目录），确认 `8010` 可访问 |
| `make stack-verify` 报 8000 端口服务不对 | 8000 被其他 uvicorn 占用 | 停止占用进程，仅保留 rag-agentic-system 容器或 `make run` |
| Agent 未调用 `check_machine_health` | 问题未明确传感器数值或健康意图 | 使用本文 3.1 节推荐问题，或补充 temperature / pressure / vibration 等读数 |
| 「设备健康预测」Tab 可用但聊天无工具调用 | Tab 直连 API，聊天走 Agent | 以 Debug Trace 中是否出现 `check_machine_health` 为准验收 Agent 链路 |

---

## 6. 相关命令速查

```bash
# rag-agentic-system 仓库
make health-up        # 仅启动 predictive-maintenance-mini Docker
make stack-up         # 启动双服务栈
make stack-verify     # 验证 8000 + 8010
make ui               # 启动 Streamlit

# predictive-maintenance-mini 仓库
make docker-up        # 启动预测 API (:8010)
make docker-verify    # 验证预测接口
```

完整 PDF 问答与 UI 录屏流程见 [ui_demo_guide.md](ui_demo_guide.md)。
