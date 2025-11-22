import json
import asyncio
from typing import Self, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import StdioServerParameters, ClientSession, stdio_client
from mcp.types import ListToolsResult, Tool

from .settings import ApiKeysSettings
from .services.embedding import EmbeddingService
from .services.descriptor import DescriptorService
from .services.index import IndexService
from .types import McpConfig, McpStartupConfig, McpServerDescription, DescribeMcpServerResponse

from .log import logger

class MCPEngine:
    def __init__(self, api_keys_settings:ApiKeysSettings):
        self.api_keys_settings = api_keys_settings
        self.hmap_mcp_server_to_session: Dict[str, ClientSession] = {}
        self.mcp_config: Optional[McpConfig] = None
    
    async def __aenter__(self) -> Self:
        self.async_exit_stack = AsyncExitStack()
        self.thread_pool = ThreadPoolExecutor(max_workers=self.api_keys_settings.THREAD_POOL_MAX_WORKERS)
        self.index_service = await self.async_exit_stack.enter_async_context(
            IndexService(
                index_name=self.api_keys_settings.INDEX_NAME,
                dimensions=self.api_keys_settings.DIMENSIONS,
                qdrant_storage_path=self.api_keys_settings.QDRANT_STORAGE_PATH
            )
        )
        self.embedding_service = await self.async_exit_stack.enter_async_context(
            EmbeddingService(
                api_key=self.api_keys_settings.OPENAI_API_KEY,
                embedding_model_name=self.api_keys_settings.EMBEDDING_MODEL_NAME,
                dimension=self.api_keys_settings.DIMENSIONS
            )
        )
        self.descriptor_service = await self.async_exit_stack.enter_async_context(
            DescriptorService(
                openai_api_key=self.api_keys_settings.OPENAI_API_KEY,
                openai_model_name=self.api_keys_settings.DESCRIPTOR_MODEL_NAME
            )
        )
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            logger.error(f"Exception in APIEngine context manager: {exc_value}")
            logger.exception(traceback)
        await self.async_exit_stack.aclose()
        self.thread_pool.shutdown(wait=True)

    def load_mcp_config(self, mcp_config_filepath: str) -> McpConfig:
        try:
            config_path = Path(mcp_config_filepath)
            if not config_path.exists():
                raise FileNotFoundError(f"MCP config file not found: {mcp_config_filepath}")

            with open(config_path, 'r') as f:
                config_data = json.load(f)

            return McpConfig(**config_data)
        except Exception as e:
            logger.error(f"Error loading MCP config from {mcp_config_filepath}: {e}")
            raise

    async def index_mcp_servers(self, mcp_config: McpConfig) -> None:
        logger.info(f"Starting indexing of {len(mcp_config.mcpServers)} MCP servers")
        tasks = []
        for server_name, startup_config in mcp_config.mcpServers.items():
            task = asyncio.create_task(
                self._index_single_server(server_name, startup_config)
            )
            tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = sum(1 for r in results if not isinstance(r, Exception))
        failures = sum(1 for r in results if isinstance(r, Exception))

        logger.info(f"Indexing completed: {successes} successful, {failures} failed")

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                server_name = list(mcp_config.mcpServers.keys())[i]
                logger.error(f"Failed to index server '{server_name}': {result}")

    async def _index_single_server(self, server_name: str, startup_config: McpStartupConfig) -> None:
        try:
            existing_server = await self.index_service.get_server(server_name)
            if existing_server is not None:
                logger.info(f"Server '{server_name}' already indexed, skipping")
                return

            logger.info(f"Describing MCP server: {server_name}")

            server_response:DescribeMcpServerResponse = await self.descriptor_service.describe_mcp_server(
                server_name=server_name,
                mcp_startup_config=startup_config,
                timeout=self.api_keys_settings.MCP_SERVER_STARTUP_TIMEOUT
            )

            if server_response is None:
                logger.warning(f"Failed to describe server '{server_name}' - skipping indexing")
                return

            description_text = (
                f"{server_response.server_description.title}\n"
                f"{server_response.server_description.summary}\n"
                f"Capabilities: {', '.join(server_response.server_description.capabilities)}\n"
                f"Limitations: {', '.join(server_response.server_description.limitations)}"
            )

            server_embedding = await self.embedding_service.create_embedding([description_text])

            await self._index_server_tools(server_response, server_embedding[0])

            nb_tools = len(server_response.tools.tools)
            await self.index_service.add_server(
                server_name=server_name,
                mcp_server_description=server_response.server_description,
                embedding=server_embedding[0],
                nb_tools=nb_tools
            )

            logger.info(f"Indexed server: {server_name}")
        except Exception as e:
            logger.error(f"Error indexing server '{server_name}': {e}")
            raise

    async def _index_server_tools(self, server_response:DescribeMcpServerResponse, server_embedding: list[float]) -> None:
        server_name = server_response.server_name
        tools = server_response.tools.tools

        logger.info(f"Indexing {len(tools)} tools from server '{server_name}'")

        tasks = []
        for tool in tools:
            task = asyncio.create_task(
                self._index_single_tool(server_name, tool, server_embedding)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = sum(1 for r in results if not isinstance(r, Exception))
        failures = sum(1 for r in results if isinstance(r, Exception))

        logger.info(f"Tool indexing completed for '{server_name}': {successes} successful, {failures} failed")

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tool_name = tools[i].name
                logger.error(f"Failed to index tool '{tool_name}' from server '{server_name}': {result}")

    async def _index_single_tool(self, server_name: str, tool:Tool, server_embedding: list[float]) -> None:
        try:
            enhanced_description = await self.descriptor_service.enhance_tool(
                server_name=server_name,
                tool_name=tool.name,
                tool_description=tool.description or "",
                tool_schema=tool.inputSchema
            )

            if enhanced_description:
                tool_embedding = await self.embedding_service.create_embedding([enhanced_description])

                weighted_embedding = await self.embedding_service.weighted_embedding(
                    base_embedding=server_embedding,
                    corpus_embedding=tool_embedding[0],
                    alpha=0.1
                )

                await self.index_service.add_tool(
                    server_name=server_name,
                    tool_name=tool.name,
                    tool_description=enhanced_description,
                    tool_schema=str(tool.inputSchema),
                    embedding=weighted_embedding
                )

                logger.debug(f"Indexed tool: {tool.name} from server '{server_name}'")
            else:
                logger.warning(f"Failed to enhance description for tool '{tool.name}' from server '{server_name}'")

        except Exception as e:
            logger.error(f"Error indexing tool '{tool.name}' from server '{server_name}': {e}")
            raise

    async def start_mcp_server(self, server_name: str) -> bool:
        if server_name in self.hmap_mcp_server_to_session:
            logger.info(f"Server '{server_name}' already running")
            return True

        if not self.mcp_config or server_name not in self.mcp_config.mcpServers:
            logger.error(f"Server '{server_name}' not found in config")
            return False

        startup_config = self.mcp_config.mcpServers[server_name]
        timeout = self.api_keys_settings.MCP_SERVER_STARTUP_TIMEOUT

        try:
            server_params = StdioServerParameters(
                command=startup_config.command,
                args=startup_config.args,
                env=startup_config.env
            )

            async with asyncio.timeout(delay=timeout):
                stdio_transport = await self.async_exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
                reader, writer = stdio_transport
                session = await self.async_exit_stack.enter_async_context(
                    ClientSession(reader, writer)
                )
                await session.initialize()

            self.hmap_mcp_server_to_session[server_name] = session
            logger.info(f"Successfully started MCP server: {server_name}")
            return True

        except asyncio.TimeoutError:
            logger.error(f"Timeout ({timeout}s) starting server '{server_name}'")
            return False
        except Exception as e:
            logger.error(f"Failed to start server '{server_name}': {e}")
            return False

    async def shutdown_mcp_server(self, server_name: str) -> bool:
        session = self.hmap_mcp_server_to_session.get(server_name)
        if not session:
            logger.warning(f"Server '{server_name}' not running")
            return True

        try:
            del self.hmap_mcp_server_to_session[server_name]
            logger.info(f"Successfully shutdown MCP server: {server_name}")
            return True
        except Exception as e:
            logger.error(f"Error shutting down server '{server_name}': {e}")
            return False

    async def execute_tool(self, server_name: str, tool_name: str, arguments: dict) -> dict:
        session = self.hmap_mcp_server_to_session.get(server_name)
        if not session:
            return {"error": f"Server '{server_name}' not running"}

        try:
            result = await session.call_tool(name=tool_name, arguments=arguments)
            clean_contents = []
            for content in result.content:
                content_dict = content.model_dump()
                content_dict.pop("annotations", None)
                content_dict.pop("meta", None)
                clean_contents.append(content_dict)

            return {
                "success": True,
                "server_name": server_name,
                "tool_name": tool_name,
                "results": clean_contents
            }

        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}' on server '{server_name}': {e}")
            return {
                "success": False,
                "server_name": server_name,
                "tool_name": tool_name,
                "error": str(e)
            }

    def list_running_servers(self) -> list:
        return list(self.hmap_mcp_server_to_session.keys())
        