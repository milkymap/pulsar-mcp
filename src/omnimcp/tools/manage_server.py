from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from ..mcp_engine import MCPEngine

class ManageServerTool:
    def __init__(self, mcp_engine: MCPEngine):
        self.mcp_engine = mcp_engine

    async def __call__(self, server_name: str, action: str) -> ToolResult:
        return await self.manage_server(server_name, action)

    async def manage_server(self, server_name: str, action: str) -> ToolResult:
        try:
            if self.mcp_engine.is_server_ignored(server_name):
                return ToolResult(
                    content=[TextContent(type="text", text=f"Error: Server '{server_name}' is ignored and cannot be accessed")]
                )

            match action:
                case "start":
                    success, message = await self.mcp_engine.start_mcp_server(server_name)
                    result_text = f"Server '{server_name}' start {'successful' if success else 'failed' } message : {message}"
                case "shutdown":
                    success, message = await self.mcp_engine.shutdown_mcp_server(server_name)
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