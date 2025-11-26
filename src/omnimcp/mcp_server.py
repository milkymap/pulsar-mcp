import json 
import yaml 

from typing import List, Optional, Literal, Annotated
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from .mcp_engine import MCPEngine
from .log import logger

from .tools import (
    SearchTools, GetServerInfoTool,
    ListServerToolsTool, GetToolDetailsTool, ManageServerTool,
    ListRunningServersTool, ExecuteToolTool, PollTaskResultTool,
    GetContentTool
)


class MCPServer:
    def __init__(self, mcp_engine:MCPEngine):
        self.mcp_engine = mcp_engine
        self.mcp = FastMCP(
            name="omnimcp",
            instructions="""
            Pulsar MCP: Intelligent MCP Ecosystem Explorer
            I help you discover and manage MCP tools across your entire ecosystem through semantic search and progressive exploration.
            Discovery: Search for tools using natural language - find what you need without knowing exact names
            Exploration: Browse servers and tools with guided next-step recommendations
            Management: Start/stop servers and execute tools with proper schema validation
            Background Execution: Run long-running tools asynchronously and track progress with task IDs
            Progressive: Minimal results first, detailed schemas only when needed for efficient token usage
            Start with search_tools() to find relevant tools, then follow the guided workflow to execution.
            For background tasks, use execute_tool() with in_background=True, then poll_task_result() to check status.
            """,
            lifespan=self.lifespan
        )
    
    async def run_server(self, transport:str, host:Optional[str]=None, port:Optional[int]=None):
        match transport:
            case "stdio":
                await self.mcp.run_async(transport="stdio")
            case "http":
                if host is None or port is None:
                    logger.error("Host and port must be specified for HTTP transport")
                    raise ValueError("Host and port must be specified for HTTP transport")
                await self.mcp.run_async(transport="http", host=host, port=port)
            case _:
                logger.error(f"Unsupported transport: {transport}")
                raise ValueError(f"Unsupported transport: {transport}")

    @asynccontextmanager
    async def lifespan(self, mcp:FastMCP):
        self.register_tools()
        self.ignore_servers = self.mcp_engine.list_servers_to_ignore()
        total_servers = await self.mcp_engine.index_service.nb_servers(ignore_servers=self.ignore_servers)
        logger.info(f"MCP Server starting with {total_servers} indexed servers.")
        servers, offset = await self.mcp_engine.index_service.list_servers(
            limit=total_servers,
            offset=None,
            ignore_servers=self.ignore_servers
        )
        assert offset is None, "Offset should be None when fetching all servers"
        indexed_servers = []
        for payload in servers:
            server_name = payload.get('server_name')
            item = {
                "server_name": server_name,
                "title": payload.get('title'),
                "nb_tools": payload.get('nb_tools', 0)
            }
            blocked_tools = self.mcp_engine.get_blocked_tools(server_name)
            if blocked_tools:
                item['blocked_tools'] = blocked_tools
            hints = self.mcp_engine.get_server_hints(server_name)
            if hints:
                item['hints'] = hints
            indexed_servers.append(yaml.dump(item, sort_keys=False))
        additional_msg = "\n###\n".join(indexed_servers)
        self.indexed_servers = [payload.get('server_name') for payload in servers]
        
        self.define_semantic_router(mcp, additional_msg)
        yield
    
    def register_tools(self):
        self.execute_tool = ExecuteToolTool(self.mcp_engine)
        self.search_tools = SearchTools(self.mcp_engine)
        self.get_server_info = GetServerInfoTool(self.mcp_engine)
        self.list_server_tools = ListServerToolsTool(self.mcp_engine)
        self.get_tool_details = GetToolDetailsTool(self.mcp_engine)
        self.manage_server = ManageServerTool(self.mcp_engine)
        self.list_running_servers = ListRunningServersTool(self.mcp_engine)
        self.poll_task_result = PollTaskResultTool(self.mcp_engine)
        self.get_content = GetContentTool(self.mcp_engine.content_manager)

    def define_semantic_router(self, mcp:FastMCP, additional_msg:str):
        @mcp.tool(
            name="semantic_router",
            description=f"""
            Universal gateway to the Pulsar MCP ecosystem. Execute any MCP operation through a single unified interface.
            OPERATIONS & PARAMETERS:
            - search_tools
            Required: query
            Optional: limit, scope, target_servers, enhanced
            Discover tools/servers using natural language queries with semantic ranking

            - get_server_info
            Required: server_name
            View detailed server capabilities, limitations, and tool count

            - list_server_tools
            Required: server_name
            Optional: limit, offset
            See all tools available on a specific server with pagination

            - get_tool_details
            Required: server_name, tool_name
            Get complete tool schema and description before execution

            - manage_server
            Required: server_name, action
            Start or shutdown MCP server sessions (action: 'start' or 'shutdown')

            - list_running_servers
            No parameters required
            Show currently active server sessions ready for tool execution

            - execute_tool
            Required: server_name, tool_name
            Optional: arguments, timeout, in_background, priority
            Run tools on active servers with optional background execution support

            - poll_task_result
            Required: task_id
            Check status and retrieve results of background tasks

            - get_content
            Required: ref_id
            Optional: chunk_index
            Retrieve offloaded content (large text chunks, images, audio) by reference ID

            WORKFLOW (UPDATED):
            1. Discovery:
            search_tools → get_server_info (optional) → list_server_tools (optional)
            2. Preparation:
            get_tool_details → manage_server(start)
            3. Execution:
            execute_tool → poll_task_result (if in_background=True)
            4. Cleanup:
            manage_server(shutdown)
            5. Repeat for new tasks

            IMPORTANT BEST PRACTICES:
            1 ALWAYS use get_tool_details before execute_tool - never execute without checking the schema first!
            2 PREFER search_tools over list_server_tools for discovery - it's more efficient and finds relevant tools faster
            3 START with search_tools to discover what you need - don't browse blindly through all tools
            4 VERIFY server is running with list_running_servers before execute_tool, or start it with manage_server
            5 USE scope parameter in search to filter for 'tool', 'prompt' or 'resources' type for better results. Only 'tool' is supported right now.
            6 FOR background tasks: always save the task_id and poll with poll_task_result to get results
            7 CHECK server capabilities with get_server_info to understand limitations before heavy usage
            8 FOR search: write clear, descriptive queries with full context (e.g., "tools for reading PDF documents ...query can be very detailed" not just "PDF"). If your query is vague or
            short, set enhanced=True to trigger LLM-powered query enhancement for better results
            9 ONLY 'operation' parameter is required. Other parameters depend on the chosen operation.
            10 WHEN tool results show [Reference: ref_id], use get_content to retrieve full content. For chunked text, use chunk_index to get specific chunks.

            ACCESS CONTROL:
            - IGNORED SERVERS: Some servers may be ignored by the administrator. They will not appear in search results and all operations (list_server_tools, get_tool_details, 
            manage_server, execute_tool) will return an error.
            - BLOCKED TOOLS: Some tools may be blocked on specific servers. They will appear in search_tools and list_server_tools results with "blocked": true flag. Do NOT attempt to
            execute blocked tools - execution will fail.
            - ALWAYS check the "blocked" field in search/list results before attempting execution.

            -----------------------
            LIST OF INDEXED SERVERS
            -----------------------
            {additional_msg}            
            """
        )
        async def semantic_router(
            operation: Annotated[
                Literal[
                    "search_tools",
                    "get_server_info",
                    "list_server_tools",
                    "get_tool_details",
                    "manage_server",
                    "list_running_servers",
                    "execute_tool",
                    "poll_task_result",
                    "get_content"
                ],
                "The operation to perform in the MCP ecosystem"
            ],
            # search parameters
            query: Annotated[str, "Natural language search query (be specific in term of technical features) for finding servers or tools"] = None,
            limit: Annotated[int, "Maximum number of results to return (default: 10 for search, 20 for list, 50 for tools)"] = 10,
            scope: Annotated[List[str], "Filter results by type. Only tool is supported right now. Use None to get mixed results(tool, prompt, resources)"] = ['tool'],
            enhanced: Annotated[bool, "Use LLM query enhancement for better search results (default: True)"] = True,
            # Server/tool identification parameters
            server_name: Annotated[str, "Name of the MCP server to operate on"] = None,
            target_servers: Annotated[List[str], "List of server names to filter tool search results"] = None,
            tool_name: Annotated[str, "Name of the tool to retrieve details or execute"] = None,
            # Pagination parameters
            offset: Annotated[str, "Pagination cursor for retrieving next page of results"] = None,
            # Server management parameters
            action: Annotated[Literal["start", "shutdown"], "Server lifecycle action: 'start' to launch, 'shutdown' to terminate"] = "start",
            # Tool execution parameters
            arguments: Annotated[dict, "Tool-specific arguments as a dictionary matching the tool's schema"] = None,
            timeout: Annotated[float, "Maximum execution time in seconds (default: 60)"] = 60.0,
            in_background: Annotated[bool, "Execute tool asynchronously and return task ID immediately (default: False)"] = False,
            priority: Annotated[int, "Background task priority, lower numbers run first (default: 1)"] = 1,
            # Background task parameters
            task_id: Annotated[str, "Task identifier for polling background execution status"] = None,
            # Content retrieval parameters
            ref_id: Annotated[str, "Reference ID for retrieving offloaded content"] = None,
            chunk_index: Annotated[int, "Specific chunk index to retrieve (for large text content)"] = None,    
        ) -> ToolResult:
            try:
                match operation:
                    case "search_tools":
                        if query is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'query' is required for search")]
                            )
                        
                        server_names = self.indexed_servers
                        if target_servers is not None and len(target_servers) > 0:
                            server_names = target_servers
                        
                        if len(set(server_names).intersection(set(self.ignore_servers or []))) > 0:
                            return ToolResult(
                                content=[TextContent(type="text", text=f"Error: Some servers in 'target_servers' are set to be ignored: {self.ignore_servers}")]
                            )
                        
                        if server_names is None or len(server_names) == 0:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: No indexed servers available for search")]
                            )

                        return await self.search_tools(
                            query=query,
                            limit=limit,
                            scope=scope,
                            server_names=server_names,  # the only server names to look into
                            enhanced=enhanced if enhanced is not None else True
                        )
                    
                    case "get_server_info":
                        if server_name is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'server_name' is required for get_server_info")]
                            )
                        return await self.get_server_info(server_name=server_name)
                                        
                    case "list_server_tools":
                        if server_name is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'server_name' is required for list_server_tools")]
                            )
                        return await self.list_server_tools(
                            server_name=server_name,
                            limit=limit,
                            offset=offset
                        )
                    
                    case "get_tool_details":
                        if server_name is None or tool_name is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'server_name' and 'tool_name' are required for get_tool_details")]
                            )
                        return await self.get_tool_details(
                            tool_name=tool_name,
                            server_name=server_name
                        )
                    
                    case "manage_server":
                        if server_name is None or action is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'server_name' and 'action' are required for manage_server")]
                            )
                        return await self.manage_server(
                            server_name=server_name,
                            action=action
                        )
                    
                    case "list_running_servers":
                        return await self.list_running_servers()
                    
                    case "execute_tool":
                        if server_name is None or tool_name is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'server_name' and 'tool_name' are required for execute_tool")]
                            )
                        return await self.execute_tool(
                            server_name=server_name,
                            tool_name=tool_name,
                            arguments=arguments,
                            timeout=timeout or 60,
                            in_background=in_background or False,
                            priority=priority or 1
                        )
                    
                    case "poll_task_result":
                        if task_id is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'task_id' is required for poll_task_result")]
                            )
                        return await self.poll_task_result(task_id=task_id)

                    case "get_content":
                        if ref_id is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'ref_id' is required for get_content")]
                            )
                        return await self.get_content(ref_id=ref_id, chunk_index=chunk_index)

                    case _:
                        return ToolResult(
                            content=[TextContent(type="text", text=f"Unknown operation: {operation}")]
                        )
                        
            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Router failed: {str(e)}")]
                )

       