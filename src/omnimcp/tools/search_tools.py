import json
from typing import List, Optional
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from ..mcp_engine import MCPEngine

class SearchTools:
    def __init__(self, mcp_engine: MCPEngine):
        self.mcp_engine = mcp_engine

    async def __call__(self, query: str, limit: int = 10, scope: Optional[List[str]] = None,
                      server_names: list[str] = None, enhanced: bool = True) -> ToolResult:
        return await self.search(query, limit, scope, server_names, enhanced)

    async def search(self, query: str, limit: int = 10, scope: Optional[List[str]] = None,
                    server_names: list[str] = None, enhanced: bool = True) -> ToolResult:
        try:
            if enhanced:
                enhanced_query = await self.mcp_engine.descriptor_service.enhance_query_with_llm(query)
            else:
                enhanced_query = query

            query_embedding = await self.mcp_engine.embedding_service.create_embedding([enhanced_query])
            all_results = await self.mcp_engine.index_service.search(
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
                    srv_name = payload.get('server_name')
                    tl_name = payload.get('tool_name')
                    minimal_results.append({
                        "type": "tool",
                        "server_name": srv_name,
                        "tool_name": tl_name,
                        "title": payload.get('title'),
                        "score": result.get('score', 0),
                        "blocked": self.mcp_engine.is_tool_blocked(srv_name, tl_name)
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