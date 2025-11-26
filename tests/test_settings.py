import pytest
from src.omnimcp.settings import ApiKeysSettings


class TestApiKeysSettings:
    def test_required_fields(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("QDRANT_DATA_PATH", raising=False)
        monkeypatch.delenv("TOOL_OFFLOADED_DATA_PATH", raising=False)
        monkeypatch.delenv("CONFIG_PATH", raising=False)

        with pytest.raises(Exception):
            ApiKeysSettings()

    def test_minimal_config(self, monkeypatch):
        monkeypatch.setenv("CONFIG_PATH", "/tmp/config.json")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("QDRANT_DATA_PATH", "/tmp/qdrant_data")
        monkeypatch.setenv("TOOL_OFFLOADED_DATA_PATH", "/tmp/tool_offloaded_data")

        settings = ApiKeysSettings()
        assert settings.CONFIG_PATH == "/tmp/config.json"
        assert settings.OPENAI_API_KEY == "sk-test-key"
        assert settings.QDRANT_DATA_PATH == "/tmp/qdrant_data"
        assert settings.TOOL_OFFLOADED_DATA_PATH == "/tmp/tool_offloaded_data"

    def test_default_values(self, monkeypatch):
        monkeypatch.setenv("CONFIG_PATH", "/tmp/config.json")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("QDRANT_DATA_PATH", "/tmp/qdrant_data")
        monkeypatch.setenv("TOOL_OFFLOADED_DATA_PATH", "/tmp/tool_offloaded_data")

        settings = ApiKeysSettings()
        # Server defaults
        assert settings.TRANSPORT == "http"
        assert settings.HOST == "localhost"
        assert settings.PORT == 8000
        # Model defaults
        assert settings.DESCRIPTOR_MODEL_NAME == "gpt-4.1-mini"
        assert settings.EMBEDDING_MODEL_NAME == "text-embedding-3-small"
        assert settings.DIMENSIONS == 1024
        assert settings.INDEX_NAME == "omnimcp_idx"
        assert settings.MAX_RESULT_TOKENS == 5000
        assert settings.DESCRIBE_IMAGES is True
        assert settings.VISION_MODEL_NAME == "gpt-4.1-mini"
        assert settings.MCP_SERVER_INDEX_RATE_LIMIT == 3
        assert settings.MCP_SERVER_TOOL_INDEX_RATE_LIMIT == 32
        assert settings.BACKGROUND_MCP_TOOL_QUEUE_MAX_SUBSCRIBERS == 8
        assert settings.BACKGROUND_MCP_TOOL_QUEUE_SIZE == 64

    def test_custom_values(self, monkeypatch):
        monkeypatch.setenv("CONFIG_PATH", "/custom/config.json")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-custom-key")
        monkeypatch.setenv("QDRANT_DATA_PATH", "/custom/qdrant_data")
        monkeypatch.setenv("TOOL_OFFLOADED_DATA_PATH", "/custom/tool_offloaded_data")
        monkeypatch.setenv("TRANSPORT", "stdio")
        monkeypatch.setenv("HOST", "0.0.0.0")
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("DESCRIPTOR_MODEL_NAME", "gpt-4o")
        monkeypatch.setenv("EMBEDDING_MODEL_NAME", "text-embedding-3-large")
        monkeypatch.setenv("DIMENSIONS", "3072")
        monkeypatch.setenv("INDEX_NAME", "custom_idx")
        monkeypatch.setenv("MAX_RESULT_TOKENS", "4000")
        monkeypatch.setenv("DESCRIBE_IMAGES", "false")

        settings = ApiKeysSettings()
        assert settings.CONFIG_PATH == "/custom/config.json"
        assert settings.OPENAI_API_KEY == "sk-custom-key"
        assert settings.QDRANT_DATA_PATH == "/custom/qdrant_data"
        assert settings.TOOL_OFFLOADED_DATA_PATH == "/custom/tool_offloaded_data"
        assert settings.TRANSPORT == "stdio"
        assert settings.HOST == "0.0.0.0"
        assert settings.PORT == 9000
        assert settings.DESCRIPTOR_MODEL_NAME == "gpt-4o"
        assert settings.EMBEDDING_MODEL_NAME == "text-embedding-3-large"
        assert settings.DIMENSIONS == 3072
        assert settings.INDEX_NAME == "custom_idx"
        assert settings.MAX_RESULT_TOKENS == 4000
        assert settings.DESCRIBE_IMAGES is False
