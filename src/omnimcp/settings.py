from pydantic_settings import BaseSettings
from pydantic import Field


class ApiKeysSettings(BaseSettings):
    OPENAI_API_KEY: str = Field(validation_alias="OPENAI_API_KEY")
    DESCRIPTOR_MODEL_NAME:str = Field("gpt-4.1-mini", validation_alias="DESCRIPTOR_MODEL_NAME")
    EMBEDDING_MODEL_NAME:str = Field("text-embedding-3-small", validation_alias="EMBEDDING_MODEL_NAME")
    DIMENSIONS:int = Field(1024, validation_alias="DIMENSIONS")
    INDEX_NAME: str = Field("pulsar_idx", validation_alias="INDEX_NAME")
    QDRANT_STORAGE_PATH: str = Field(validation_alias="QDRANT_STORAGE_PATH")
    MCP_SERVER_INDEX_RATE_LIMIT:int = Field(3, validation_alias="MCP_SERVER_INDEX_RATE_LIMIT")
    MCP_SERVER_TOOL_INDEX_RATE_LIMIT:int = Field(32, validation_alias="MCP_SERVER_TOOL_INDEX_RATE_LIMIT")
    BACKGROUND_MCP_TOOL_QUEUE_MAX_SUBSCRIBERS:int = Field(8, validation_alias="BACKGROUND_MCP_TOOL_QUEUE_MAX_SUBSCRIBERS")
    BACKGROUND_MCP_TOOL_QUEUE_SIZE:int = Field(64, validation_alias="BACKGROUND_MCP_TOOL_QUEUE_SIZE")
    MCP_SERVER_EMBEDDING_WEIGHTS:float= Field(0.1, validation_alias="MCP_SERVER_EMBEDDING_WEIGHTS")
    MCP_SERVER_POLLING_INTERVAL_MS:int = Field(5000, validation_alias="MCP_SERVER_POLLING_INTERVAL_MS")
    # Content manager settings
    CONTENT_STORAGE_PATH: str = Field(validation_alias="CONTENT_STORAGE_PATH")
    MAX_RESULT_TOKENS: int = Field(5000, validation_alias="MAX_RESULT_TOKENS")
    DESCRIBE_IMAGES: bool = Field(True, validation_alias="DESCRIBE_IMAGES")
    VISION_MODEL_NAME: str = Field("gpt-4.1-mini", validation_alias="VISION_MODEL_NAME")
    
