from app.core.config import FIXED_DIMENSION
from app.services.embedding_service import (
    FakeEmbeddingProvider,
    get_embedding_model_name,
    get_embedding_provider,
)


def test_fake_embedding_provider_is_deterministic():
    provider = FakeEmbeddingProvider()

    embeddings, dimension = provider.embed_texts(["same text", "same text"])

    assert dimension == FIXED_DIMENSION
    assert len(embeddings) == 2
    assert len(embeddings[0]) == FIXED_DIMENSION
    assert embeddings[0] == embeddings[1]


def test_test_environment_uses_fake_embedding_provider():
    assert get_embedding_provider().name == "fake"
    assert get_embedding_model_name() == "fake-hash-embedding"
