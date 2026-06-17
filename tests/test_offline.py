"""Offline unit tests (no DashScope / network required)."""

from app.tools.common import kb_not_found_message
from app.tools.document_tools import _normalize_text, _sanitize_heading, _unique_keep_order
from app.services import kb_registry


def test_unique_keep_order():
    assert _unique_keep_order(["a", "b", "a", "", "c"]) == ["a", "b", "c"]


def test_normalize_text():
    assert _normalize_text("  hello   world  ") == "hello world"


def test_sanitize_heading_strips_nested_number():
    result = _sanitize_heading("1.1 软件工程概述 1.2 下一节")
    assert "1.2" not in result


def test_kb_not_found_message_empty_registry():
    kb_registry.clear_all_knowledge_bases()
    msg = kb_not_found_message("missing-id")
    assert "missing-id" in msg
    assert "请先上传" in msg
