from pydantic_settings import BaseSettings
from pydantic import Field


class ApiKeysSettings(BaseSettings):
    # CLI / Server settings
    CONFIG_PATH: str = Field(validation_alias="CONFIG_PATH")
    TRANSPORT: str = Field("http", validation_alias="TRANSPORT")
    HOST: str = Field("localhost", validation_alias="HOST")
    PORT: int = Field(8000, validation_alias="PORT")

    # API Keys
    OPENAI_API_KEY: str = Field(validation_alias="OPENAI_API_KEY")

    # Model settings
    DESCRIPTOR_MODEL_NAME: str = Field("gpt-4.1-mini", validation_alias="DESCRIPTOR_MODEL_NAME")
    EMBEDDING_MODEL_NAME: str = Field("text-embedding-3-small", validation_alias="EMBEDDING_MODEL_NAME")
    VISION_MODEL_NAME: str = Field("gpt-4.1-mini", validation_alias="VISION_MODEL_NAME")
    DIMENSIONS: int = Field(1024, validation_alias="DIMENSIONS")

    # Storage settings
    INDEX_NAME: str = Field("omnimcp_idx", validation_alias="INDEX_NAME")
    QDRANT_DATA_PATH: str = Field(validation_alias="QDRANT_DATA_PATH")
    TOOL_OFFLOADED_DATA_PATH: str = Field(validation_alias="TOOL_OFFLOADED_DATA_PATH")

    # Rate limiting
    MCP_SERVER_INDEX_RATE_LIMIT: int = Field(3, validation_alias="MCP_SERVER_INDEX_RATE_LIMIT")
    MCP_SERVER_TOOL_INDEX_RATE_LIMIT: int = Field(32, validation_alias="MCP_SERVER_TOOL_INDEX_RATE_LIMIT")

    # Background queue settings
    BACKGROUND_MCP_TOOL_QUEUE_MAX_SUBSCRIBERS: int = Field(8, validation_alias="BACKGROUND_MCP_TOOL_QUEUE_MAX_SUBSCRIBERS")
    BACKGROUND_MCP_TOOL_QUEUE_SIZE: int = Field(64, validation_alias="BACKGROUND_MCP_TOOL_QUEUE_SIZE")

    # Other settings
    MCP_SERVER_EMBEDDING_WEIGHTS: float = Field(0.1, validation_alias="MCP_SERVER_EMBEDDING_WEIGHTS")
    MCP_SERVER_POLLING_INTERVAL_MS: int = Field(5000, validation_alias="MCP_SERVER_POLLING_INTERVAL_MS")
    MAX_RESULT_TOKENS: int = Field(5000, validation_alias="MAX_RESULT_TOKENS")
    DESCRIBE_IMAGES: bool = Field(True, validation_alias="DESCRIBE_IMAGES")
    
