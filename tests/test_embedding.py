import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.omnimcp.services.embedding import EmbeddingService


@pytest.fixture
def embedding_service():
    return EmbeddingService(
        api_key="test-api-key",
        embedding_model_name="text-embedding-3-small",
        dimension=1024
    )


class TestEmbeddingServiceInit:
    def test_initialization(self, embedding_service):
        assert embedding_service.api_key == "test-api-key"
        assert embedding_service.embedding_model_name == "text-embedding-3-small"
        assert embedding_service.dimension == 1024


class TestEmbeddingServiceContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_entry(self, embedding_service):
        async with embedding_service as service:
            assert service.client is not None
            assert hasattr(service.client, 'embeddings')


class TestCreateEmbedding:
    @pytest.mark.asyncio
    async def test_create_embedding_single_text(self, embedding_service):
        mock_response = MagicMock()
        mock_embedding_item = MagicMock()
        mock_embedding_item.embedding = [0.1, 0.2, 0.3, 0.4]
        mock_response.data = [mock_embedding_item]

        async with embedding_service:
            with patch.object(
                embedding_service.client.embeddings,
                'create',
                new_callable=AsyncMock,
                return_value=mock_response
            ):
                result = await embedding_service.create_embedding(["Hello world"])

                assert len(result) == 1
                assert result[0] == [0.1, 0.2, 0.3, 0.4]

                embedding_service.client.embeddings.create.assert_called_once_with(
                    input=["Hello world"],
                    model="text-embedding-3-small",
                    dimensions=1024
                )

    @pytest.mark.asyncio
    async def test_create_embedding_multiple_texts(self, embedding_service):
        mock_response = MagicMock()
        mock_embedding_1 = MagicMock()
        mock_embedding_1.embedding = [0.1, 0.2, 0.3]
        mock_embedding_2 = MagicMock()
        mock_embedding_2.embedding = [0.4, 0.5, 0.6]
        mock_embedding_3 = MagicMock()
        mock_embedding_3.embedding = [0.7, 0.8, 0.9]
        mock_response.data = [mock_embedding_1, mock_embedding_2, mock_embedding_3]

        async with embedding_service:
            with patch.object(
                embedding_service.client.embeddings,
                'create',
                new_callable=AsyncMock,
                return_value=mock_response
            ):
                texts = ["First text", "Second text", "Third text"]
                result = await embedding_service.create_embedding(texts)

                assert len(result) == 3
                assert result[0] == [0.1, 0.2, 0.3]
                assert result[1] == [0.4, 0.5, 0.6]
                assert result[2] == [0.7, 0.8, 0.9]

                embedding_service.client.embeddings.create.assert_called_once_with(
                    input=texts,
                    model="text-embedding-3-small",
                    dimensions=1024
                )

    @pytest.mark.asyncio
    async def test_create_embedding_empty_list(self, embedding_service):
        mock_response = MagicMock()
        mock_response.data = []

        async with embedding_service:
            with patch.object(
                embedding_service.client.embeddings,
                'create',
                new_callable=AsyncMock,
                return_value=mock_response
            ):
                result = await embedding_service.create_embedding([])

                assert len(result) == 0
                assert result == []


class TestInjectBaseIntoCorpus:
    def test_inject_base_into_corpus_default_alpha(self, embedding_service):
        base_embedding = [1.0, 2.0, 3.0, 4.0]
        corpus_embeddings = [
            [0.5, 0.5, 0.5, 0.5],
            [1.0, 1.0, 1.0, 1.0]
        ]

        result = embedding_service.inject_base_into_corpus(
            base_embedding,
            corpus_embeddings,
            alpha=0.1
        )

        assert len(result) == 2

        # For first corpus: 0.1 * [1.0, 2.0, 3.0, 4.0] + 0.9 * [0.5, 0.5, 0.5, 0.5]
        expected_1 = [
            0.1 * 1.0 + 0.9 * 0.5,  # 0.55
            0.1 * 2.0 + 0.9 * 0.5,  # 0.65
            0.1 * 3.0 + 0.9 * 0.5,  # 0.75
            0.1 * 4.0 + 0.9 * 0.5   # 0.85
        ]
        assert result[0] == pytest.approx(expected_1)

        # For second corpus: 0.1 * [1.0, 2.0, 3.0, 4.0] + 0.9 * [1.0, 1.0, 1.0, 1.0]
        expected_2 = [
            0.1 * 1.0 + 0.9 * 1.0,  # 1.0
            0.1 * 2.0 + 0.9 * 1.0,  # 1.1
            0.1 * 3.0 + 0.9 * 1.0,  # 1.2
            0.1 * 4.0 + 0.9 * 1.0   # 1.3
        ]
        assert result[1] == pytest.approx(expected_2)

    def test_inject_base_into_corpus_custom_alpha(self, embedding_service):
        base_embedding = [2.0, 4.0]
        corpus_embeddings = [[1.0, 2.0]]

        result = embedding_service.inject_base_into_corpus(
            base_embedding,
            corpus_embeddings,
            alpha=0.3
        )

        # 0.3 * [2.0, 4.0] + 0.7 * [1.0, 2.0]
        expected = [
            0.3 * 2.0 + 0.7 * 1.0,  # 1.3
            0.3 * 4.0 + 0.7 * 2.0   # 2.6
        ]
        assert result[0] == pytest.approx(expected)

    def test_inject_base_into_corpus_alpha_zero(self, embedding_service):
        base_embedding = [5.0, 10.0]
        corpus_embeddings = [[1.0, 2.0]]

        result = embedding_service.inject_base_into_corpus(
            base_embedding,
            corpus_embeddings,
            alpha=0.0
        )

        # 0.0 * base + 1.0 * corpus = corpus unchanged
        assert result[0] == [1.0, 2.0]

    def test_inject_base_into_corpus_alpha_one(self, embedding_service):
        base_embedding = [5.0, 10.0]
        corpus_embeddings = [[1.0, 2.0]]

        result = embedding_service.inject_base_into_corpus(
            base_embedding,
            corpus_embeddings,
            alpha=1.0
        )

        # 1.0 * base + 0.0 * corpus = base only
        assert result[0] == [5.0, 10.0]

    def test_inject_base_into_corpus_empty_corpus(self, embedding_service):
        base_embedding = [1.0, 2.0, 3.0]
        corpus_embeddings = []

        result = embedding_service.inject_base_into_corpus(
            base_embedding,
            corpus_embeddings,
            alpha=0.1
        )

        assert result == []

    def test_inject_base_into_corpus_multiple_vectors(self, embedding_service):
        base_embedding = [1.0, 1.0, 1.0]
        corpus_embeddings = [
            [0.0, 0.0, 0.0],
            [1.0, 1.0, 1.0],
            [2.0, 2.0, 2.0]
        ]

        result = embedding_service.inject_base_into_corpus(
            base_embedding,
            corpus_embeddings,
            alpha=0.5
        )

        assert len(result) == 3
        assert result[0] == pytest.approx([0.5, 0.5, 0.5])
        assert result[1] == pytest.approx([1.0, 1.0, 1.0])
        assert result[2] == pytest.approx([1.5, 1.5, 1.5])
