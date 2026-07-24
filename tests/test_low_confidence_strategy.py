from app.retrievers.confidence import LOW_CONFIDENCE_ANSWER
from app.schemas.chat_state import ChatState
from app.services.chat_service import chat_with_rag_state


def test_low_confidence_rag_answer_does_not_generate(monkeypatch):
    monkeypatch.setattr("app.retrievers.confidence.RAG_MIN_CONFIDENCE", 0.8)
    monkeypatch.setattr(
        "app.services.chat_service.retrieve_relevant_chunks_pgvector",
        lambda **_kwargs: (
            ["weak evidence"],
            None,
            [
                {
                    "chunk_id": "chunk-low",
                    "document_id": "doc-low",
                    "content": "weak evidence",
                    "score": 0.2,
                    "source_metadata": {"document_filename": "low.pdf"},
                }
            ],
        ),
    )

    def fail_generate_answer(**_kwargs):
        raise AssertionError("generate_answer should not be called for low confidence")

    monkeypatch.setattr("app.services.chat_service.generate_answer", fail_generate_answer)

    answer, history, metadata = chat_with_rag_state(
        ChatState(
            knowledge_base_id="doc-low",
            user_id="user-low",
            user_query="question",
        )
    )

    assert answer == LOW_CONFIDENCE_ANSWER
    assert history[-1] == ("question", LOW_CONFIDENCE_ANSWER)
    assert metadata["confidence"] == 0.2
    assert metadata["sources"][0]["chunk_id"] == "chunk-low"


def test_high_confidence_rag_answer_still_generates(monkeypatch):
    monkeypatch.setattr("app.retrievers.confidence.RAG_MIN_CONFIDENCE", 0.8)
    monkeypatch.setattr(
        "app.services.chat_service.retrieve_relevant_chunks_pgvector",
        lambda **_kwargs: (
            ["strong evidence"],
            None,
            [
                {
                    "chunk_id": "chunk-high",
                    "document_id": "doc-high",
                    "content": "strong evidence",
                    "score": 0.95,
                    "source_metadata": {"document_filename": "high.pdf"},
                }
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.chat_service.generate_answer",
        lambda **_kwargs: ("generated answer", [("question", "generated answer")]),
    )

    answer, history, metadata = chat_with_rag_state(
        ChatState(
            knowledge_base_id="doc-high",
            user_id="user-high",
            user_query="question",
        )
    )

    assert answer == "generated answer"
    assert history[-1] == ("question", "generated answer")
    assert metadata["confidence"] == 0.95
    assert metadata["sources"][0]["chunk_id"] == "chunk-high"
