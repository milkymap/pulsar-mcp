import json
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from ..mcp_engine import MCPEngine

class ExecuteToolTool:
    def __init__(self, mcp_engine: MCPEngine):
        self.mcp_engine = mcp_engine

    async def __call__(self, server_name: str, tool_name: str, arguments: dict = None,
                      timeout: float = 60, in_background: bool = False, priority: int = 1) -> ToolResult:
        return await self.execute_tool(server_name, tool_name, arguments, timeout, in_background, priority)

    async def execute_tool(self, server_name: str, tool_name: str, arguments: dict = None,
                          timeout: float = 60, in_background: bool = False, priority: int = 1) -> ToolResult:
        try:
            if self.mcp_engine.is_server_ignored(server_name):
                return ToolResult(
                    content=[TextContent(type="text", text=f"Error: Server '{server_name}' is ignored and cannot be accessed")]
                )

            if isinstance(arguments, str):
                arguments = json.loads(arguments)

            result = await self.mcp_engine.execute_tool(
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