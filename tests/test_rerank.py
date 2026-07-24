from app.retrievers.rerank import RerankerService


def test_mock_reranker_reorders_candidates_and_keeps_rerank_score():
    candidates = [
        {
            "chunk_id": "1",
            "content": "billing invoice payment",
            "final_score": 0.9,
            "source_metadata": {},
        },
        {
            "chunk_id": "2",
            "content": "pump bearing thermal failure maintenance",
            "final_score": 0.1,
            "source_metadata": {},
        },
    ]

    results = RerankerService(provider="mock").rerank(
        query="pump thermal failure",
        candidate_chunks=candidates,
        top_k=2,
    )

    assert [item["chunk_id"] for item in results] == ["2", "1"]
    assert results[0]["rerank_score"] > results[1]["rerank_score"]
    assert results[0]["source_metadata"]["reranker"] == {
        "provider": "mock",
        "rank": 1,
        "score": results[0]["rerank_score"],
    }


def test_none_reranker_preserves_order_and_sets_rerank_score():
    candidates = [
        {"chunk_id": "1", "content": "a", "final_score": 0.2, "source_metadata": {}},
        {"chunk_id": "2", "content": "b", "final_score": 0.1, "source_metadata": {}},
    ]

    results = RerankerService(provider="none").rerank(
        query="anything",
        candidate_chunks=candidates,
    )

    assert [item["chunk_id"] for item in results] == ["1", "2"]
    assert [item["rerank_score"] for item in results] == [0.2, 0.1]
