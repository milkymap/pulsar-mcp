import json 

from typing import List

from contextlib import asynccontextmanager
from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent
from typing import Optional, Literal, Annotated

from .mcp_engine import MCPEngine
from .log import logger

class MCPServer:
    def __init__(self, mcp_engine:MCPEngine):
        self.mcp_engine = mcp_engine
        self.mcp = FastMCP(
            name="pulsar_mcp",
            instructions="""
            Pulsar MCP: Intelligent MCP Ecosystem Explorer
            I help you discover and manage MCP tools across your entire ecosystem through semantic search and progressive exploration.
            Discovery: Search for tools using natural language - find what you need without knowing exact names
            Exploration: Browse servers and tools with guided next-step recommendations
            Management: Start/stop servers and execute tools with proper schema validation
            Background Execution: Run long-running tools asynchronously and track progress with task IDs
            Progressive: Minimal results first, detailed schemas only when needed for efficient token usage
            Start with search() to find relevant tools, then follow the guided workflow to execution.
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
        self.define_tools(mcp, self.mcp_engine)
        yield

    def define_tools(self, mcp:FastMCP, mcp_engine:MCPEngine):
        @mcp.tool(
            name="semantic_router",
            description="""
            Universal gateway to the Pulsar MCP ecosystem. Execute any MCP operation through a single unified interface.
            OPERATIONS & PARAMETERS:
            - search
            Required: query
            Optional: limit, scope, filter_by_servers, enhanced
            Discover tools/servers using natural language queries with semantic ranking

            - get_server_info
            Required: server_name
            View detailed server capabilities, limitations, and tool count

            - list_indexed_servers
            Optional: limit, offset
            Browse all available MCP servers with pagination support

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

            WORKFLOW:
            1. Discovery: search → get_server_info → list_server_tools
            2. Preparation: get_tool_details → manage_server(start)
            3. Execution: execute_tool → poll_task_result (if background)
            4. Cleanup: manage_server(shutdown)
            5. Repeat as needed for new tasks

            IMPORTANT BEST PRACTICES:
            1 ALWAYS use get_tool_details before execute_tool - never execute without checking the schema first!
            2 PREFER search over list_server_tools for discovery - it's more efficient and finds relevant tools faster
            3 START with search to discover what you need - don't browse blindly through servers
            4 VERIFY server is running with list_running_servers before execute_tool, or start it with manage_server
            5 USE scope parameter in search to filter by 'server' or 'tool' type for better results
            6 FOR background tasks: always save the task_id and poll with poll_task_result to get results
            7 CHECK server capabilities with get_server_info to understand limitations before heavy usage
            8 FOR search: write clear, descriptive queries with full context (e.g., "tools for reading PDF documents ...query can be very detailed" not just "PDF"). If your query is vague or short, set enhanced=True to trigger LLM-powered query enhancement for better results


            Only 'operation' parameter is required. Other parameters depend on the chosen operation.
            """
        )
        async def semantic_router(
            operation: Annotated[
                Literal[
                    "search",
                    "get_server_info", 
                    "list_indexed_servers",
                    "list_server_tools",
                    "get_tool_details",
                    "manage_server",
                    "list_running_servers",
                    "execute_tool",
                    "poll_task_result"
                ],
                "The operation to perform in the MCP ecosystem"
            ],
            # search parameters
            query: Annotated[str, "Natural language search query (be specific in term of technical features) for finding servers or tools"] = None,
            limit: Annotated[int, "Maximum number of results to return (default: 10 for search, 20 for list, 50 for tools)"] = 10,
            scope: Annotated[List[str], "Filter results by type: ['server'], ['tool'], or None for mixed results"] = None,
            enhanced: Annotated[bool, "Use LLM query enhancement for better search results (default: True)"] = True,
            # Server/tool identification parameters
            server_name: Annotated[str, "Name of the MCP server to operate on"] = None,
            filter_by_servers: Annotated[List[str], "List of server names to filter tool search results"] = None,
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
        ) -> ToolResult:
            try:
                match operation:
                    case "search":
                        if query is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'query' is required for search")]
                            )
                        return await search(
                            query=query,
                            limit=limit,
                            scope=scope,
                            server_names=filter_by_servers,
                            enhanced=enhanced if enhanced is not None else True
                        )
                    
                    case "get_server_info":
                        if server_name is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'server_name' is required for get_server_info")]
                            )
                        return await get_server_info(server_name=server_name)
                    
                    case "list_indexed_servers":
                        return await list_indexed_servers(
                            limit=limit,
                            offset=offset
                        )
                    
                    case "list_server_tools":
                        if server_name is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'server_name' is required for list_server_tools")]
                            )
                        return await list_server_tools(
                            server_name=server_name,
                            limit=limit,
                            offset=offset
                        )
                    
                    case "get_tool_details":
                        if server_name is None or tool_name is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'server_name' and 'tool_name' are required for get_tool_details")]
                            )
                        return await get_tool_details(
                            tool_name=tool_name,
                            server_name=server_name
                        )
                    
                    case "manage_server":
                        if server_name is None or action is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'server_name' and 'action' are required for manage_server")]
                            )
                        return await manage_server(
                            server_name=server_name,
                            action=action
                        )
                    
                    case "list_running_servers":
                        return await list_running_servers()
                    
                    case "execute_tool":
                        if server_name is None or tool_name is None:
                            return ToolResult(
                                content=[TextContent(type="text", text="Error: 'server_name' and 'tool_name' are required for execute_tool")]
                            )
                        return await execute_tool(
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
                        return await poll_task_result(task_id=task_id)
                    
                    case _:
                        return ToolResult(
                            content=[TextContent(type="text", text=f"Unknown action: {action}")]
                        )
                        
            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Router failed: {str(e)}")]
                )

        async def search(query: str, limit: int = 10, scope: Optional[List[str]] = None, server_names: list[str] = None, enhanced: bool = True) -> ToolResult:
            try:
                if enhanced:
                    enhanced_query = await mcp_engine.descriptor_service.enhance_query_with_llm(query)
                else:
                    enhanced_query = query

                query_embedding = await mcp_engine.embedding_service.create_embedding([enhanced_query])
                all_results = await mcp_engine.index_service.search(
                    embedding=query_embedding[0],
                    top_k=limit,
                    server_names=server_names,
                    scope=scope
                )

                minimal_results = []
                for result in all_results:
                    payload = result.get('payload', {})
                    if payload.get('type') == 'server':
                        minimal_results.append({
                            "type": "server",
                            "server_name": payload.get('server_name'),
                            "title": payload.get('title'),
                            "score": result.get('score', 0)
                        })
                    elif payload.get('type') == 'tool':
                        minimal_results.append({
                            "type": "tool",
                            "server_name": payload.get('server_name'),
                            "tool_name": payload.get('tool_name'),
                            "title": payload.get('title'),
                            "score": result.get('score', 0)
                        })

                result_text = f"Found {len(minimal_results)} results for query: '{query}'"
                if scope:
                    result_text += f" (scope: {scope})"
                
                guidance = "Next steps:\n"
                guidance += "• For servers: Use get_server_info to see capabilities and limitations\n"
                guidance += "• For tools: Use get_tool_details to see full schema before execution\n"
                guidance += "• Use list_server_tools to browse all tools from a specific server"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=result_text),
                        *[ TextContent(type="text", text=json.dumps(res)) for res in minimal_results],
                        TextContent(type="text", text=guidance)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Search failed: {str(e)}")]
                )

        async def get_server_info(server_name: str) -> ToolResult:
            try:
                server_info = await mcp_engine.index_service.get_server(server_name)
                
                if server_info is None:
                    return ToolResult(
                        content=[TextContent(type="text", text=f"Server '{server_name}' not found in index")]
                    )

                info_text = f"Server: {server_name}\n"
                info_text += f"Title: {server_info.get('title')}\n"
                info_text += f"Tools: {server_info.get('nb_tools')}\n\n"
                info_text += f"Summary: {server_info.get('summary')}\n\n"

                info_text += "Capabilities:\n"
                for cap in server_info.get('capabilities'):
                    info_text += f"• {cap}\n"

                info_text += "\nLimitations:\n"
                for lim in server_info.get('limitations'):
                    info_text += f"• {lim}\n"

                guidance = f"Next steps:\n"
                guidance += f"• Use list_server_tools('{server_name}') to see available tools\n"
                guidance += f"• Use manage_server('{server_name}', 'start') to start the server for execution"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=info_text),
                        TextContent(type="text", text=guidance)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to get server info: {str(e)}")]
                )

        async def list_indexed_servers(limit: int = 20, offset: Optional[str] = None) -> ToolResult:
            try:
                servers, offset = await mcp_engine.index_service.list_servers(
                    limit=limit,
                    offset=offset
                )
                total_servers = await mcp_engine.index_service.nb_servers()

                minimal_servers = []
                for payload in servers:
                    minimal_servers.append({
                        "server_name": payload.get('server_name'),
                        "title": payload.get('title'),
                        "nb_tools": payload.get('nb_tools', 0)
                    })

                result_text = f"Found {len(minimal_servers)} servers (total: {total_servers})\n\n"
                for server in minimal_servers:
                    result_text += f"• {server['server_name']}: {server['title']} ({server['nb_tools']} tools)\n"

                guidance = "Next steps:\n"
                guidance += "• Use get_server_info(server_name) for detailed capabilities\n"
                guidance += "• Use list_server_tools(server_name) to browse tools\n"
                guidance += "• Use search(query, scope='server') for targeted search"
                guidance += f"• Use offset '{offset}' for next page of results" if offset else "Last page of results"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=result_text),
                        TextContent(type="text", text=guidance)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to list servers: {str(e)}")]
                )

        async def list_server_tools(server_name: str, limit:int=50, offset:Optional[str]=None) -> ToolResult:
            try:
                tools, offset = await mcp_engine.index_service.list_tools(
                    server_name=server_name,
                )
                if not tools:
                    return ToolResult(
                        content=[TextContent(type="text", text=f"No tools found for server '{server_name}'")]
                    )

                content = []
                for payload in tools:
                    content.append(
                        TextContent(
                            type="text", 
                            text=json.dumps({
                                "tool_name": payload.get('tool_name'),
                                "title": payload.get('title')
                            })
                        )
                    )

                guidance = "Next steps:\n"
                guidance += f"• Use get_tool_details('{server_name}', 'tool_name') for schema\n"
                guidance += f"• Use manage_server('{server_name}', 'start') before execution\n"
                guidance += "• Always check tool schema before calling execute_tool"
                guidance += f"• Use offset '{offset}' for next page of results" if offset else "Last page of results"
                content.append(TextContent(type="text", text=guidance))
                return ToolResult(content=content)

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to list tools for server '{server_name}': {str(e)}")]
                )

        async def get_tool_details(tool_name: str, server_name: str) -> ToolResult:
            try:

                tool_info = await mcp_engine.index_service.get_tool(
                    server_name=server_name,
                    tool_name=tool_name
                )

                if tool_info is None:
                    return ToolResult(
                        content=[TextContent(type="text", text=f"Tool '{tool_name}' not found on server '{server_name}'")]
                    )

                details = f"Tool: {tool_name} (from {server_name})\n\n"
                details += f"Description: {tool_info.get('tool_description', 'No description available')}\n\n"
                details += f"Schema:\n{tool_info.get('tool_schema', 'No schema available')}\n"

                guidance = "IMPORTANT: Review this schema carefully before execution!\n\n"
                guidance += "Next steps:\n"
                guidance += f"• Ensure server is running: manage_server('{server_name}', 'start')\n"
                guidance += f"• Execute: execute_tool('{server_name}', '{tool_name}', arguments)\n"
                guidance += "• Always provide correct arguments matching the schema above"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=details),
                        TextContent(type="text", text=guidance)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to get tool details: {str(e)}")]
                )

        async def manage_server(server_name: str, action: str) -> ToolResult:
            try:
                match action:
                    case "start":
                        success, message = await mcp_engine.start_mcp_server(server_name)
                        result_text = f"Server '{server_name}' start {'successful' if success else 'failed' } message : {message}"
                    case "shutdown":
                        success, message = await mcp_engine.shutdown_mcp_server(server_name)
                        result_text = f"Server '{server_name}' shutdown {'successful' if success else 'failed'} message : {message}"
                    case _:
                        return ToolResult(
                            content=[TextContent(type="text", text=f"Invalid action: {action}. Use 'start' or 'shutdown'.")]
                        )

                guidance = "Next steps:\n"
                if action == "start" and success:
                    guidance += f"• Server is ready for tool execution\n"
                    guidance += f"• Use list_server_tools('{server_name}') to browse available tools\n"
                    guidance += f"• Use execute_tool('{server_name}', 'tool_name', arguments) to run tools"
                elif action == "shutdown" and success:
                    guidance += f"• Server session has been terminated\n"
                    guidance += f"• Use manage_server('{server_name}', 'start') to restart when needed"
                else:
                    guidance += "• Check server configuration and try again\n"
                    guidance += "• Verify server exists in your MCP config file"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=result_text),
                        TextContent(type="text", text=guidance)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Server management failed: {str(e)}")]
                )

        async def list_running_servers() -> ToolResult:
            try:
                running_servers = mcp_engine.list_running_servers()

                if not running_servers:
                    result_text = "No MCP servers are currently running."
                    guidance = "Next steps:\n"
                    guidance += "• Use list_indexed_servers() to see available servers\n"
                    guidance += "• Use manage_server(server_name, 'start') to start a server\n"
                    guidance += "• Servers must be running before you can execute tools"
                else:
                    result_text = f"Active MCP servers ({len(running_servers)} running):\n\n"
                    for server in running_servers:
                        result_text += f"• {server}\n"

                    guidance = "Next steps:\n"
                    guidance += "• Use list_server_tools(server_name) to browse tools\n"
                    guidance += "• Use get_tool_details() before execution\n"
                    guidance += "• Use execute_tool() to run tools on active servers"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=result_text),
                        TextContent(type="text", text=guidance)
                    ]
                )
            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to list running servers: {str(e)}")]
                )

        async def execute_tool(server_name: str, tool_name: str, arguments: dict = None, timeout:float=60, in_background:bool=False, priority:int=1) -> ToolResult:
            try:
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                
                result = await mcp_engine.execute_tool(
                    server_name=server_name,
                    tool_name=tool_name,
                    arguments=arguments,
                    timeout=timeout,
                    in_background=in_background,
                    priority=priority
                )
                return ToolResult(content=result)
            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Execution failed: {str(e)}")]
                )

        async def poll_task_result(task_id: str) -> ToolResult:
            try:
                is_done, result_content, error_msg = await mcp_engine.poll_task_result(task_id)

                if error_msg:
                    return ToolResult(
                        content=[TextContent(type="text", text=f"Task polling failed: {error_msg}")]
                    )

                if not is_done:
                    status_text = f"Background task {task_id} is still running."
                    guidance = "Next steps:\\n"
                    guidance += f"• Check again later using poll_task_result('{task_id}')\\n"
                    guidance += "• Background tasks may take time to complete depending on complexity"

                    return ToolResult(
                        content=[
                            TextContent(type="text", text=status_text),
                            TextContent(type="text", text=guidance)
                        ]
                    )

                # Task completed successfully
                status_text = f"Background task {task_id} completed successfully."

                # Return the original tool result content
                content_blocks = [TextContent(type="text", text=status_text)]
                if result_content:
                    content_blocks.extend(result_content)

                guidance = "Task completed! Results are shown above.\\n"
                guidance += "The task has been removed from the background queue."
                content_blocks.append(TextContent(type="text", text=guidance))

                return ToolResult(content=content_blocks)

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to poll task result: {str(e)}")]
                )
