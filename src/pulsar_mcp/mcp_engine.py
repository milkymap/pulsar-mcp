import json
import asyncio

import zmq 
import zmq.asyncio as azmq 

from hashlib import sha256

from typing import Self, Dict, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import StdioServerParameters, ClientSession, stdio_client
from mcp.types import ListToolsResult, Tool, CallToolResult

from .settings import ApiKeysSettings
from .services.embedding import EmbeddingService
from .services.descriptor import DescriptorService
from .services.index import IndexService
from .types import McpConfig, McpStartupConfig, McpServerDescription, DescribeMcpServerResponse

from .log import logger

class MCPEngine:
    def __init__(self, api_keys_settings:ApiKeysSettings):
        self.api_keys_settings = api_keys_settings
        self.mcp_config: Optional[McpConfig] = None
        self.hmap_background_mcp_server_tasks:Dict[str, asyncio.Task] = {}
        self.hmap_background_mcp_server_status:Dict[str, int] = {}
    
    async def __aenter__(self) -> Self:
        self.ctx = azmq.Context()
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
        for server_name, mcp_tasks in self.hmap_background_mcp_server_tasks.items():
            logger.info(f"Cancelling background MCP server task for: {server_name}")
            mcp_tasks.cancel()
        await asyncio.gather(*self.hmap_background_mcp_server_tasks, return_exceptions=True)
        self.ctx.term()
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

            await self._index_server_tools(server_response, server_embedding[0])  # Index tools
            # if one tool fails, we want to fail the whole server indexing

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
        if any([ isinstance(res, Exception) for res in results  ]):
            raise Exception(f"One or more tools failed to index for server '{server_name}'") 

    async def _index_single_tool(self, server_name: str, tool:Tool, server_embedding: list[float]) -> None:
        try:
            enhanced_description = await self.descriptor_service.enhance_tool(
                server_name=server_name,
                tool_name=tool.name,
                tool_description=tool.description or "",
                tool_schema=tool.inputSchema
            )

            tool_embedding = await self.embedding_service.create_embedding([enhanced_description])

            weighted_embedding = self.embedding_service.weighted_embedding(
                base_embedding=server_embedding,
                corpus_embeddings=tool_embedding[0],
                alpha=0.1
            )

            await self.index_service.add_tool(
                server_name=server_name,
                tool_name=tool.name,
                tool_description=enhanced_description,
                tool_schema=tool.inputSchema,
                embedding=weighted_embedding
            )

            logger.debug(f"Indexed tool: {tool.name} from server '{server_name}'")
   
        except Exception as e:
            logger.error(f"Error indexing tool '{tool.name}' from server '{server_name}': {e}")
            raise
    
    async def background_mcp_server(self, server_name:str, mcp_startup_config:McpStartupConfig, timeout:int=50) -> Optional[DescribeMcpServerResponse]:
        server_parameters = StdioServerParameters(
            command=mcp_startup_config.command,
            args=mcp_startup_config.args,
            env=mcp_startup_config.env
        )
        async with stdio_client(server=server_parameters) as transport:
            read, write = transport 
            async with ClientSession(read, write) as session:
                try:
                    async with asyncio.timeout(delay=timeout):
                        await session.initialize()
                except asyncio.TimeoutError:
                    logger.error("Timeout while trying to initialize MCP session.") 
                    self.hmap_background_mcp_server_status[server_name] = 1  # timeout
                    return
                except Exception as e:
                    logger.error(f"Error initializing MCP session: {e}")
                    self.hmap_background_mcp_server_status[server_name] = 2  # error
                    
                logger.info("Initialized MCP session")
                tools_result = await session.list_tools()
                logger.info(f"Retrieved {len(tools_result.tools)} tools from MCP server")
                self.hmap_background_mcp_server_status[server_name] = 3 # running

                server_hash = sha256(server_name.encode('utf-8')).hexdigest()
                router_socket:azmq.Socket = self.ctx.socket(zmq.ROUTER)
                router_socket.bind(f"inproc://{server_hash}")

                poller = azmq.Poller()
                poller.register(router_socket, zmq.POLLIN)

                keep_loop = True
                while keep_loop:
                    try:
                        if not keep_loop:
                            logger.info("Shutting down background MCP server loop")
                            break

                        hmap_socket_flag = dict(await poller.poll(timeout=5000))
                        if not hmap_socket_flag:
                            continue
                        
                        if not keep_loop:
                            logger.info("Shutting down background MCP server loop")
                            break

                        if not router_socket in hmap_socket_flag:
                            continue

                        if hmap_socket_flag[router_socket] != zmq.POLLIN:
                            continue

                        caller_id, _, encoded_tool_name, encdoded_tool_arguments = await router_socket.recv_multipart()
                        try:
                            tool_name = encoded_tool_name.decode('utf-8')
                            tool_arguments = json.loads(encdoded_tool_arguments.decode('utf-8'))
                            
                            result = await session.call_tool(name=tool_name, arguments=tool_arguments)
                            content = []
                            for content_block in result.content:
                                content_block_dict = content_block.model_dump()
                                content_block_dict.pop("annotations", None)
                                content_block_dict.pop("meta", None)
                                content.append(content_block_dict)
                            
                            response_payload = json.dumps({"status": True, "content": content}).encode('utf-8')
                        except Exception as e:
                            logger.error(f"Error executing tool '{tool_name}': {e}")
                            response_payload = json.dumps({"status": False, "error_message": str(e)}).encode('utf-8')
                        
                        await router_socket.send_multipart([caller_id, b"", response_payload])
                    except asyncio.CancelledError:
                        logger.info("Background MCP server task cancelled")
                        keep_loop = False
                    except Exception as e:
                        logger.error(f"Error in background MCP server loop: {e}")
                        break 
                    
                router_socket.close(linger=0)
        
    async def start_mcp_server(self, server_name: str) -> Tuple[bool, Optional[str]]:
        if server_name in self.hmap_background_mcp_server_tasks:
            return True, f"Server '{server_name}' already running"
        
        if not self.mcp_config or server_name not in self.mcp_config.mcpServers:
            return False, f"Server '{server_name}' not found in config"

        startup_config = self.mcp_config.mcpServers[server_name]
        timeout = self.api_keys_settings.MCP_SERVER_STARTUP_TIMEOUT

        try:
            task = asyncio.create_task(
                self.background_mcp_server(
                    server_name=server_name,
                    mcp_startup_config=startup_config,
                    timeout=timeout
                )
            )
            task.set_name(f"background_task_{server_name}")
            self.hmap_background_mcp_server_tasks[server_name] = task
            self.hmap_background_mcp_server_status[server_name] = 0  # pending
            task.add_done_callback(
                lambda t: self.hmap_background_mcp_server_tasks.pop(t.get_name().split("_")[-1])
            )

            while self.hmap_background_mcp_server_status[server_name] == 0:
                await asyncio.sleep(1)
                logger.info(f"Waiting for MCP server {server_name} to start...")
            
            match self.hmap_background_mcp_server_status[server_name]:
                case 1:
                    return False, f"Timeout starting server '{server_name}'"
                case 2:
                    return False, f"Error starting server '{server_name}'"
                case 3:
                    return True, f"Successfully started server '{server_name}'"
        except Exception as e:
            logger.error(f"Failed to start server '{server_name}': {e}")
            return False, str(e)

    async def shutdown_mcp_server(self, server_name: str) -> Tuple[bool, Optional[str]]:
        task = self.hmap_background_mcp_server_tasks.get(server_name)
        if not task:
            logger.info(f"Server '{server_name}' not running")
            return True, f"Server '{server_name}' not running"
        
        try:
            task.cancel()
            await task
            logger.info(f"Successfully shutdown MCP server: {server_name}")
            del self.hmap_background_mcp_server_status[server_name]
            # server name must be removed from the map in the done callback
            return True, f"Successfully shutdown server '{server_name}'"
        except Exception as e:
            logger.error(f"Error shutting down server '{server_name}': {e}")
            return False, str(e)

    async def execute_tool(self, server_name: str, tool_name: str, arguments: Optional[dict]=None, timeout:float=60) -> CallToolResult:
        if not server_name in self.hmap_background_mcp_server_tasks:
            raise Exception(f"Server '{server_name}' not running")
        
        if self.hmap_background_mcp_server_status.get(server_name) != 3:
            raise Exception(f"Server '{server_name}' not in running state")
        
        server_hash = sha256(server_name.encode('utf-8')).hexdigest()
        socket = self.ctx.socket(zmq.DEALER)
        socket.connect(f"inproc://{server_hash}")
        await socket.send_multipart([b"", tool_name.encode('utf-8'), json.dumps(arguments or {}).encode('utf-8')])
        try:
            async with asyncio.timeout(delay=timeout):
                _, encoded_response = await socket.recv_multipart()
                response:Dict = json.loads(encoded_response.decode('utf-8'))
                if response["status"]:
                    return response["content"]
                error_message = response.get("error_message", "Unknown error")
                raise Exception(f"Error executing tool '{tool_name}' on server '{server_name}': {error_message}")
        except asyncio.TimeoutError:
            raise Exception(f"Timeout waiting for tool '{tool_name}' response from server '{server_name}'")
    
    def list_running_servers(self) -> list:
        return list(self.hmap_background_mcp_server_tasks.keys())
        