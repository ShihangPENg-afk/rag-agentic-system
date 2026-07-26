import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_HEALTH_API_URL = "http://127.0.0.1:8010"
UPLOAD_TIMEOUT_SECONDS = 300
ASK_TIMEOUT_SECONDS = 300
BACKEND_CHECK_TIMEOUT_SECONDS = 5
LIST_TIMEOUT_SECONDS = 30
HEALTH_API_TIMEOUT_SECONDS = 30
SIDEBAR_KB_SELECT_KEY = "sidebar_available_kb_select"


st.set_page_config(
    page_title="Industrial Maintenance Agent Platform",
    page_icon="🔧",
    layout="wide",
)

st.title("Industrial Maintenance Agent Platform")


def _init_session_state() -> None:
    defaults = {
        "knowledge_base_id": None,
        "upload_filename": None,
        "chunks_count": None,
        "upload_status": None,
        "upload_message": None,
        "backend_reachable": None,
        "backend_check_error": None,
        "history": [],
        "last_upload_response": None,
        "last_batch_upload_response": None,
        "selected_kb_from_list": None,
        "auth_token": None,
        "auth_email": None,
        "auth_status": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _normalize_base_url(url: str) -> str:
    return url.strip().rstrip("/")


def _format_list_error(exc: requests.RequestException, resource: str) -> str:
    if isinstance(exc, requests.Timeout):
        return f"获取{resource}超时，请稍后重试。"
    if isinstance(exc, requests.ConnectionError):
        return f"无法连接后端，无法获取{resource}。"
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        if response is not None:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            return f"获取{resource}失败（HTTP {response.status_code}）：{detail}"
        return f"获取{resource}失败：{exc}"
    return f"获取{resource}时发生网络错误：{exc}"


def _auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def register_user(api_base_url: str, email: str, password: str) -> dict:
    response = requests.post(
        f"{api_base_url}/auth/register",
        json={"email": email, "password": password},
        timeout=LIST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def login_user(api_base_url: str, email: str, password: str) -> str:
    response = requests.post(
        f"{api_base_url}/auth/login",
        json={"email": email, "password": password},
        timeout=LIST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise ValueError("登录响应中缺少 access_token")
    return token


def check_backend_openapi(api_base_url: str) -> tuple[bool, str | None]:
    try:
        response = requests.get(
            f"{api_base_url}/openapi.json",
            timeout=BACKEND_CHECK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True, None
    except requests.Timeout:
        return False, "连接后端超时，请确认服务已启动。"
    except requests.ConnectionError:
        return False, "无法连接后端，请确认 API 地址正确且服务已启动。"
    except requests.HTTPError as exc:
        return False, f"后端返回 HTTP {exc.response.status_code}。"
    except requests.RequestException as exc:
        return False, f"检查后端时发生网络错误：{exc}"


def fetch_documents(api_base_url: str, token: str, limit: int = 50) -> list[dict]:
    response = requests.get(
        f"{api_base_url}/documents/",
        params={"limit": limit},
        headers=_auth_headers(token),
        timeout=LIST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json().get("documents", [])


def fetch_active_knowledge_base_ids(api_base_url: str) -> set[str]:
    response = requests.get(
        f"{api_base_url}/knowledge_bases",
        timeout=LIST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return {kb["id"] for kb in payload.get("knowledge_bases", [])}


def _is_kb_active(kb_id: str | None, active_kb_ids: set[str]) -> bool:
    return bool(kb_id and kb_id in active_kb_ids)


def _clear_knowledge_base_session() -> None:
    st.session_state.knowledge_base_id = None
    st.session_state.upload_filename = None
    st.session_state.chunks_count = None
    st.session_state.upload_status = None
    st.session_state.upload_message = None
    st.session_state.history = []


def fetch_qa_logs(
    api_base_url: str,
    token: str,
    knowledge_base_id: str,
    limit: int = 100,
) -> list[dict]:
    response = requests.get(
        f"{api_base_url}/qa_logs/",
        params={"knowledge_base_id": knowledge_base_id, "limit": limit},
        headers=_auth_headers(token),
        timeout=LIST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json().get("qa_logs", [])


def upload_pdf(api_base_url: str, uploaded_file, token: str) -> dict:
    response = requests.post(
        f"{api_base_url}/documents/upload",
        files={"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")},
        headers=_auth_headers(token),
        timeout=UPLOAD_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def upload_pdfs(api_base_url: str, uploaded_files: list, token: str) -> dict:
    multipart_files = [
        ("files", (uploaded_file.name, uploaded_file.getvalue(), "application/pdf"))
        for uploaded_file in uploaded_files
    ]
    response = requests.post(
        f"{api_base_url}/upload_pdfs/",
        files=multipart_files,
        headers=_auth_headers(token),
        timeout=UPLOAD_TIMEOUT_SECONDS * max(len(uploaded_files), 1),
    )
    response.raise_for_status()
    return response.json()


def _normalize_uploaded_files(uploaded) -> list:
    if uploaded is None:
        return []
    if isinstance(uploaded, list):
        return uploaded
    return [uploaded]


def _find_kb_select_index(available_docs: list[dict], kb_id: str | None) -> int:
    if not kb_id:
        return 0
    for index, doc in enumerate(available_docs, start=1):
        if doc["knowledge_base_id"] == kb_id:
            return index
    return 0


def _sync_sidebar_kb_select(available_docs: list[dict], kb_id: str | None) -> None:
    target_index = _find_kb_select_index(available_docs, kb_id)
    if target_index > 0:
        st.session_state[SIDEBAR_KB_SELECT_KEY] = target_index


def _apply_single_upload_result(result: dict) -> None:
    st.session_state.last_upload_response = result
    st.session_state.last_batch_upload_response = None
    st.session_state.knowledge_base_id = result.get("knowledge_base_id")
    st.session_state.upload_filename = result.get("filename")
    st.session_state.chunks_count = result.get("chunks_count")
    st.session_state.upload_status = result.get("status")
    st.session_state.upload_message = result.get("message")
    st.session_state.history = []
    st.session_state.pop("sidebar_documents", None)
    st.session_state.pop("active_kb_ids", None)
    st.session_state.pop("qa_logs_cache", None)
    st.session_state.pop("qa_logs_cache_key", None)
    st.session_state.pop(SIDEBAR_KB_SELECT_KEY, None)


def _apply_batch_upload_result(result: dict) -> None:
    st.session_state.last_batch_upload_response = result
    st.session_state.last_upload_response = None
    _clear_knowledge_base_session()
    st.session_state.pop("sidebar_documents", None)
    st.session_state.pop("active_kb_ids", None)
    st.session_state.pop("qa_logs_cache", None)
    st.session_state.pop("qa_logs_cache_key", None)
    st.session_state.pop(SIDEBAR_KB_SELECT_KEY, None)


def _history_for_request(history: list) -> list[dict]:
    normalized = [_normalize_turn(turn) for turn in history]
    return [{"user": turn["user"], "assistant": turn["assistant"]} for turn in normalized]


def ask_question(
    api_base_url: str,
    question: str,
    knowledge_base_id: str,
    history: list,
    token: str,
) -> dict:
    response = requests.post(
        f"{api_base_url}/ask",
        json={
            "question": question,
            "knowledge_base_id": knowledge_base_id,
            "history": _history_for_request(history),
            "debug": True,
        },
        headers=_auth_headers(token),
        timeout=ASK_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _format_ask_error(exc: requests.RequestException) -> str:
    if isinstance(exc, requests.Timeout):
        return "问答请求超时，请稍后重试。"
    if isinstance(exc, requests.ConnectionError):
        return "无法连接后端，请确认 API 地址正确且服务已启动。"
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        if response is not None:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            return f"问答失败（HTTP {response.status_code}）：{detail}"
        return f"问答失败：{exc}"
    return f"问答时发生网络错误：{exc}"


def _normalize_turn(turn) -> dict:
    if isinstance(turn, dict):
        return {
            "user": turn.get("user", ""),
            "assistant": turn.get("assistant", ""),
            "debug": turn.get("debug"),
        }
    return {"user": turn[0], "assistant": turn[1], "debug": None}


def _merge_history_with_debug(api_history: list, previous_history: list, debug: dict | None) -> list[dict]:
    normalized_previous = [_normalize_turn(t) for t in previous_history]
    merged: list[dict] = []

    for index, turn in enumerate(api_history):
        if isinstance(turn, dict):
            user = turn.get("user", "")
            assistant = turn.get("assistant", "")
        else:
            user, assistant = turn[0], turn[1]

        preserved_debug = None
        if index < len(normalized_previous):
            prev = normalized_previous[index]
            if prev["user"] == user and prev["assistant"] == assistant:
                preserved_debug = prev.get("debug")

        is_latest = index == len(api_history) - 1
        merged.append(
            {
                "user": user,
                "assistant": assistant,
                "debug": debug if is_latest else preserved_debug,
            }
        )
    return merged


def _apply_document_to_session(doc: dict) -> None:
    st.session_state.knowledge_base_id = doc.get("knowledge_base_id")
    st.session_state.upload_filename = doc.get("filename")
    st.session_state.chunks_count = doc.get("chunks_count")
    st.session_state.upload_status = doc.get("status")
    st.session_state.upload_message = None


def _render_tool_trace(tool_trace: list) -> None:
    if not tool_trace:
        st.caption("无工具调用记录。")
        return

    for index, step in enumerate(tool_trace, start=1):
        tool_name = step.get("tool_name") or "unknown_tool"
        st.markdown(f"**{index}. {tool_name}**")
        st.caption("输入")
        tool_input = step.get("tool_input")
        if tool_input is None:
            st.text("（无）")
        else:
            st.json(tool_input)
        st.caption("输出预览")
        st.text(step.get("tool_output_preview") or "（无）")
        if index < len(tool_trace):
            st.divider()


def _render_reasoning_snapshot(reasoning: dict) -> None:
    sub_queries = reasoning.get("sub_queries") or []
    decision = reasoning.get("decision") or "（无）"
    retrieval_round = reasoning.get("retrieval_round", 0)

    st.markdown(f"**decision:** `{decision}`")
    st.markdown(f"**retrieval_round:** `{retrieval_round}`")

    st.caption("sub_queries")
    if sub_queries:
        for query_index, query in enumerate(sub_queries, start=1):
            st.markdown(f"{query_index}. {query}")
    else:
        st.text("（无）")

    evidence_by_sub_query = reasoning.get("evidence_by_sub_query") or {}
    if evidence_by_sub_query:
        st.caption("evidence_by_sub_query")
        st.json(evidence_by_sub_query)


def _render_memory_snapshot(memory: dict) -> None:
    current_question = memory.get("current_question") or "（无）"
    chat_history_pairs = memory.get("chat_history_pairs") or []
    history_count = len(chat_history_pairs)

    st.markdown(f"**current_question:** {current_question}")
    st.markdown(f"**history 数量:** `{history_count}`")

    memory_summary = memory.get("memory_summary")
    if memory_summary:
        st.caption("memory_summary")
        st.text(memory_summary)


def _render_evidence_preview(evidence_preview: list) -> None:
    if not evidence_preview:
        st.caption("无检索证据预览。")
        return

    for index, preview in enumerate(evidence_preview, start=1):
        st.markdown(f"**证据 {index}**")
        st.text(preview)
        if index < len(evidence_preview):
            st.divider()


def _render_agent_debug_trace(debug: dict | None) -> None:
    if not debug:
        st.caption("该轮问答未保留 Debug 信息。")
        return

    tool_trace = debug.get("tool_trace") or []
    reasoning = debug.get("reasoning_snapshot") or {}
    memory = debug.get("memory_snapshot") or {}
    evidence_preview = debug.get("retrieved_evidence_preview") or []

    tab_tool, tab_reasoning, tab_memory, tab_evidence = st.tabs(
        ["工具轨迹", "推理快照", "记忆快照", "证据预览"]
    )

    with tab_tool:
        _render_tool_trace(tool_trace)

    with tab_reasoning:
        _render_reasoning_snapshot(reasoning)

    with tab_memory:
        _render_memory_snapshot(memory)

    with tab_evidence:
        _render_evidence_preview(evidence_preview)

    message_count = debug.get("message_count")
    if message_count is not None:
        st.caption(f"message_count: {message_count}")


def _format_health_error(exc: requests.RequestException, action: str) -> str:
    if isinstance(exc, requests.Timeout):
        return f"{action}请求超时，请稍后重试。"
    if isinstance(exc, requests.ConnectionError):
        return f"无法连接工业预测 API，请确认 HEALTH_API_URL 正确且服务已启动。"
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        if response is not None:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            return f"{action}失败（HTTP {response.status_code}）：{detail}"
        return f"{action}失败：{exc}"
    return f"{action}时发生网络错误：{exc}"


def fetch_health_model_info(health_api_url: str) -> dict:
    response = requests.get(
        f"{health_api_url}/model-info",
        timeout=HEALTH_API_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "features": payload.get("features", []),
        "numeric_features": payload.get("numeric_features", []),
        "categorical_features": payload.get("categorical_features", []),
        "metrics": payload.get("metrics", {}),
        "classes": payload.get("classes", []),
    }


def call_health_predict(features: dict, health_api_url: str) -> dict:
    response = requests.post(
        f"{health_api_url}/predict",
        json={"features": features},
        timeout=HEALTH_API_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _normalize_feature_list(features: list) -> list[str]:
    if not features:
        return []
    if isinstance(features[0], str):
        return [name for name in features if name]
    if isinstance(features[0], dict):
        names: list[str] = []
        for item in features:
            name = item.get("name") or item.get("feature")
            if name:
                names.append(name)
        return names
    return [str(item) for item in features if item is not None]


def _load_health_model_info(health_api_url: str, force: bool = False) -> dict | None:
    if (
        not force
        and st.session_state.get("health_model_info_url") == health_api_url
        and st.session_state.get("health_model_info")
    ):
        return st.session_state.health_model_info

    try:
        model_info = fetch_health_model_info(health_api_url)
        st.session_state.health_model_info = model_info
        st.session_state.health_model_info_url = health_api_url
        return model_info
    except requests.RequestException as exc:
        st.error(_format_health_error(exc, "获取模型信息"))
        return None


def _render_health_prediction_tab() -> None:
    st.subheader("设备健康预测")

    health_api_url = _normalize_base_url(
        st.text_input(
            "HEALTH_API_URL",
            value=os.getenv("HEALTH_API_URL", DEFAULT_HEALTH_API_URL),
            help="工业预测 API 地址，可通过环境变量 HEALTH_API_URL 覆盖默认值。",
            key="health_api_url_input",
        )
    )

    load_clicked = st.button("获取模型信息", key="load_health_model_info")

    model_info = None
    if load_clicked:
        with st.spinner("正在获取模型信息..."):
            model_info = _load_health_model_info(health_api_url, force=True)
            if model_info is not None:
                st.session_state.pop("health_prediction_result", None)
    elif st.session_state.get("health_model_info_url") == health_api_url:
        model_info = st.session_state.get("health_model_info")

    if not model_info:
        st.info("请先点击「获取模型信息」，从工业预测 API 加载模型 schema。")
        return

    numeric_features = _normalize_feature_list(model_info.get("numeric_features", []))
    categorical_features = _normalize_feature_list(model_info.get("categorical_features", []))
    fallback_features = _normalize_feature_list(model_info.get("features", []))

    if not numeric_features and not categorical_features:
        numeric_features = fallback_features

    if not numeric_features and not categorical_features:
        st.warning("模型未返回有效的特征字段，无法生成输入框。")
        st.json(model_info)
        return

    classes = model_info.get("classes") or []
    metrics = model_info.get("metrics") or {}
    if classes:
        st.caption(f"类别 classes: {', '.join(str(c) for c in classes)}")
    if metrics:
        with st.expander("模型指标 metrics", expanded=False):
            st.json(metrics)

    st.caption(
        f"数值特征 {len(numeric_features)} 项 · 类别特征 {len(categorical_features)} 项"
    )

    feature_values: dict = {}
    input_cols = st.columns(2)

    for index, feature_name in enumerate(numeric_features):
        with input_cols[index % 2]:
            feature_values[feature_name] = st.number_input(
                feature_name,
                value=0.0,
                key=f"health_numeric_{feature_name}",
            )

    col_offset = len(numeric_features)
    for index, feature_name in enumerate(categorical_features):
        with input_cols[(col_offset + index) % 2]:
            feature_values[feature_name] = st.text_input(
                feature_name,
                value="",
                key=f"health_categorical_{feature_name}",
            )

    if st.button("预测设备健康状态", type="primary", key="predict_device_health"):
        with st.spinner("正在预测设备健康状态..."):
            try:
                result = call_health_predict(feature_values, health_api_url)
                st.session_state.health_prediction_result = result
            except requests.RequestException as exc:
                st.error(_format_health_error(exc, "健康预测"))
                return

    result = st.session_state.get("health_prediction_result")
    if not result:
        return

    st.divider()
    st.subheader("预测结果")

    prediction = result.get("prediction")
    risk_level = result.get("risk_level")
    recommendation = result.get("recommendation")
    probabilities = result.get("probabilities")

    metric_cols = st.columns(2)
    with metric_cols[0]:
        st.metric("prediction", str(prediction) if prediction is not None else "—")
    with metric_cols[1]:
        st.metric("risk_level", str(risk_level) if risk_level is not None else "—")

    st.markdown("**recommendation**")
    if recommendation:
        st.info(recommendation)
    else:
        st.caption("（无）")

    st.markdown("**probabilities**")
    if isinstance(probabilities, dict) and probabilities:
        for label, prob in probabilities.items():
            if isinstance(prob, (int, float)):
                st.markdown(f"`{label}`: {prob:.2%}")
                st.progress(min(max(float(prob), 0.0), 1.0))
            else:
                st.markdown(f"`{label}`: {prob}")
    elif probabilities is not None:
        st.json(probabilities)
    else:
        st.caption("（无）")


def _format_request_error(exc: requests.RequestException) -> str:
    if isinstance(exc, requests.Timeout):
        return "上传请求超时，PDF 向量化可能耗时较长，请稍后重试。"
    if isinstance(exc, requests.ConnectionError):
        return "无法连接后端，请确认 API 地址正确且服务已启动。"
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        if response is not None:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            return f"上传失败（HTTP {response.status_code}）：{detail}"
        return f"上传失败：{exc}"
    return f"上传时发生网络错误：{exc}"


def _format_auth_error(exc: Exception, action: str) -> str:
    if isinstance(exc, requests.Timeout):
        return f"{action}请求超时，请稍后重试。"
    if isinstance(exc, requests.ConnectionError):
        return "无法连接后端，请确认 API 地址正确且服务已启动。"
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        if response is not None:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            return f"{action}失败（HTTP {response.status_code}）：{detail}"
        return f"{action}失败：{exc}"
    if isinstance(exc, ValueError):
        return str(exc)
    return f"{action}时发生错误：{exc}"


def _clear_user_scoped_state() -> None:
    _clear_knowledge_base_session()
    for key in (
        "sidebar_documents",
        "active_kb_ids",
        "qa_logs_cache",
        "qa_logs_cache_key",
        SIDEBAR_KB_SELECT_KEY,
    ):
        st.session_state.pop(key, None)


def _render_auth_panel(api_base_url: str, reachable: bool) -> None:
    st.subheader("用户登录")

    if st.session_state.auth_token:
        st.success(f"已登录：{st.session_state.auth_email}")
        if st.button("退出登录", key="logout_button"):
            st.session_state.auth_token = None
            st.session_state.auth_email = None
            st.session_state.auth_status = None
            _clear_user_scoped_state()
            st.rerun()
        return

    email = st.text_input(
        "Email",
        value=os.getenv("DEMO_EMAIL", "demo@example.com"),
        key="auth_email_input",
    )
    password = st.text_input(
        "Password",
        type="password",
        value=os.getenv("DEMO_PASSWORD", "password123"),
        key="auth_password_input",
    )
    disabled = not reachable or not email or not password

    col_login, col_register = st.columns(2)
    with col_login:
        login_clicked = st.button("登录", disabled=disabled, key="login_button")
    with col_register:
        register_clicked = st.button("注册并登录", disabled=disabled, key="register_login_button")

    if login_clicked or register_clicked:
        try:
            if register_clicked:
                try:
                    register_user(api_base_url, email, password)
                except requests.HTTPError as exc:
                    if exc.response is None or exc.response.status_code != 409:
                        raise
            token = login_user(api_base_url, email, password)
            st.session_state.auth_token = token
            st.session_state.auth_email = email
            st.session_state.auth_status = "logged_in"
            _clear_user_scoped_state()
            st.rerun()
        except Exception as exc:
            action = "注册或登录" if register_clicked else "登录"
            st.error(_format_auth_error(exc, action))


def _render_knowledge_base_status(active_kb_ids: set[str]) -> None:
    st.subheader("当前知识库状态")

    kb_id = st.session_state.knowledge_base_id
    kb_active = _is_kb_active(kb_id, active_kb_ids)

    if kb_id:
        if kb_active:
            st.success("当前文档已入库，可通过 pgvector 检索；内存 FAISS fallback 也已加载。")
        else:
            st.info(
                "当前文档已保存在 PostgreSQL + pgvector，可继续问答。"
                "内存 FAISS fallback 未加载，通常是后端重启后的正常状态。"
            )

        col1, col2 = st.columns(2)
        with col1:
            st.metric("文本块数量", st.session_state.chunks_count or 0)
        with col2:
            display_status = "pgvector + FAISS" if kb_active else "pgvector"
            st.metric("问答状态", display_status)

        st.markdown(f"**knowledge_base_id:** `{kb_id}`")
        st.markdown(f"**filename:** `{st.session_state.upload_filename or '-'}`")
        st.markdown(f"**chunks_count:** `{st.session_state.chunks_count}`")
        st.markdown(
            f"**数据库 status:** `{st.session_state.upload_status or '-'}` "
            f"（表示文档、chunks 与 embeddings 已入库）"
        )
        if st.session_state.upload_message:
            st.markdown(f"**message:** {st.session_state.upload_message}")
    else:
        st.info("尚未选择文档。请在侧边栏上传 PDF 构建，或从文档列表中选择。")


def _load_sidebar_catalog(
    api_base_url: str,
    token: str,
    force_refresh: bool,
) -> tuple[list[dict], set[str]]:
    documents: list[dict] = st.session_state.get("sidebar_documents", [])
    active_kb_ids: set[str] = st.session_state.get("active_kb_ids", set())

    if (
        force_refresh
        or "sidebar_documents" not in st.session_state
        or "active_kb_ids" not in st.session_state
    ):
        documents = fetch_documents(api_base_url, token)
        active_kb_ids = fetch_active_knowledge_base_ids(api_base_url)
        st.session_state.sidebar_documents = documents
        st.session_state.active_kb_ids = active_kb_ids

    return documents, active_kb_ids


def _render_sidebar_documents(api_base_url: str, token: str | None, reachable: bool) -> set[str]:
    st.subheader("知识库选择")

    if not reachable:
        st.caption("后端不可访问，无法加载文档列表。")
        return set()

    if not token:
        st.info("请先登录，再加载当前用户的文档列表。")
        return set()

    refresh_clicked = st.button("刷新列表", key="refresh_documents")

    try:
        documents, active_kb_ids = _load_sidebar_catalog(api_base_url, token, refresh_clicked)
    except requests.RequestException as exc:
        st.error(_format_list_error(exc, "文档或知识库列表"))
        return st.session_state.get("active_kb_ids", set())

    available_docs = documents
    pgvector_only_docs = [doc for doc in documents if doc["knowledge_base_id"] not in active_kb_ids]

    st.caption(f"文档记录：{len(documents)} 条 · 内存 FAISS fallback 已加载：{len(active_kb_ids)} 个")

    if available_docs:
        current_kb = st.session_state.knowledge_base_id
        option_indices = list(range(len(available_docs) + 1))

        def _format_available_option(index: int) -> str:
            if index == 0:
                return "（未选择 - 请先选择或上传 PDF）"
            doc = available_docs[index - 1]
            marker = "pgvector + FAISS" if doc["knowledge_base_id"] in active_kb_ids else "pgvector"
            return (
                f"{marker} · {doc['filename']} · {doc['chunks_count']} 块 · "
                f"{doc['created_at'][:19]}"
            )

        if _find_kb_select_index(available_docs, current_kb) > 0:
            _sync_sidebar_kb_select(available_docs, current_kb)
        elif SIDEBAR_KB_SELECT_KEY not in st.session_state:
            st.session_state[SIDEBAR_KB_SELECT_KEY] = 0

        selected_index = st.selectbox(
            "文档 / 知识库",
            option_indices,
            format_func=_format_available_option,
            key=SIDEBAR_KB_SELECT_KEY,
        )

        if selected_index == 0:
            if _find_kb_select_index(available_docs, st.session_state.knowledge_base_id) > 0:
                _sync_sidebar_kb_select(available_docs, st.session_state.knowledge_base_id)
                st.rerun()
        else:
            selected_doc = available_docs[selected_index - 1]
            selected_kb = selected_doc["knowledge_base_id"]
            if selected_kb != st.session_state.knowledge_base_id:
                _apply_document_to_session(selected_doc)
                st.session_state.history = []
                st.rerun()
    else:
        st.warning("当前没有已入库文档。请上传 PDF 构建知识库。")
        if st.session_state.knowledge_base_id:
            _clear_knowledge_base_session()
            st.rerun()

    if pgvector_only_docs:
        with st.expander(f"pgvector 持久化文档（{len(pgvector_only_docs)} 条，内存 FAISS fallback 未加载）"):
            for doc in pgvector_only_docs:
                st.markdown(
                    f"**{doc['filename']}** · {doc['chunks_count']} 块 · "
                    f"`{doc['knowledge_base_id'][:8]}...`"
                )
                st.caption(f"上传于 {doc['created_at'][:19]} · 数据库 status: {doc.get('status', '-')}")

    if not documents:
        st.caption("暂无已上传文档记录。")

    return active_kb_ids


def _render_chat_tab(api_base_url: str, active_kb_ids: set[str]) -> None:
    _render_knowledge_base_status(active_kb_ids)
    st.divider()
    st.subheader("对话")

    kb_id = st.session_state.knowledge_base_id
    auth_token = st.session_state.auth_token
    can_chat = bool(kb_id) and st.session_state.backend_reachable and bool(auth_token)

    if not auth_token:
        st.warning("请先在侧边栏登录，再上传文档或提问。")
    elif not kb_id:
        st.warning("请先上传 PDF 并构建知识库，或从侧边栏文档列表中选择后再提问。")

    for turn in st.session_state.history:
        normalized = _normalize_turn(turn)
        with st.chat_message("user"):
            st.markdown(normalized["user"])
        with st.chat_message("assistant"):
            st.markdown(normalized["assistant"])
            with st.expander("Agent 推理步骤 / Debug Trace", expanded=False):
                _render_agent_debug_trace(normalized.get("debug"))

    if prompt := st.chat_input(
        "请输入你的问题...",
        disabled=not can_chat,
    ):
        if not auth_token:
            st.warning("请先在侧边栏登录。")
        elif not kb_id:
            st.warning("请先上传 PDF 或选择一个文档后再提问。")
        elif not st.session_state.backend_reachable:
            st.error(st.session_state.backend_check_error or "后端不可访问，无法提问。")
        else:
            with st.spinner("正在思考，请稍候..."):
                try:
                    result = ask_question(
                        api_base_url,
                        prompt,
                        st.session_state.knowledge_base_id,
                        st.session_state.history,
                        st.session_state.auth_token,
                    )
                    st.session_state.history = _merge_history_with_debug(
                        result.get("history", []),
                        st.session_state.history,
                        result.get("debug"),
                    )
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(_format_ask_error(exc))


def _render_qa_history_tab(api_base_url: str, token: str | None) -> None:
    st.subheader("历史问答")

    if not token:
        st.info("请先登录，再查看当前用户的历史问答。")
        return

    documents: list[dict] = st.session_state.get("sidebar_documents", [])
    if not documents:
        st.info("请先在侧边栏刷新列表，或上传 PDF 后再查看历史问答。")
        return

    doc_options = {doc["knowledge_base_id"]: doc for doc in documents}
    kb_ids = list(doc_options.keys())

    def _format_history_kb(kb: str) -> str:
        doc = doc_options[kb]
        return f"{doc['filename']} · {doc['chunks_count']} 块 · {kb[:8]}..."

    default_kb = st.session_state.knowledge_base_id
    default_index = kb_ids.index(default_kb) if default_kb in kb_ids else 0

    selected_kb = st.selectbox(
        "选择要查看的历史知识库",
        kb_ids,
        format_func=_format_history_kb,
        index=default_index,
        key="history_kb_select",
    )

    st.caption(f"知识库：`{selected_kb}`（历史记录来自 PostgreSQL；检索主路径使用 pgvector）")

    col_refresh, col_limit = st.columns([1, 2])
    with col_refresh:
        reload_clicked = st.button("刷新历史", key="refresh_qa_logs")
    with col_limit:
        log_limit = st.number_input(
            "显示条数",
            min_value=1,
            max_value=500,
            value=100,
            step=10,
            key="qa_log_limit",
        )

    if reload_clicked:
        st.session_state.pop("qa_logs_cache", None)

    qa_logs: list[dict] = []
    cache_key = f"{selected_kb}:{log_limit}"
    if st.session_state.get("qa_logs_cache_key") == cache_key:
        qa_logs = st.session_state.get("qa_logs_cache", [])
    else:
        with st.spinner("正在加载历史问答..."):
            try:
                qa_logs = fetch_qa_logs(
                    api_base_url,
                    token,
                    selected_kb,
                    limit=int(log_limit),
                )
                st.session_state.qa_logs_cache = qa_logs
                st.session_state.qa_logs_cache_key = cache_key
            except requests.RequestException as exc:
                st.error(_format_list_error(exc, "历史问答"))
                return

    if not qa_logs:
        st.caption("该知识库暂无历史问答记录。")
        return

    st.markdown(f"共 **{len(qa_logs)}** 条记录（按时间倒序）")

    for index, log in enumerate(qa_logs, start=1):
        created_at = log.get("created_at", "")
        mode = log.get("mode", "unknown")
        with st.container(border=True):
            st.markdown(f"**#{index}** · `{created_at[:19]}` · mode: `{mode}`")
            with st.chat_message("user"):
                st.markdown(log.get("question", ""))
            with st.chat_message("assistant"):
                st.markdown(log.get("answer", ""))
                debug = log.get("debug")
                if debug:
                    with st.expander("Agent 推理步骤 / Debug Trace", expanded=False):
                        _render_agent_debug_trace(debug)


def _render_debug_help_tab() -> None:
    st.subheader("调试说明")

    st.markdown(
        """
        本页面在问答时默认开启 `debug=True`，每轮对话可在 **Agent 推理步骤 / Debug Trace**
        展开查看以下信息：
        """
    )

    st.markdown(
        """
        | 面板 | 说明 |
        | --- | --- |
        | **工具轨迹** | Agent 调用了哪些工具、输入参数与输出预览 |
        | **推理快照** | 子问题拆分、检索轮次、决策类型 |
        | **记忆快照** | 当前问题、会话历史摘要 |
        | **证据预览** | 检索到的文档片段预览 |
        """
    )

    st.divider()
    st.markdown("**相关 API**")
    st.code(
        "\n".join(
            [
                "GET  /documents/                          # 最近上传文档（PostgreSQL）",
                "GET  /knowledge_bases                     # 当前内存 FAISS fallback 状态",
                "GET  /qa_logs/?knowledge_base_id=...      # 历史问答",
                "POST /documents/upload                    # 上传 PDF",
                "POST /ask                                 # RAG + LangGraph Agent 问答（debug=true）",
                "GET  /health (predictive-maintenance-mini)     # 设备健康预测服务",
                "POST /predict (predictive-maintenance-mini)    # 传感器参数预测",
            ]
        ),
        language="text",
    )

    st.markdown(
        """
        **设备健康预测**（独立 Tab）通过 `HEALTH_API_URL`（默认 `http://127.0.0.1:8010`）
        调用 predictive-maintenance-mini 的 `/model-info` 与 `/predict`，与 PDF 问答链路互不干扰。
        """
    )

    st.divider()
    st.markdown("**后端连接状态**")
    if st.session_state.backend_reachable:
        st.success("后端 /openapi.json 可访问")
    else:
        st.error(st.session_state.backend_check_error or "后端不可访问")

    if st.session_state.last_upload_response:
        st.divider()
        st.markdown("**最近一次上传响应**")
        st.json(st.session_state.last_upload_response)


_init_session_state()

with st.sidebar:
    st.header("配置")
    api_base_url = _normalize_base_url(
        st.text_input(
            "API_BASE_URL",
            value=os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL),
            help="FastAPI 后端地址，可通过环境变量 API_BASE_URL 覆盖默认值。",
        )
    )

    st.subheader("后端连接")
    reachable, error_message = check_backend_openapi(api_base_url)
    st.session_state.backend_reachable = reachable
    st.session_state.backend_check_error = error_message

    if reachable:
        st.success("后端 /openapi.json 可访问")
    else:
        st.error(error_message or "后端不可访问")

    st.divider()
    _render_auth_panel(api_base_url, reachable)

    st.divider()
    active_kb_ids = _render_sidebar_documents(api_base_url, st.session_state.auth_token, reachable)

    st.divider()
    st.subheader("知识库构建")
    uploaded_input = st.file_uploader(
        "上传 PDF 文件",
        type=["pdf"],
        accept_multiple_files=True,
        help="选择 1 个 PDF 将自动设为当前知识库；选择多个 PDF 批量构建后请手动选择要问答的文档。",
    )
    uploaded_files = _normalize_uploaded_files(uploaded_input)

    build_clicked = st.button(
        "构建 / 更新知识库",
        type="primary",
        disabled=not uploaded_files or not reachable or not st.session_state.auth_token,
    )

    if build_clicked:
        if not st.session_state.auth_token:
            st.warning("请先登录，再上传 PDF。")
        elif not uploaded_files:
            st.warning("请先选择 PDF 文件。")
        elif len(uploaded_files) == 1:
            with st.spinner("正在上传并构建向量库，请稍候..."):
                try:
                    result = upload_pdf(api_base_url, uploaded_files[0], st.session_state.auth_token)
                    _apply_single_upload_result(result)
                    st.success("知识库构建成功，已自动设为当前文档，可直接开始问答。")
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(_format_request_error(exc))
        else:
            with st.spinner(f"正在批量上传 {len(uploaded_files)} 个 PDF，请稍候..."):
                try:
                    result = upload_pdfs(api_base_url, uploaded_files, st.session_state.auth_token)
                    _apply_batch_upload_result(result)
                    uploaded_count = result.get("total_uploaded", 0)
                    failed_count = result.get("total_failed", 0)
                    if uploaded_count > 0:
                        st.success(
                            f"批量构建完成：成功 {uploaded_count} 个，失败 {failed_count} 个。"
                            "请从上方文档列表中选择要问答的文档。"
                        )
                    else:
                        st.error(f"批量构建失败：{failed_count} 个文件均未成功。")
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(_format_request_error(exc))

tab_chat, tab_history, tab_debug, tab_health = st.tabs(
    ["聊天", "历史记录", "调试说明", "设备健康预测"]
)

with tab_chat:
    _render_chat_tab(api_base_url, active_kb_ids if reachable else set())

with tab_history:
    _render_qa_history_tab(api_base_url, st.session_state.auth_token)

with tab_debug:
    _render_debug_help_tab()

with tab_health:
    _render_health_prediction_tab()
