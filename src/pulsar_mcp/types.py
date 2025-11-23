from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from mcp.types import ListToolsResult

class McpStartupConfig(BaseModel):
    command:str
    args: list[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    timeout:float=30.0
    include_tools:Optional[List[str]] = None
    exclude_tools:Optional[List[str]] = None
    force_reindex:bool = False

class McpConfig(BaseModel):
    mcpServers: Dict[str, McpStartupConfig]

class McpServerDescription(BaseModel):
    title: str
    summary: str
    capabilities: List[str]
    limitations: List[str]

class McpServerFullDescription(BaseModel):
    server_name: str
    server_description: McpServerDescription
    tools:ListToolsResult
    