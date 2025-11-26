import pytest
from src.omnimcp.settings import ApiKeysSettings


class TestApiKeysSettings:
    def test_required_fields(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("QDRANT_STORAGE_PATH", raising=False)
        monkeypatch.delenv("CONTENT_STORAGE_PATH", raising=False)

        with pytest.raises(Exception):
            ApiKeysSettings()

    def test_minimal_config(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("QDRANT_STORAGE_PATH", "/tmp/qdrant")
        monkeypatch.setenv("CONTENT_STORAGE_PATH", "/tmp/content")

        settings = ApiKeysSettings()
        assert settings.OPENAI_API_KEY == "sk-test-key"
        assert settings.QDRANT_STORAGE_PATH == "/tmp/qdrant"
        assert settings.CONTENT_STORAGE_PATH == "/tmp/content"

    def test_default_values(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("QDRANT_STORAGE_PATH", "/tmp/qdrant")
        monkeypatch.setenv("CONTENT_STORAGE_PATH", "/tmp/content")

        settings = ApiKeysSettings()
        assert settings.DESCRIPTOR_MODEL_NAME == "gpt-4.1-mini"
        assert settings.EMBEDDING_MODEL_NAME == "text-embedding-3-small"
        assert settings.DIMENSIONS == 1024
        assert settings.INDEX_NAME == "pulsar_idx"
        assert settings.MAX_RESULT_TOKENS == 5000
        assert settings.DESCRIBE_IMAGES is True
        assert settings.VISION_MODEL_NAME == "gpt-4.1-mini"
        assert settings.MCP_SERVER_INDEX_RATE_LIMIT == 3
        assert settings.MCP_SERVER_TOOL_INDEX_RATE_LIMIT == 32
        assert settings.BACKGROUND_MCP_TOOL_QUEUE_MAX_SUBSCRIBERS == 8
        assert settings.BACKGROUND_MCP_TOOL_QUEUE_SIZE == 64

    def test_custom_values(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-custom-key")
        monkeypatch.setenv("QDRANT_STORAGE_PATH", "/custom/qdrant")
        monkeypatch.setenv("CONTENT_STORAGE_PATH", "/custom/content")
        monkeypatch.setenv("DESCRIPTOR_MODEL_NAME", "gpt-4o")
        monkeypatch.setenv("EMBEDDING_MODEL_NAME", "text-embedding-3-large")
        monkeypatch.setenv("DIMENSIONS", "3072")
        monkeypatch.setenv("INDEX_NAME", "custom_idx")
        monkeypatch.setenv("MAX_RESULT_TOKENS", "4000")
        monkeypatch.setenv("DESCRIBE_IMAGES", "false")

        settings = ApiKeysSettings()
        assert settings.OPENAI_API_KEY == "sk-custom-key"
        assert settings.DESCRIPTOR_MODEL_NAME == "gpt-4o"
        assert settings.EMBEDDING_MODEL_NAME == "text-embedding-3-large"
        assert settings.DIMENSIONS == 3072
        assert settings.INDEX_NAME == "custom_idx"
        assert settings.MAX_RESULT_TOKENS == 4000
        assert settings.DESCRIBE_IMAGES is False
