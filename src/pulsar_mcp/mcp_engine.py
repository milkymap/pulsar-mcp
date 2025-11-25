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
from mcp.types import Tool, ContentBlock, ListToolsResult

from tiktoken import encoding_for_model

from .settings import ApiKeysSettings
from .services.embedding import EmbeddingService
from .services.descriptor import DescriptorService
from .services.index import IndexService
from .types import McpServersConfig, McpStartupConfig, McpServerDescription, McpServerToolDescription
from .utilities import retrieve_mcp_server_tool

from .log import logger

class MCPEngine:
    def __init__(self, api_keys_settings:ApiKeysSettings, mcp_config:McpServersConfig):
        self.api_keys_settings = api_keys_settings
        self.mcp_config = mcp_config
        
    async def __aenter__(self) -> Self:
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

        for _ in range(self.api_keys_settings.BACKGROUND_MCP_TOOL_QUEUE_MAX_SUBSCRIBERS):
            task = asyncio.create_task(self.subscriber())
            self.subscriber_tasks.add(task)

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
        logger.info(f"Starting indexing of {len(self.mcp_config.mcpServers)} MCP servers")
        tasks:List[asyncio.Task] = []
        for server_name, startup_config in self.mcp_config.mcpServers.items():
            if startup_config.ignore:
                logger.info(f"Server '{server_name}' is marked to be ignored. Skipping indexing.")
                continue
            
            server_info = await self.index_service.get_server(server_name=server_name)  # Preload server to check existence
            if server_info is not None and not startup_config.overwrite:    
                logger.info(f"Server '{server_name}' already indexed and reindex not requested. Skipping.")
                continue

            
            task = asyncio.create_task(
                self.protected_index_single_mcp_server(server_name, startup_config)
            )
            task.set_name(f"INDEX_TASK_{server_name}")
            tasks.append(task)
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        nb_failures = 0
        for task, result in zip(tasks, results):
            server_name = task.get_name().replace("INDEX_TASK_", "")
            if not isinstance(result, Exception):
                logger.info(f"Successfully indexed server '{server_name}' with {result} tools")
                continue 
            logger.error(f"Failed to index server '{server_name}': {result}")
            nb_failures += 1
        logger.info(f"Completed indexing MCP servers with {nb_failures} failures out of {len(tasks)} servers to index")
        if nb_failures == len(self.mcp_config.mcpServers):
            raise Exception("All MCP server indexing attempts failed")
    
    async def protected_index_single_mcp_server(self, server_name: str, startup_config: McpStartupConfig) -> int:
        await self.mcp_server_semaphore.acquire()
        try:
            nb_tools = await self.index_single_mcp_server(server_name, startup_config)
            return nb_tools
        finally:
            self.mcp_server_semaphore.release()

    async def index_single_mcp_server(self, server_name: str, startup_config: McpStartupConfig) -> int:    
        logger.info(f"Indexing MCP server: {server_name}")
        
        tools:ListToolsResult = await retrieve_mcp_server_tool(
            server_name=server_name,
            mcp_startup_config=startup_config,
        )
        nb_tools = len(tools.tools)
        tasks:List[asyncio.Task] = []
        for tool in tools.tools:
            tasks.append(
                self.descriptor_service.describe_mcp_server_tool(
                    server_name=server_name,
                    tool_name=tool.name,
                    tool_description=tool.description or "",
                    tool_schema=tool.inputSchema
                ) 
            ) 
        
        enhanced_tools:List[McpServerToolDescription | BaseException] = await asyncio.gather(*tasks, return_exceptions=True)
        exception_encountered = False
        for i, res in enumerate(enhanced_tools):
            if isinstance(res, Exception):
                logger.error(f"Error describing tool '{tools.tools[i].name}' from server '{server_name}': {res}")
                exception_encountered = True
                break 
        
        if exception_encountered:
            raise Exception(f"Failed to describe all tools from server '{server_name}'")
        
        server_description:McpServerDescription = await self.descriptor_service.describe_mcp_server(
            server_name=server_name,
            enhanced_tools=enhanced_tools,
        )
        texts:List[str] = []
        
        texts.append(
            f"{server_description.title}\n"
            f"{server_description.summary}\n"
            f"Capabilities: {', '.join(server_description.capabilities)}\n"
            f"Limitations: {', '.join(server_description.limitations)}"
        )
        for tool_desc in enhanced_tools:
            text = (
                f"{tool_desc.title}\n"
                f"{tool_desc.summary}\n"
                f"Example Utterances: {', '.join(tool_desc.uttirances)}"
            )
            texts.append(text)
        
        embeddings = await self.embedding_service.create_embedding(texts=texts)
        server_embedding, *tool_embeddings = embeddings
        enhanced_tool_embeddings = self.embedding_service.inject_base_into_corpus(
            base_embedding=server_embedding,
            corpus_embeddings=tool_embeddings,
            alpha=self.api_keys_settings.MCP_SERVER_EMBEDDING_WEIGHTS
        )

        tasks:List[asyncio.Task] = []
        for tool, enhanced_tool, tool_embedding in zip(tools.tools, enhanced_tools, enhanced_tool_embeddings):
            tasks.append(
                self.index_service.add_tool(
                    server_name=server_name,
                    tool_name=tool.name,
                    tool_description=tool.description,
                    tool_schema=tool.inputSchema,
                    enhanced_tool=enhanced_tool,
                    embedding=tool_embedding
                )
            )
        await asyncio.gather(*tasks) 
        await self.index_service.add_server(
            server_name=server_name,
            mcp_server_description=server_description,
            embedding=server_embedding,
            nb_tools=nb_tools 
        )
        return nb_tools

    async def subscriber(self):
        logger.info("Starting background MCP tool subscriber")
        while True:
            try:
                task = await self.priority_queue.get()
                priority, (server_name, tool_name, arguments, timeout, task_id) = task
                logger.info(f"Processing background tool task {task_id} for tool '{tool_name}' on server '{server_name}' with priority {priority}")
                task_handler = asyncio.create_task(
                    self.handle_tool_call(
                        server_name=server_name,
                        tool_name=tool_name,
                        arguments=arguments,
                        timeout=timeout
                    )
                )
                self.background_tasks[task_id] = task_handler
                with suppress(Exception):
                    await task_handler
                logger.info(f"Completed background tool task {task_id} for tool '{tool_name}' on server '{server_name}'")         
                self.priority_queue.task_done()
            except asyncio.CancelledError:
                break 

    async def call_mcp_tool(self, session:ClientSession, tool_name:str, tool_arguments:Dict, timeout:float=60) -> bytes:
        try:
            async with asyncio.timeout(delay=timeout):
                result = await session.call_tool(name=tool_name, arguments=tool_arguments)
                content = []
                for content_block in result.content:  # check content type
                    content_block_dict = content_block.model_dump()
                    content_block_dict.pop("annotations", None)
                    content_block_dict.pop("meta", None)
                    content.append(content_block_dict)    
                tool_call_result = json.dumps({"status": True, "content": content}).encode('utf-8')
        except TimeoutError:
            logger.error(f"Timeout while executing tool '{tool_name}'")
            tool_call_result = json.dumps({"status": False, "error_message": "Tool execution timed out"}).encode('utf-8')
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}")
            tool_call_result = json.dumps({"status": False, "error_message": str(e)}).encode('utf-8')
        
        return tool_call_result
        
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
                    
                    if not router_socket in hmap_socket_flag:
                        continue

                    if hmap_socket_flag[router_socket] != zmq.POLLIN:
                        continue

                    caller_id, _, encoded_request = await router_socket.recv_multipart()
                    plain_request:Dict = json.loads(encoded_request.decode('utf-8'))
                    tool_call_result = await self.call_mcp_tool(
                        session=session,
                        tool_name=plain_request.get("tool_name", ""),
                        tool_arguments=plain_request.get("tool_arguments", {}),
                        timeout=plain_request.get("timeout", 60)
                    )
                    await router_socket.send_multipart([caller_id, b"", tool_call_result])
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
            await socket.send_multipart([b""], flags=zmq.SNDMORE)
            await socket.send_json({
                "tool_name": tool_name,
                "tool_arguments": arguments or {},
                "timeout": timeout
            })
            _, encoded_response = await socket.recv_multipart()
            response:Dict = json.loads(encoded_response.decode('utf-8'))
            if response["status"]:
                return response["content"]
            error_message = response.get("error_message", "Unknown error")
            raise Exception(f"Error executing tool '{tool_name}' on server '{server_name}': {error_message}")
            
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
            await self.priority_queue.put((priority, (server_name, tool_name, arguments, timeout, task_id)))
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
            return False, None, None 
        
        try:
            result = task.result()
            del self.background_tasks[task_id]
            return True, result, None
        except Exception as e:
            del self.background_tasks[task_id]
            return False, None, str(e)
    
    def list_running_servers(self) -> list:
        running_server_names = list(self.mcp_server_tasks.keys())
        return running_server_names
    
    def list_servers_to_ignore(self) -> Optional[list]:
        if not self.mcp_config:
            return None 
        
        ignored_servers = [
            server_name 
            for server_name, startup_config in self.mcp_config.mcpServers.items() 
            if startup_config.ignore
        ]
        return ignored_servers or None
    
    def get_server_hints(self, server_name:str) -> Optional[str]:
        if not self.mcp_config or server_name not in self.mcp_config.mcpServers:
            return None 
        
        startup_config = self.mcp_config.mcpServers[server_name]
        return startup_config.hints
        