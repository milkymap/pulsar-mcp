from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from ..mcp_engine import MCPEngine

class GetServerInfoTool:
    def __init__(self, mcp_engine: MCPEngine):
        self.mcp_engine = mcp_engine

    async def __call__(self, server_name: str) -> ToolResult:
        return await self.get_server_info(server_name)

    async def get_server_info(self, server_name: str) -> ToolResult:
        try:
            server_info = await self.mcp_engine.index_service.get_server(server_name)

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