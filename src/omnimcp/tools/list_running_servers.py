from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from ..mcp_engine import MCPEngine

class ListRunningServersTool:
    def __init__(self, mcp_engine: MCPEngine):
        self.mcp_engine = mcp_engine

    async def __call__(self) -> ToolResult:
        return await self.list_running_servers()

    async def list_running_servers(self) -> ToolResult:
        try:
            running_servers = self.mcp_engine.list_running_servers()

            if not running_servers:
                result_text = "No MCP servers are currently running."
                guidance = "Next steps:\n"
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