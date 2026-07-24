from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

TRACE_LOGGER_NAME = "agent_traces"
trace_logger = logging.getLogger(TRACE_LOGGER_NAME)


def _truncate(text: str, limit: int = 180) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _summarize_list(items: list[Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"type": "list", "count": len(items)}
    if not items:
        return summary

    first = items[0]
    if isinstance(first, dict):
        summary["first_keys"] = sorted(list(first.keys()))[:8]
        for key in ("chunk_id", "document_id", "score", "final_score", "risk_level", "ticket_id"):
            if key in first:
                summary[key] = first.get(key)
    else:
        summary["preview"] = [_truncate(str(item)) for item in items[:3]]
    return summary


def summarize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate(value)
    if isinstance(value, dict):
        summary: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"trace_recorder", "messages"}:
                continue
            if key in {"content", "answer", "final_answer", "draft_answer", "confirmation_message"}:
                summary[key] = _truncate(item)
            elif key in {"retrieved_chunks", "sources", "maintenance_plan", "tools_used", "errors"}:
                summary[key] = _summarize_list(item if isinstance(item, list) else [])
            else:
                summary[key] = summarize_value(item)
        return summary
    if isinstance(value, list):
        return _summarize_list(value)
    return _truncate(str(value))


@dataclass
class AgentTraceRecorder:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    events: list[dict[str, Any]] = field(default_factory=list)
    logger: logging.Logger = field(default=trace_logger)

    def record(
        self,
        *,
        node_name: str,
        tool_name: str,
        input_summary: Any,
        output_summary: Any,
        latency_ms: int,
        error: str | None = None,
    ) -> dict[str, Any]:
        event = {
            "trace_id": self.trace_id,
            "node_name": node_name,
            "tool_name": tool_name,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "latency_ms": latency_ms,
            "error": error,
        }
        self.events.append(event)
        self.logger.info("%s", json.dumps(event, ensure_ascii=False, default=str))
        return event


def run_node_with_trace(
    state: dict[str, Any],
    *,
    node_name: str,
    tool_name: str,
    node_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    recorder = state.get("trace_recorder")
    input_summary = summarize_value(state)
    started_at = time.perf_counter()
    output: dict[str, Any] | None = None
    error: str | None = None

    try:
        output = node_fn(state)
        return output
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        if isinstance(recorder, AgentTraceRecorder):
            recorder.record(
                node_name=node_name,
                tool_name=tool_name,
                input_summary=input_summary,
                output_summary=summarize_value(output) if output is not None else None,
                latency_ms=latency_ms,
                error=error,
            )
