from typing import Optional
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent, ImageContent, AudioContent

from ..services.content_manager import ContentManager


class GetContentTool:
    def __init__(self, content_manager: ContentManager):
        self.content_manager = content_manager

    async def __call__(self, ref_id: str, chunk_index: Optional[int] = None) -> ToolResult:
        return await self.get_content(ref_id, chunk_index)

    async def get_content(self, ref_id: str, chunk_index: Optional[int] = None) -> ToolResult:
        try:
            content = self.content_manager.get_content(ref_id, chunk_index)
            content_type = content.get("type")

            match content_type:
                case "text":
                    text = content.get("text", "")
                    total_chunks = content.get("total_chunks", 1)
                    current_chunk = content.get("chunk_index")

                    if current_chunk is not None:
                        text = f"[Chunk {current_chunk + 1}/{total_chunks}]\n\n{text}"

                    return ToolResult(
                        content=[TextContent(type="text", text=text)]
                    )

                case "image":
                    return ToolResult(
                        content=[ImageContent(
                            type="image",
                            data=content.get("data"),
                            mimeType=content.get("mimeType", "image/png")
                        )]
                    )

                case "audio":
                    return ToolResult(
                        content=[AudioContent(
                            type="audio",
                            data=content.get("data"),
                            mimeType=content.get("mimeType", "audio/wav")
                        )]
                    )

                case _:
                    return ToolResult(
                        content=[TextContent(type="text", text=f"Unknown content type: {content_type}")]
                    )

        except FileNotFoundError as e:
            return ToolResult(
                content=[TextContent(type="text", text=f"Content not found: {str(e)}")]
            )
        except IndexError as e:
            return ToolResult(
                content=[TextContent(type="text", text=f"Invalid chunk index: {str(e)}")]
            )
        except Exception as e:
            return ToolResult(
                content=[TextContent(type="text", text=f"Failed to retrieve content: {str(e)}")]
            )
