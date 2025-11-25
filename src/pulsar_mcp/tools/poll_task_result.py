from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from ..mcp_engine import MCPEngine

class PollTaskResultTool:
    def __init__(self, mcp_engine: MCPEngine):
        self.mcp_engine = mcp_engine

    async def __call__(self, task_id: str) -> ToolResult:
        return await self.poll_task_result(task_id)

    async def poll_task_result(self, task_id: str) -> ToolResult:
        try:
            is_done, result_content, error_msg = await self.mcp_engine.poll_task_result(task_id)

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