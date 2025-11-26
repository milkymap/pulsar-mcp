from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from ..mcp_engine import MCPEngine

class GetToolDetailsTool:
    def __init__(self, mcp_engine: MCPEngine):
        self.mcp_engine = mcp_engine

    async def __call__(self, tool_name: str, server_name: str) -> ToolResult:
        return await self.get_tool_details(tool_name, server_name)

    async def get_tool_details(self, tool_name: str, server_name: str) -> ToolResult:
        try:
            if self.mcp_engine.is_server_ignored(server_name):
                return ToolResult(
                    content=[TextContent(type="text", text=f"Error: Server '{server_name}' is ignored and cannot be accessed")]
                )

            tool_info = await self.mcp_engine.index_service.get_tool(
                server_name=server_name,
                tool_name=tool_name
            )

            if tool_info is None:
                return ToolResult(
                    content=[TextContent(type="text", text=f"Tool '{tool_name}' not found on server '{server_name}'")]
                )

            is_blocked = self.mcp_engine.is_tool_blocked(server_name, tool_name)

            details = f"Tool: {tool_name} (from {server_name})\n"
            if is_blocked:
                details += "⚠️ WARNING: This tool is BLOCKED and cannot be executed.\n"
            details += f"\nDescription: {tool_info.get('tool_description', 'No description available')}\n\n"
            details += f"Schema:\n{tool_info.get('tool_schema', 'No schema available')}\n"

            guidance = "IMPORTANT: Review this schema carefully before execution!\n\n"
            if is_blocked:
                guidance = "⚠️ This tool is blocked and will fail if you try to execute it.\n\n"
            guidance += "Next steps:\n"
            guidance += f"Ensure server is running: manage_server('{server_name}', 'start')\n"
            guidance += f"Execute: execute_tool('{server_name}', '{tool_name}', arguments)\n"
            guidance += "Always provide correct arguments matching the schema above"
            guidance += "For long running tool, consider to launch them in background and poll for results."

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