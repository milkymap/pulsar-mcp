import asyncio 
from uuid import uuid5, NAMESPACE_DNS
from hashlib import sha256

from typing import Dict, Any, List, Optional, Tuple  
from qdrant_client import AsyncQdrantClient, models


from ..log import logger
from ..types import McpServerDescription, McpServerToolDescription

class IndexService:
    def __init__(self, index_name:str, dimensions:int, qdrant_storage_path:str):
        self.index_name = index_name
        self.dimensions = dimensions
        self.qdrant_storage_path = qdrant_storage_path
        
    async def __aenter__(self):
        self.client = AsyncQdrantClient(path=self.qdrant_storage_path)
        if not await self.client.collection_exists(collection_name=self.index_name):
            await self.client.create_collection(
                collection_name=self.index_name,
                vectors_config=models.VectorParams(
                    size=self.dimensions,
                    distance=models.Distance.COSINE
                )
            )
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            logger.error(f"Exception in VectorStoreService context manager: {exc_value}")
            logger.exception(traceback)
        await self.client.close()
    
    async def add_server(self, server_name:str, mcp_server_description:McpServerDescription, embedding:List[float], nb_tools:int):
        await self.client.upsert(
            collection_name=self.index_name,
            points=[
                models.PointStruct(
                    id=str(uuid5(namespace=NAMESPACE_DNS, name=server_name)),
                    vector=embedding,
                    payload={
                        "type": "server",
                        "server_name": server_name,
                        "title": mcp_server_description.title,
                        "summary": mcp_server_description.summary,
                        "capabilities": mcp_server_description.capabilities,
                        "limitations": mcp_server_description.limitations,
                        "nb_tools": nb_tools
                    }
                )
            ]
        )
    
    async def add_tool(self, server_name, tool_name:str, tool_description:str, tool_schema:Dict[str, Any], embedding:List[float], enhanced_tool:McpServerToolDescription):
        tool_id = f"{server_name}::{tool_name}"
        await self.client.upsert(
            collection_name=self.index_name,
            points=[
                models.PointStruct(
                    id=str(uuid5(namespace=NAMESPACE_DNS, name=tool_id)),
                    vector=embedding,
                    payload={
                        "type": "tool",
                        "server_name": server_name,
                        "title": enhanced_tool.title,
                        "summary": enhanced_tool.summary,
                        "utterances": enhanced_tool.utterances,
                        "tool_name": tool_name,
                        "tool_description": tool_description,
                        "tool_schema": tool_schema
                    }
                )
            ]
        )
        
    async def get_server(self, server_name:str) -> Optional[Dict[str, Any]]:
        server_id = str(uuid5(namespace=NAMESPACE_DNS, name=server_name))
        result = await self.client.retrieve(
            collection_name=self.index_name,
            ids=[server_id],
            with_payload=True,
            with_vectors=False
        )
        if not result or len(result) == 0:
            return None 
        return result[0].payload
        
    async def get_tool(self, server_name:str, tool_name:str) -> Optional[Dict[str, Any]]:
        tool_id = str(uuid5(namespace=NAMESPACE_DNS, name=f"{server_name}::{tool_name}"))
        result = await self.client.retrieve(
            collection_name=self.index_name,
            ids=[tool_id],
            with_payload=True,
            with_vectors=False
        )
        if not result or len(result) == 0:
            return None
        return result[0].payload

    async def delete_server(self, server_name:str) -> Dict[str, Any]:
        server_id = str(uuid5(namespace=NAMESPACE_DNS, name=server_name))
        server_data = await self.get_server(server_name)
 
        nb_components = server_data.get("nb_tools", 0) 
        
        if nb_components == 0:
            await self.client.delete(
                collection_name=self.index_name,
                points_selector=models.PointIdsList(points=[server_id])
            )
            return server_data
        
        scroll_result = await self.client.scroll(  # Get all tools associated with the server
            collection_name=self.index_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="server_name",
                        match=models.MatchValue(value=server_name)
                    ),
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="tool")
                    ) 
                ]
            ),
            with_payload=False,
            with_vectors=False,
            limit=nb_components
        )
        
        records, next_point_id = scroll_result
        assert next_point_id is None, "More records found than expected when deleting server components."
        
        await self.client.delete(
            collection_name=self.index_name,
            points_selector=models.PointIdsList(
                points=[point.id for point in records] + [server_id]
            )
        )
        
        return server_data
        
    async def search(self, embedding:List[float], top_k:int=5, server_names:Optional[List[str]]=None, scope:List[str]=None) -> List[Dict[str, Any]]:
        query_filter = []
        if server_names is not None and len(server_names) > 0:
            if scope is not None and "server" in scope:
                raise ValueError("Cannot filter by server_name when searching for servers.")
        
        if server_names:
            query_filter.append(
                models.FieldCondition(
                    key="server_name",
                    match=models.MatchAny(any=server_names)
                )
            )
        if scope is not None and len(scope) > 0:
            # scope value must be one of tool, prompt, resources  
            # only tool is implemented for now
            query_filter.append(
                models.FieldCondition(
                    key="type",
                    match=models.MatchAny(any=scope)
                )
            )
        
        if not query_filter:
            query_filter = None
        else:
            query_filter = models.Filter(must=query_filter)

        records = await self.client.query_points(
            collection_name=self.index_name,
            query=embedding,
            query_filter=query_filter,
            limit=top_k
        )

        result = []
        for point in records.points:
            result.append({
                "id": point.id,
                "score": point.score,
                "payload": point.payload
            })
        
        return result
    
    async def list_servers(self, limit:int=100, offset:Optional[str]=None, ignore_servers:Optional[List[str]]=None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        scroll_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value="server")
                )
            ]
        )
        if ignore_servers is not None and len(ignore_servers) > 0:
            scroll_filter.must_not = [
                models.FieldCondition(
                    key="server_name",
                    match=models.MatchAny(any=ignore_servers)
                )
            ]

        scroll_result = await self.client.scroll(
            collection_name=self.index_name,
            scroll_filter=scroll_filter,
            with_payload=True,
            with_vectors=False,
            limit=limit,
            offset=offset
        )
        records, next_point_id = scroll_result
        
        result = []
        for point in records:
            result.append(point.payload)
        
        return result, next_point_id

    async def list_tools(self, server_name: str, limit: int = 20, offset: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        scroll_result = await self.client.scroll(
            collection_name=self.index_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="tool")
                    ),
                    models.FieldCondition(
                        key="server_name",
                        match=models.MatchValue(value=server_name)
                    )
                ]
            ),
            with_payload=True,
            with_vectors=False,
            limit=limit,
            offset=offset
        )
        records, next_point_id = scroll_result

        result = []
        for point in records:
            result.append(point.payload)

        return result, next_point_id

        
    async def nb_servers(self, ignore_servers:Optional[List[str]]=None):
        count_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value="server")
                )
            ]
        )
        if ignore_servers is not None and len(ignore_servers) > 0:
            count_filter.must_not = [
                models.FieldCondition(
                    key="server_name",
                    match=models.MatchAny(any=ignore_servers)
                )
            ]

        count_result = await self.client.count(
            collection_name=self.index_name,
            count_filter=count_filter
        )
        return count_result.count

    async def nb_tools(self, ignore_servers:Optional[List[str]]=None):
        count_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value="tool")
                )
            ]
        )
        if ignore_servers is not None and len(ignore_servers) > 0:
            count_filter.must_not = [
                models.FieldCondition(
                    key="server_name",
                    match=models.MatchAny(any=ignore_servers)
                )
            ]
        count_result = await self.client.count(
            collection_name=self.index_name,
            count_filter=count_filter
        )
        return count_result.count
        