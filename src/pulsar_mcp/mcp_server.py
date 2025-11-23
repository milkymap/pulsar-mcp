import json 

from typing import List

from contextlib import asynccontextmanager
from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent
from typing import Optional

from .mcp_engine import MCPEngine
from .settings import ApiKeysSettings
from .log import logger

class MCPServer:
    def __init__(self, api_keys_settings:ApiKeysSettings, mcp_config_filepath:str):
        self.api_keys_settings = api_keys_settings
        self.mcp_config_filepath = mcp_config_filepath
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
            Start with semantic_search() to find relevant tools, then follow the guided workflow to execution.
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
        async with MCPEngine(self.api_keys_settings) as mcp_engine:
            mcp_engine.load_mcp_config(self.mcp_config_filepath)
            await mcp_engine.index_mcp_servers()
            self.define_tools(mcp, mcp_engine)
            yield

    def define_tools(self, mcp:FastMCP, mcp_engine:MCPEngine):
        @mcp.tool(
            name="semantic_search",
            description="Search across indexed MCP servers and tools using natural language. Returns ranked results with relevance scores, server names, and tool names. Use scope='server' for servers only, scope='tool' for tools only, or leave unset for mixed results. Set server_names to limit tool search to specific servers. Use enhanced=False to skip LLM query enhancement for faster search."
        )
        async def semantic_search(query: str, limit: int = 10, scope: Optional[List[str]] = None, server_names: list[str] = None, enhanced: bool = True) -> ToolResult:
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
                            "score": result.get('score', 0)
                        })

                result_text = f"Found {len(minimal_results)} results for query: '{query}'"
                if scope:
                    result_text += f" (scope: {scope})"
                
                guidance_text = "Next steps:\n"
                guidance_text += "• For servers: Use get_server_info to see capabilities and limitations\n"
                guidance_text += "• For tools: Use get_tool_details to see full schema before execution\n"
                guidance_text += "• Use list_server_tools to browse all tools from a specific server"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=result_text),
                        *[ TextContent(type="text", text=json.dumps(res)) for res in minimal_results],
                        TextContent(type="text", text=guidance_text)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Search failed: {str(e)}")]
                )

        @mcp.tool(
            name="get_server_info",
            description="Get comprehensive information about a specific MCP server including title, summary, capabilities, limitations, and tool count. Essential for understanding server capabilities before use."
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

                guidance_text = f"Next steps:\n"
                guidance_text += f"• Use list_server_tools('{server_name}') to see available tools\n"
                guidance_text += f"• Use manage_server('{server_name}', 'start') to start the server for execution"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=info_text),
                        TextContent(type="text", text=guidance_text)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to get server info: {str(e)}")]
                )

        @mcp.tool(
            name="list_indexed_servers",
            description="Browse all indexed MCP servers with server names, titles, and tool counts. Supports pagination with limit and offset. Ideal for discovering available servers in your ecosystem."
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

                guidance_text = "Next steps:\n"
                guidance_text += "• Use get_server_info(server_name) for detailed capabilities\n"
                guidance_text += "• Use list_server_tools(server_name) to browse tools\n"
                guidance_text += "• Use semantic_search(query, scope='server') for targeted search"
                guidance_text += f"• Use offset '{offset}' for next page of results" if offset else "Last page of results"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=result_text),
                        TextContent(type="text", text=guidance_text)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to list servers: {str(e)}")]
                )

        @mcp.tool(
            name="list_server_tools",
            description="Get all tool names available on a specific MCP server. Returns just the tool names for quick browsing. Use get_tool_details for full schemas before execution."
        )
        async def list_server_tools(server_name: str, limit:int=50, offset:Optional[str]=None) -> ToolResult:
            try:
                tools, offset = await mcp_engine.index_service.list_tools(
                    server_name=server_name,
                )

                tool_names = []
                for payload in tools:
                    tool_names.append(payload.get('tool_name'))

                result_text = f"Tools available on '{server_name}' ({len(tool_names)} total):\n\n"
                for tool_name in tool_names:
                    result_text += f"• {tool_name}\n"

                guidance_text = "Next steps:\n"
                guidance_text += f"• Use get_tool_details('{server_name}', 'tool_name') for schema\n"
                guidance_text += f"• Use manage_server('{server_name}', 'start') before execution\n"
                guidance_text += "• Always check tool schema before calling execute_tool"
                guidance_text += f"• Use offset '{offset}' for next page of results" if offset else "Last page of results"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=result_text),
                        TextContent(type="text", text=guidance_text)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to list tools for server '{server_name}': {str(e)}")]
                )


        @mcp.tool(
            name="get_tool_details",
            description="Get complete tool information including enhanced description and full JSON schema. Critical for understanding tool parameters before execution. Always use this before calling execute_tool."
        )
        async def get_tool_details(tool_name: str, server_name: str) -> ToolResult:
            try:
                tool_info = await mcp_engine.index_service.get_tool(
                    server_name=server_name,
                    tool_name=tool_name
                )

                if tool_info is None:
                    raise ValueError(f"Tool '{tool_name}' not found on server '{server_name}'")

                if tool_info.get('tool_schema') is None:
                    raise ValueError(f"Tool '{tool_name}' on server '{server_name}' has no schema available")
                
                if tool_info.get('tool_description') is None:
                    raise ValueError(f"Tool '{tool_name}' on server '{server_name}' has no description available")

                details_text = f"Tool: {tool_name} (from {server_name})\n\n"
                details_text += f"Description: {tool_info.get('tool_description', 'No description available')}\n\n"
                details_text += f"Schema:\n{tool_info.get('tool_schema', 'No schema available')}\n"

                guidance_text = "IMPORTANT: Review this schema carefully before execution!\n\n"
                guidance_text += "Next steps:\n"
                guidance_text += f"• Ensure server is running: manage_server('{server_name}', 'start')\n"
                guidance_text += f"• Execute: execute_tool('{server_name}', '{tool_name}', arguments)\n"
                guidance_text += "• Always provide correct arguments matching the schema above"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=details_text),
                        TextContent(type="text", text=guidance_text)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to get tool details: {str(e)}")]
                )

        @mcp.tool(
            name="manage_server",
            description="Start or shutdown MCP servers to manage active sessions. Use action='start' to launch servers for tool execution, or action='shutdown' to terminate sessions and free resources."
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

                guidance_text = "Next steps:\n"
                if action == "start" and success:
                    guidance_text += f"• Server is ready for tool execution\n"
                    guidance_text += f"• Use list_server_tools('{server_name}') to browse available tools\n"
                    guidance_text += f"• Use execute_tool('{server_name}', 'tool_name', arguments) to run tools"
                elif action == "shutdown" and success:
                    guidance_text += f"• Server session has been terminated\n"
                    guidance_text += f"• Use manage_server('{server_name}', 'start') to restart when needed"
                else:
                    guidance_text += "• Check server configuration and try again\n"
                    guidance_text += "• Verify server exists in your MCP config file"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=result_text),
                        TextContent(type="text", text=guidance_text)
                    ]
                )

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Server management failed: {str(e)}")]
                )

        @mcp.tool(
            name="list_running_servers",
            description="Show all currently active MCP server sessions. Lists server names that are ready for tool execution. Servers must be running before you can execute tools on them."
        )
        async def list_running_servers() -> ToolResult:
            try:
                running_servers = mcp_engine.list_running_servers()

                if not running_servers:
                    result_text = "No MCP servers are currently running."
                    guidance_text = "Next steps:\n"
                    guidance_text += "• Use list_indexed_servers() to see available servers\n"
                    guidance_text += "• Use manage_server(server_name, 'start') to start a server\n"
                    guidance_text += "• Servers must be running before you can execute tools"
                else:
                    result_text = f"Active MCP servers ({len(running_servers)} running):\n\n"
                    for server in running_servers:
                        result_text += f"• {server}\n"

                    guidance_text = "Next steps:\n"
                    guidance_text += "• Use list_server_tools(server_name) to browse tools\n"
                    guidance_text += "• Use get_tool_details() before execution\n"
                    guidance_text += "• Use execute_tool() to run tools on active servers"

                return ToolResult(
                    content=[
                        TextContent(type="text", text=result_text),
                        TextContent(type="text", text=guidance_text)
                    ]
                )
            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to list running servers: {str(e)}")]
                )

        @mcp.tool(
            name="execute_tool",
            description="Execute a specific tool on a running MCP server with provided arguments. Preserves original tool output format (text, images, JSON, etc.). Server must be started first via manage_server. Use priority to control background task scheduling (lower numbers = higher priority)."
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

        @mcp.tool(
            name="poll_task_result",
            description="Check the status and result of a background task using its task ID. Returns task status (running/completed/failed) and results if available. Essential for tracking long-running background tool executions."
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
                    guidance_text = "Next steps:\\n"
                    guidance_text += f"• Check again later using poll_task_result('{task_id}')\\n"
                    guidance_text += "• Background tasks may take time to complete depending on complexity"

                    return ToolResult(
                        content=[
                            TextContent(type="text", text=status_text),
                            TextContent(type="text", text=guidance_text)
                        ]
                    )

                # Task completed successfully
                status_text = f"Background task {task_id} completed successfully."

                # Return the original tool result content
                content_blocks = [TextContent(type="text", text=status_text)]
                if result_content:
                    content_blocks.extend(result_content)

                guidance_text = "Task completed! Results are shown above.\\n"
                guidance_text += "The task has been removed from the background queue."
                content_blocks.append(TextContent(type="text", text=guidance_text))

                return ToolResult(content=content_blocks)

            except Exception as e:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Failed to poll task result: {str(e)}")]
                )
