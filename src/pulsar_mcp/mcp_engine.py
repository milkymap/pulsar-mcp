import json
import asyncio

from uuid import uuid4

import zmq 
import zmq.asyncio as azmq 

from hashlib import sha256

from typing import Self, Dict, Optional, Set, Tuple, List, AsyncGenerator 
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from pathlib import Path


from mcp import StdioServerParameters, ClientSession, stdio_client
from mcp.types import Tool, ContentBlock

from .settings import ApiKeysSettings
from .services.embedding import EmbeddingService
from .services.descriptor import DescriptorService
from .services.index import IndexService
from .types import McpConfig, McpStartupConfig, McpServerFullDescription

from .log import logger

class MCPEngine:
    def __init__(self, api_keys_settings:ApiKeysSettings):
        self.api_keys_settings = api_keys_settings
        
    async def __aenter__(self) -> Self:
        self.mcp_config: Optional[McpConfig] = None
        
        self.mcp_server_tasks:Dict[str, asyncio.Task] = {}
        self.subscriber_tasks:Set[asyncio.Task] = set()
        self.background_tasks:Dict[str, asyncio.Task] = {}

        self.ctx = azmq.Context()
        self.resources_manager = AsyncExitStack()

        self.mcp_server_semaphore = asyncio.Semaphore(self.api_keys_settings.MCP_SERVER_INDEX_RATE_LIMIT)
        self.mcp_server_tool_semaphore = asyncio.Semaphore(self.api_keys_settings.MCP_SERVER_TOOL_INDEX_RATE_LIMIT)
        
        self.priority_queue = asyncio.PriorityQueue(maxsize=self.api_keys_settings.BACKGROUND_MCP_TOOL_QUEUE_SIZE)
    
        index_service = IndexService(index_name=self.api_keys_settings.INDEX_NAME, dimensions=self.api_keys_settings.DIMENSIONS, qdrant_storage_path=self.api_keys_settings.QDRANT_STORAGE_PATH)
        embedding_service = EmbeddingService(api_key=self.api_keys_settings.OPENAI_API_KEY, embedding_model_name=self.api_keys_settings.EMBEDDING_MODEL_NAME, dimension=self.api_keys_settings.DIMENSIONS)
        descriptor_service = DescriptorService(openai_api_key=self.api_keys_settings.OPENAI_API_KEY, openai_model_name=self.api_keys_settings.DESCRIPTOR_MODEL_NAME)

        self.index_service = await self.resources_manager.enter_async_context(index_service)
        self.embedding_service = await self.resources_manager.enter_async_context(embedding_service)
        self.descriptor_service = await self.resources_manager.enter_async_context(descriptor_service)

        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            logger.error(f"Exception in APIEngine context manager: {exc_value}")
            logger.exception(traceback)
        
        cancelled_tasks:List[asyncio.Task] = []
        for server_name, task in self.mcp_server_tasks.items():
            logger.info(f"Cancelling background MCP server task for: {server_name}")
            if not task.done():
                task.cancel()
                cancelled_tasks.append(task)
        await asyncio.gather(*cancelled_tasks, return_exceptions=True)

        cancelled_tasks.clear()
        for task in self.subscriber_tasks:
            logger.info("Cancelling background MCP tool subscriber task")
            if not task.done():
                task.cancel()
                cancelled_tasks.append(task)
        
        await asyncio.gather(*cancelled_tasks, return_exceptions=True)

        cancelled_tasks.clear()
        for task_id, task in self.background_tasks.items():
            logger.info(f"Cancelling background MCP tool task with ID: {task_id}")
            if not task.done():
                task.cancel()
                cancelled_tasks.append(task)
        await asyncio.gather(*cancelled_tasks, return_exceptions=True)

        self.ctx.term()
        await self.resources_manager.aclose()
        
    def load_mcp_config(self, mcp_config_filepath: str) -> McpConfig:
        try:
            config_path = Path(mcp_config_filepath)
            if not config_path.exists():
                raise FileNotFoundError(f"MCP config file not found: {mcp_config_filepath}")

            with open(config_path, 'r') as f:
                config_data = json.load(f)
            self.mcp_config = McpConfig(**config_data)
        except Exception as e:
            logger.error(f"Error loading MCP config from {mcp_config_filepath}: {e}")
            raise e 
    
    @asynccontextmanager
    async def create_socket(self, socket_type:int, socket_method:str, addr:str) -> AsyncGenerator[azmq.Socket, None]:
        if socket_method not in ["bind", "connect"]:
            raise ValueError(f"Invalid socket method: {socket_method}. Must be 'bind' or 'connect'.")
        
        socket = self.ctx.socket(socket_type)
        try:
            match socket_method:
                case "bind":
                    socket.bind(addr)
                case "connect":
                    socket.connect(addr)    
            yield socket
        finally:
            socket.close(linger=0)
            logger.info(f"Closed socket with method {socket_method}")

    async def index_mcp_servers(self) -> None:
        if not hasattr(self, 'mcp_config') or self.mcp_config is None:
            raise Exception("MCP config not loaded. Please load the MCP config before indexing servers.")
        
        logger.info(f"Starting indexing of {len(self.mcp_config.mcpServers)} MCP servers")
        tasks = []
        for server_name, startup_config in self.mcp_config.mcpServers.items():
            task = asyncio.create_task(self.index_single_server(server_name, startup_config))
            tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        server_names = list(self.mcp_config.mcpServers.keys())
        nb_failures = 0
        for i, result in enumerate(results):
            if not isinstance(result, Exception):
                logger.info(f"Successfully indexed server '{server_names[i]}'")
                continue 
            logger.error(f"Failed to index server '{server_names[i]}': {result}")
            nb_failures += 1
        logger.info(f"Completed indexing MCP servers with {nb_failures} failures out of {len(self.mcp_config.mcpServers)} servers")
        if nb_failures == len(self.mcp_config.mcpServers):
            raise Exception("All MCP server indexing attempts failed")

    async def index_single_server(self, server_name: str, startup_config: McpStartupConfig) -> None:
        existing_server = await self.index_service.get_server(server_name)
        if existing_server is not None and not startup_config.force_reindex:
            logger.info(f"Server '{server_name}' already indexed, skipping")
            return
        logger.info(f"Describing MCP server: {server_name}")
        await self.mcp_server_semaphore.acquire()
        try:
            server_response:McpServerFullDescription = await self.descriptor_service.describe_mcp_server(
                server_name=server_name,
                mcp_startup_config=startup_config,
                timeout=startup_config.timeout
            )
            
            description_text = (
                f"{server_response.server_description.title}\n"
                f"{server_response.server_description.summary}\n"
                f"Capabilities: {', '.join(server_response.server_description.capabilities)}\n"
                f"Limitations: {', '.join(server_response.server_description.limitations)}"
            )
            server_embedding = await self.embedding_service.create_embedding([description_text])
            # if one tool fails, we want to abort the whole server indexing
            await self.index_server_tools(server_response, server_embedding[0])  
            nb_tools = len(server_response.tools.tools)
            await self.index_service.add_server(
                server_name=server_name,
                mcp_server_description=server_response.server_description,
                embedding=server_embedding[0],
                nb_tools=nb_tools
            )

            logger.info(f"Indexed server: {server_name}")
        finally:
            self.mcp_server_semaphore.release()

    async def index_single_tool(self, server_name: str, tool:Tool, server_embedding: list[float], barrier:asyncio.Barrier) -> None:
        await self.mcp_server_tool_semaphore.acquire()
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
                alpha=self.api_keys_settings.MCP_SERVER_EMBEDDING_WEIGHTS
            )
            logger.info(f"Prepared to index tool: {tool.name} from server '{server_name}', waiting at barrier...")
            await barrier.wait()  # synchronize before indexing: this will prevent to add the tool if another tool failed
            await self.index_service.add_tool(
                server_name=server_name,
                tool_name=tool.name,
                tool_description=enhanced_description,
                tool_schema=tool.inputSchema,
                embedding=weighted_embedding
            )
            logger.debug(f"Indexed tool: {tool.name} from server '{server_name}'")
        finally:
            self.mcp_server_tool_semaphore.release()
            logger.info(f"Released semaphore for tool: {tool.name} from server '{server_name}'")

    async def index_server_tools(self, server_response:McpServerFullDescription, server_embedding: list[float]) -> None:
        server_name = server_response.server_name
        tools = server_response.tools.tools

        logger.info(f"Indexing {len(tools)} tools from server '{server_name}'")

        barrier = asyncio.Barrier(parties=len(tools))
        tasks:List[asyncio.Task] = []
        for tool in tools:
            task = asyncio.create_task(self.index_single_tool(server_name, tool, server_embedding, barrier))
            task.set_name(f"INDEX_TOOL_{server_name}_{tool.name}")
            tasks.append(task)
        
        logger.info(f"server : {server_name}, waiting for tools to be indexed...")
        kill_all_tasks = False
        
        for completed_task in asyncio.as_completed(tasks):
            try:
                await completed_task
            except Exception as e:
                logger.error(f"Error indexing tool from server '{server_name}': {e}")
                kill_all_tasks = True
                break 

        if not kill_all_tasks:
            logger.info(f"Completed indexing tools from server '{server_name}'")
            return
        
        logger.warning(f"Errors occurred during tool indexing for server {server_name}, aborting remaining tasks")
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise Exception(f"Aborted indexing tools from server '{server_name}' due to errors")
    
    async def subscriber(self):
        while True:
            try:
                task = await self.priority_queue.get()
                priority, (server_name, tool_name, arguments, task_id) = task
                logger.info(f"Processing background tool task {task_id} for tool '{tool_name}' on server '{server_name}' with priority {priority}")
                task_handler = asyncio.create_task(
                    self.handle_tool_call(
                        server_name=server_name,
                        tool_name=tool_name,
                        arguments=arguments,
                        timeout=120
                    )
                )
                self.background_tasks[task_id] = task_handler
                with suppress(Exception):
                    await task_handler
                logger.info(f"Completed background tool task {task_id} for tool '{tool_name}' on server '{server_name}'")         
                self.priority_queue.task_done()
            except asyncio.CancelledError:
                break 

    async def call_tool(self, session:ClientSession, encoded_tool_name:bytes, encdoded_tool_arguments:bytes) -> bytes:
        try:
            tool_name = encoded_tool_name.decode('utf-8')
            tool_arguments = json.loads(encdoded_tool_arguments.decode('utf-8'))
            
            result = await session.call_tool(name=tool_name, arguments=tool_arguments)
            content = []
            for content_block in result.content:  # check content type
                content_block_dict = content_block.model_dump()
                content_block_dict.pop("annotations", None)
                content_block_dict.pop("meta", None)
                content.append(content_block_dict)
            
            response_payload = json.dumps({"status": True, "content": content}).encode('utf-8')
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}")
            response_payload = json.dumps({"status": False, "error_message": str(e)}).encode('utf-8')
        
        return response_payload
        
    async def background_mcp_server(self, server_name:str, mcp_startup_config:McpStartupConfig, timeout:int=50):
        server_parameters = StdioServerParameters(
            command=mcp_startup_config.command,
            args=mcp_startup_config.args,
            env=mcp_startup_config.env
        )
        async with AsyncExitStack() as resources_manager:
            transport = await resources_manager.enter_async_context(stdio_client(server=server_parameters))
            read, write = transport 
            session = await resources_manager.enter_async_context(ClientSession(read, write))
            try:
                async with asyncio.timeout(delay=timeout):
                    await session.initialize()
                    logger.info("Initialized MCP session")
                    tools_result = await session.list_tools()
                    logger.info(f"Retrieved {len(tools_result.tools)} tools from MCP server")        
            except TimeoutError:
                logger.error("Timeout while trying to initialize MCP session.") 
                await resources_manager.aclose()
                raise 
            except Exception as e:
                logger.error(f"Error initializing MCP session: {e}")
                await resources_manager.aclose()
                raise 
            
            current_task = asyncio.current_task()
            task_name = current_task.get_name()
            task_name = task_name.replace("PENDING", "RUNNING")
            current_task.set_name(task_name)

            server_hash = sha256(server_name.encode('utf-8')).hexdigest()
            
            router_socket = await resources_manager.enter_async_context(
                self.create_socket(zmq.ROUTER, "bind", f"inproc://{server_hash}")
            )

            poller = azmq.Poller()
            poller.register(router_socket, zmq.POLLIN)

            keep_loop = True
            while keep_loop:
                try:
                    if not keep_loop:
                        logger.info("Shutting down background MCP server loop")
                        break

                    hmap_socket_flag = dict(await poller.poll(timeout=self.api_keys_settings.MCP_SERVER_POLLING_INTERVAL_MS))
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
                    response_payload = await self.call_tool(
                        session=session,
                        encoded_tool_name=encoded_tool_name,
                        encdoded_tool_arguments=encdoded_tool_arguments
                    )
                    await router_socket.send_multipart([caller_id, b"", response_payload])
                except asyncio.CancelledError:
                    logger.info("Background MCP server task cancelled")
                    keep_loop = False
                except Exception as e:
                    logger.error(f"Error in background MCP server loop: {e}")
                    break 
            
            poller.unregister(router_socket)
            router_socket.close(linger=0)
            logger.info(f"MCP server '{server_name}' has been shut down")
        
    def clear_mcp_server_task(self, task:asyncio.Task):
        task_name = task.get_name()
        _, _, server_name, _ = task_name.split("_")
        if server_name not in self.mcp_server_tasks:
            return 
        del self.mcp_server_tasks[server_name]
        logger.info(f"Cleared MCP server task for: {server_name}")

    async def start_mcp_server(self, server_name: str) -> Tuple[bool, Optional[str]]:
        if server_name in self.mcp_server_tasks:
            return True, f"Server '{server_name}' already running"
        
        if not self.mcp_config or server_name not in self.mcp_config.mcpServers:
            return False, f"Server '{server_name}' not found in config"

        startup_config = self.mcp_config.mcpServers[server_name]

        task = asyncio.create_task(
            self.background_mcp_server(
                server_name=server_name,
                mcp_startup_config=startup_config,
                timeout=startup_config.timeout
            )
        )
        task.set_name(f"BACKGROUND_TASK_{server_name}_PENDING")
        
        self.mcp_server_tasks[server_name] = task
        task.add_done_callback(self.clear_mcp_server_task)

        keep_loop = True
        while keep_loop and not task.done():
            task_name = task.get_name()
            _, _, _, status = task_name.split("_")
            if status == "RUNNING":
                keep_loop = False
                logger.info(f"MCP server {server_name} is now running")
                break
            await asyncio.sleep(1)
            logger.info(f"Waiting for MCP server {server_name} to start...")
        
        if not task.done():
            return True, f"Successfully started server '{server_name}'"
        
        error = str(task.exception()) if task.exception() else "Unknown error"
        logger.error(f"MCP server task for '{server_name}' terminated during startup with error: {error}")
        return False, f"Failed to start MCP server task for '{server_name}': {error}"
    
    
    async def shutdown_mcp_server(self, server_name: str) -> Tuple[bool, Optional[str]]:
        task = self.mcp_server_tasks.get(server_name)
        if not task:
            logger.info(f"Server '{server_name}' not running")
            return True, f"Server '{server_name}' not running"
        
        try:
            task.cancel()
            await task
            logger.info(f"Successfully shutdown MCP server: {server_name}")
            return True, f"Successfully shutdown server '{server_name}'"
        except Exception as e:
            logger.error(f"Error shutting down server '{server_name}': {e}")
            return False, str(e)
    
    async def handle_tool_call(self, server_name: str, tool_name: str, arguments: Optional[dict]=None, timeout:float=60) -> List[ContentBlock]:
        server_hash = sha256(server_name.encode('utf-8')).hexdigest()
        async with self.create_socket(zmq.DEALER, "connect", f"inproc://{server_hash}") as socket:
            await socket.send_multipart([b"", tool_name.encode('utf-8'), json.dumps(arguments or {}).encode('utf-8')])
            try:
                async with asyncio.timeout(delay=timeout):
                    _, encoded_response = await socket.recv_multipart()
                    response:Dict = json.loads(encoded_response.decode('utf-8'))
                    if response["status"]:
                        return response["content"]
                    error_message = response.get("error_message", "Unknown error")
                    raise Exception(f"Error executing tool '{tool_name}' on server '{server_name}': {error_message}")
            except TimeoutError:
                raise Exception(f"Timeout waiting for tool '{tool_name}' response from server '{server_name}'")
            
    async def execute_tool(self, server_name: str, tool_name: str, arguments: Optional[dict]=None, timeout:float=60, priority:int=1, in_background:bool=False) -> List[ContentBlock]:
        if not server_name in self.mcp_server_tasks:
            raise Exception(f"Server '{server_name}' not running")
        
        task = self.mcp_server_tasks[server_name]
        task_name = task.get_name()
        _, _, _, status = task_name.split("_")
        if status != "RUNNING":
            raise Exception(f"Server '{server_name}' not in running state")
        
        if in_background:
            task_id = str(uuid4())
            await self.priority_queue.put((priority, (server_name, tool_name, arguments, task_id)))
            logger.info(f"Queued tool '{tool_name}' on server '{server_name}' for background execution with priority {priority}")
            return [
                {
                    "type": "text",
                    "text": f"Tool '{tool_name}' on server '{server_name}' has been queued for background execution with task ID {task_id}."
                }, 
                {
                    "type": "text",
                    "text": f"Use the task ID {task_id} to track the status(result if done) of your background task."
                }
            ]
        
        result = await self.handle_tool_call(
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            timeout=timeout
        )
        return result

    async def poll_task_result(self, task_id:str) -> Tuple[bool, Optional[List[ContentBlock]], Optional[str]]:
        task = self.background_tasks.get(task_id)
        if not task:
            return False, None, f"No background task found with ID {task_id}"
        
        if not task.done():
            return False, None, f"Background task with ID {task_id} is still running"
        
        try:
            result = task.result()
            del self.background_tasks[task_id]
            return True, result, None
        except Exception as e:
            del self.background_tasks[task_id]
            return False, None, str(e)
    
    def list_running_servers(self) -> list:
        return list(self.mcp_server_tasks.keys())
        