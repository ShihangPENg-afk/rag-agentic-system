import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
UPLOAD_TIMEOUT_SECONDS = 300
ASK_TIMEOUT_SECONDS = 300
BACKEND_CHECK_TIMEOUT_SECONDS = 5
LIST_TIMEOUT_SECONDS = 30


st.set_page_config(
    page_title="Agentic RAG 文档问答助手",
    page_icon="📄",
    layout="wide",
)

st.title("Agentic RAG 文档问答助手")


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
        "selected_kb_from_list": None,
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


def fetch_documents(api_base_url: str, limit: int = 50) -> list[dict]:
    response = requests.get(
        f"{api_base_url}/documents/",
        params={"limit": limit},
        timeout=LIST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json().get("documents", [])


def fetch_qa_logs(
    api_base_url: str,
    knowledge_base_id: str,
    limit: int = 100,
) -> list[dict]:
    response = requests.get(
        f"{api_base_url}/qa_logs/",
        params={"knowledge_base_id": knowledge_base_id, "limit": limit},
        timeout=LIST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json().get("qa_logs", [])


def upload_pdf(api_base_url: str, uploaded_file) -> dict:
    response = requests.post(
        f"{api_base_url}/upload_pdf/",
        files={"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")},
        timeout=UPLOAD_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _history_for_request(history: list) -> list[dict]:
    normalized = [_normalize_turn(turn) for turn in history]
    return [{"user": turn["user"], "assistant": turn["assistant"]} for turn in normalized]


def ask_question(
    api_base_url: str,
    question: str,
    knowledge_base_id: str,
    history: list,
) -> dict:
    response = requests.post(
        f"{api_base_url}/ask/",
        json={
            "question": question,
            "knowledge_base_id": knowledge_base_id,
            "history": _history_for_request(history),
            "debug": True,
        },
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


def _render_knowledge_base_status() -> None:
    st.subheader("当前知识库状态")

    if st.session_state.knowledge_base_id:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("文本块数量", st.session_state.chunks_count or 0)
        with col2:
            st.metric("状态", st.session_state.upload_status or "unknown")

        st.markdown(f"**knowledge_base_id:** `{st.session_state.knowledge_base_id}`")
        st.markdown(f"**filename:** `{st.session_state.upload_filename or '-'}`")
        st.markdown(f"**chunks_count:** `{st.session_state.chunks_count}`")
        st.markdown(f"**status:** `{st.session_state.upload_status or '-'}`")
        if st.session_state.upload_message:
            st.markdown(f"**message:** {st.session_state.upload_message}")
    else:
        st.info("尚未选择知识库。请在侧边栏上传 PDF 构建，或从最近文档中选择已有知识库。")


def _render_sidebar_documents(api_base_url: str, reachable: bool) -> None:
    st.subheader("最近文档")

    if not reachable:
        st.caption("后端不可访问，无法加载文档列表。")
        return

    refresh_clicked = st.button("刷新文档列表", key="refresh_documents")

    documents: list[dict] = []
    if refresh_clicked or "sidebar_documents" not in st.session_state:
        try:
            documents = fetch_documents(api_base_url)
            st.session_state.sidebar_documents = documents
        except requests.RequestException as exc:
            st.error(_format_list_error(exc, "文档列表"))
            documents = st.session_state.get("sidebar_documents", [])
    else:
        documents = st.session_state.get("sidebar_documents", [])

    if not documents:
        st.caption("暂无已上传文档。")
        return

    kb_ids = [doc["knowledge_base_id"] for doc in documents]
    labels = [
        f"{doc['filename']} · {doc['chunks_count']} 块 · {doc['created_at'][:19]}"
        for doc in documents
    ]

    current_kb = st.session_state.knowledge_base_id
    default_index = kb_ids.index(current_kb) if current_kb in kb_ids else 0

    selected_index = st.selectbox(
        "选择知识库",
        range(len(documents)),
        format_func=lambda i: labels[i],
        index=default_index,
        key="sidebar_kb_select",
    )
    selected_doc = documents[selected_index]
    selected_kb = selected_doc["knowledge_base_id"]

    if selected_kb != st.session_state.knowledge_base_id:
        _apply_document_to_session(selected_doc)
        st.session_state.history = []
        st.rerun()

    st.caption(f"共 {len(documents)} 条最近文档")


def _render_chat_tab(api_base_url: str) -> None:
    _render_knowledge_base_status()
    st.divider()
    st.subheader("对话")

    has_knowledge_base = bool(st.session_state.knowledge_base_id)
    can_chat = has_knowledge_base and st.session_state.backend_reachable

    if not has_knowledge_base:
        st.warning("请先上传 PDF 并构建知识库，或从侧边栏选择已有知识库后再提问。")

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
        if not has_knowledge_base:
            st.warning("请先上传 PDF 并构建知识库后再提问。")
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
                    )
                    st.session_state.history = _merge_history_with_debug(
                        result.get("history", []),
                        st.session_state.history,
                        result.get("debug"),
                    )
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(_format_ask_error(exc))


def _render_qa_history_tab(api_base_url: str) -> None:
    st.subheader("历史问答")

    if not st.session_state.knowledge_base_id:
        st.info("请先在侧边栏选择或构建知识库，再查看历史问答。")
        return

    st.caption(f"知识库：`{st.session_state.knowledge_base_id}`")

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
    cache_key = f"{st.session_state.knowledge_base_id}:{log_limit}"
    if st.session_state.get("qa_logs_cache_key") == cache_key:
        qa_logs = st.session_state.get("qa_logs_cache", [])
    else:
        with st.spinner("正在加载历史问答..."):
            try:
                qa_logs = fetch_qa_logs(
                    api_base_url,
                    st.session_state.knowledge_base_id,
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
                "GET  /documents/                          # 最近上传文档",
                "GET  /qa_logs/?knowledge_base_id=...      # 历史问答",
                "POST /upload_pdf/                         # 上传 PDF",
                "POST /ask/                                # Agent 问答（debug=true）",
            ]
        ),
        language="text",
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
    _render_sidebar_documents(api_base_url, reachable)

    st.divider()
    st.subheader("知识库构建")
    uploaded_file = st.file_uploader("上传 PDF 文件", type=["pdf"])

    build_clicked = st.button(
        "构建 / 更新向量库",
        type="primary",
        disabled=uploaded_file is None or not reachable,
    )

    if build_clicked:
        if uploaded_file is None:
            st.warning("请先选择 PDF 文件。")
        else:
            with st.spinner("正在上传并构建向量库，请稍候..."):
                try:
                    result = upload_pdf(api_base_url, uploaded_file)
                    st.session_state.last_upload_response = result
                    st.session_state.knowledge_base_id = result.get("knowledge_base_id")
                    st.session_state.upload_filename = result.get("filename")
                    st.session_state.chunks_count = result.get("chunks_count")
                    st.session_state.upload_status = result.get("status")
                    st.session_state.upload_message = result.get("message")
                    st.session_state.history = []
                    st.session_state.pop("sidebar_documents", None)
                    st.session_state.pop("qa_logs_cache", None)
                    st.session_state.pop("qa_logs_cache_key", None)
                    st.success("向量库构建成功")
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(_format_request_error(exc))

tab_chat, tab_history, tab_debug = st.tabs(["聊天", "历史记录", "调试说明"])

with tab_chat:
    _render_chat_tab(api_base_url)

with tab_history:
    _render_qa_history_tab(api_base_url)

with tab_debug:
    _render_debug_help_tab()
