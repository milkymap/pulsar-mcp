from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class McpStartupConfig(BaseModel):
    command:str
    args: list[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    timeout:float=30.0
    include_tools:Optional[List[str]] = None
    exclude_tools:Optional[List[str]] = None
    reindex:bool = False

class McpServersConfig(BaseModel):
    mcpServers: Dict[str, McpStartupConfig]

class McpServerDescription(BaseModel):
    title: str = Field(description="A short, descriptive technical title for the MCP server")
    summary: str = Field(description="A brief summary of the MCP server's purpose and functionality")
    capabilities: List[str] = Field(description="A list of key capabilities and features of the MCP server")
    limitations: List[str] = Field(description="A list of known limitations or constraints of the MCP server")

class McpServerToolDescription(BaseModel):
    title: str = Field(description="A short, descriptive technical title for the tool")
    summary: str = Field(description="A brief summary of the tool's purpose and functionality")
    uttirances: List[str] = Field(description="Example utterances or commands that can be used to invoke the tool")

    