import json 
import asyncio 
from pathlib import Path

from contextlib import AsyncExitStack

from mcp import StdioServerParameters, ClientSession, stdio_client
from mcp.types import ListToolsResult

from .types import McpServersConfig, McpStartupConfig
from .log import logger 

def estimate_tokens(text: str) -> int:
      return len(text) // 4

def load_mcp_config(mcp_config_filepath: str) -> McpServersConfig:
    try:
        config_path = Path(mcp_config_filepath)
        if not config_path.exists():
            raise FileNotFoundError(f"MCP config file not found: {mcp_config_filepath}")

        with open(config_path, 'r') as f:
            config_data = json.load(f)
        return McpServersConfig(**config_data)
    except Exception as e:
        logger.error(f"Error loading MCP config from {mcp_config_filepath}: {e}")
        raise e 

async def retrieve_mcp_server_tool(server_name:str, mcp_startup_config:McpStartupConfig) -> ListToolsResult:
    server_parameters = StdioServerParameters(
        command=mcp_startup_config.command,
        args=mcp_startup_config.args,
        env=mcp_startup_config.env
    )
    resources_manager = AsyncExitStack() 
    try:
        transport = await resources_manager.enter_async_context(stdio_client(server=server_parameters))
        read, write = transport 
        session = await resources_manager.enter_async_context(ClientSession(read, write))
        try:
            async with asyncio.timeout(delay=mcp_startup_config.timeout):        
                await session.initialize()
        except TimeoutError:
            logger.error(f"Timeout while initializing MCP server {server_name}")
            raise
        logger.info("Initialized MCP session")
        tools_result = await session.list_tools()
        logger.info(f"Retrieved {len(tools_result.tools)} tools from MCP server {server_name}")
        return tools_result
    finally:
        try:
            await resources_manager.aclose()
        except Exception as e:
            raise Exception(f"Error closing resources for MCP server {server_name}: {e}")