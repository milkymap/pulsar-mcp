import pytest
import tempfile
import shutil
from unittest.mock import AsyncMock, MagicMock, patch
from qdrant_client import models
from src.pulsar_mcp.services.index import IndexService
from src.pulsar_mcp.types import McpServerDescription, McpServerToolDescription


@pytest.fixture
def temp_storage():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def index_service(temp_storage):
    return IndexService(
        index_name="test_index",
        dimensions=1024,
        qdrant_storage_path=temp_storage
    )


class TestIndexServiceInit:
    def test_initialization(self, index_service):
        assert index_service.index_name == "test_index"
        assert index_service.dimensions == 1024


class TestIndexServiceContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_creates_collection_if_not_exists(self, index_service):
        async with index_service:
            assert index_service.client is not None
            # Collection should be created during __aenter__
            exists = await index_service.client.collection_exists("test_index")
            assert exists

    @pytest.mark.asyncio
    async def test_context_manager_reuses_existing_collection(self, index_service):
        async with index_service:
            pass

        # Reopen and collection should still exist
        async with index_service:
            exists = await index_service.client.collection_exists("test_index")
            assert exists


class TestAddServer:
    @pytest.mark.asyncio
    async def test_add_server_basic(self, index_service):
        async with index_service:
            server_desc = McpServerDescription(
                title="Test Server",
                summary="A test MCP server",
                capabilities=["cap1", "cap2"],
                limitations=["limit1"]
            )
            embedding = [0.1] * 1024

            await index_service.add_server(
                server_name="test_server",
                mcp_server_description=server_desc,
                embedding=embedding,
                nb_tools=5
            )

            # Verify server was added
            result = await index_service.get_server("test_server")
            assert result is not None
            assert result["type"] == "server"
            assert result["server_name"] == "test_server"
            assert result["title"] == "Test Server"
            assert result["nb_tools"] == 5

    @pytest.mark.asyncio
    async def test_add_server_updates_existing(self, index_service):
        async with index_service:
            server_desc1 = McpServerDescription(
                title="Server V1",
                summary="First version",
                capabilities=["cap1"],
                limitations=[]
            )

            server_desc2 = McpServerDescription(
                title="Server V2",
                summary="Second version",
                capabilities=["cap1", "cap2"],
                limitations=["limit1"]
            )

            embedding = [0.1] * 1024

            # Add first version
            await index_service.add_server("my_server", server_desc1, embedding, 3)

            # Update with second version
            await index_service.add_server("my_server", server_desc2, embedding, 5)

            # Should have the updated version
            result = await index_service.get_server("my_server")
            assert result["title"] == "Server V2"
            assert result["nb_tools"] == 5
            assert len(result["capabilities"]) == 2


class TestAddTool:
    @pytest.mark.asyncio
    async def test_add_tool_basic(self, index_service):
        async with index_service:
            tool_desc = McpServerToolDescription(
                title="Test Tool",
                summary="A test tool",
                utterances=["use tool", "run tool"]
            )
            embedding = [0.2] * 1024
            schema = {"type": "object", "properties": {}}

            await index_service.add_tool(
                server_name="test_server",
                tool_name="test_tool",
                tool_description="Does testing",
                tool_schema=schema,
                embedding=embedding,
                enhanced_tool=tool_desc
            )

            # Verify tool was added
            result = await index_service.get_tool("test_server", "test_tool")
            assert result is not None
            assert result["type"] == "tool"
            assert result["server_name"] == "test_server"
            assert result["tool_name"] == "test_tool"
            assert result["title"] == "Test Tool"
            assert len(result["utterances"]) == 2


class TestGetServer:
    @pytest.mark.asyncio
    async def test_get_server_exists(self, index_service):
        async with index_service:
            server_desc = McpServerDescription(
                title="My Server",
                summary="Summary",
                capabilities=["cap1"],
                limitations=[]
            )
            await index_service.add_server("my_server", server_desc, [0.1] * 1024, 2)

            result = await index_service.get_server("my_server")
            assert result is not None
            assert result["server_name"] == "my_server"

    @pytest.mark.asyncio
    async def test_get_server_not_exists(self, index_service):
        async with index_service:
            result = await index_service.get_server("nonexistent_server")
            assert result is None


class TestGetTool:
    @pytest.mark.asyncio
    async def test_get_tool_exists(self, index_service):
        async with index_service:
            tool_desc = McpServerToolDescription(
                title="Tool",
                summary="Summary",
                utterances=["use"]
            )
            await index_service.add_tool(
                "server1", "tool1", "desc", {}, [0.1] * 1024, tool_desc
            )

            result = await index_service.get_tool("server1", "tool1")
            assert result is not None
            assert result["tool_name"] == "tool1"

    @pytest.mark.asyncio
    async def test_get_tool_not_exists(self, index_service):
        async with index_service:
            result = await index_service.get_tool("server1", "nonexistent_tool")
            assert result is None


class TestDeleteServer:
    @pytest.mark.asyncio
    async def test_delete_server_without_tools(self, index_service):
        async with index_service:
            server_desc = McpServerDescription(
                title="Server",
                summary="Summary",
                capabilities=[],
                limitations=[]
            )
            await index_service.add_server("server1", server_desc, [0.1] * 1024, 0)

            result = await index_service.delete_server("server1")
            assert result is not None
            assert result["server_name"] == "server1"

            # Verify deleted
            check = await index_service.get_server("server1")
            assert check is None

    @pytest.mark.asyncio
    async def test_delete_server_with_tools(self, index_service):
        async with index_service:
            # Add server
            server_desc = McpServerDescription(
                title="Server",
                summary="Summary",
                capabilities=[],
                limitations=[]
            )
            await index_service.add_server("server1", server_desc, [0.1] * 1024, 2)

            # Add tools
            tool_desc = McpServerToolDescription(
                title="Tool",
                summary="Summary",
                utterances=["use"]
            )
            await index_service.add_tool("server1", "tool1", "desc", {}, [0.2] * 1024, tool_desc)
            await index_service.add_tool("server1", "tool2", "desc", {}, [0.3] * 1024, tool_desc)

            # Delete server (should delete tools too)
            result = await index_service.delete_server("server1")
            assert result["server_name"] == "server1"

            # Verify server deleted
            check_server = await index_service.get_server("server1")
            assert check_server is None

            # Verify tools deleted
            check_tool1 = await index_service.get_tool("server1", "tool1")
            check_tool2 = await index_service.get_tool("server1", "tool2")
            assert check_tool1 is None
            assert check_tool2 is None


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_basic(self, index_service):
        async with index_service:
            # Add some tools
            tool_desc = McpServerToolDescription(
                title="Tool",
                summary="Summary",
                utterances=["use"]
            )
            await index_service.add_tool("server1", "tool1", "desc", {}, [0.9] * 1024, tool_desc)
            await index_service.add_tool("server1", "tool2", "desc", {}, [0.5] * 1024, tool_desc)

            # Search with similar embedding
            results = await index_service.search([0.9] * 1024, top_k=5)

            assert len(results) >= 1
            assert all("score" in r for r in results)
            assert all("payload" in r for r in results)

    @pytest.mark.asyncio
    async def test_search_with_server_filter(self, index_service):
        async with index_service:
            tool_desc = McpServerToolDescription(
                title="Tool",
                summary="Summary",
                utterances=["use"]
            )
            await index_service.add_tool("server1", "tool1", "desc", {}, [0.9] * 1024, tool_desc)
            await index_service.add_tool("server2", "tool2", "desc", {}, [0.9] * 1024, tool_desc)

            # Search only server1
            results = await index_service.search(
                [0.9] * 1024,
                top_k=10,
                server_names=["server1"]
            )

            assert all(r["payload"]["server_name"] == "server1" for r in results)

    @pytest.mark.asyncio
    async def test_search_with_scope_filter(self, index_service):
        async with index_service:
            # Add server and tool
            server_desc = McpServerDescription(
                title="Server",
                summary="Summary",
                capabilities=[],
                limitations=[]
            )
            tool_desc = McpServerToolDescription(
                title="Tool",
                summary="Summary",
                utterances=["use"]
            )

            await index_service.add_server("server1", server_desc, [0.9] * 1024, 1)
            await index_service.add_tool("server1", "tool1", "desc", {}, [0.9] * 1024, tool_desc)

            # Search only tools
            results = await index_service.search([0.9] * 1024, top_k=10, scope=["tool"])

            assert all(r["payload"]["type"] == "tool" for r in results)


class TestListServers:
    @pytest.mark.asyncio
    async def test_list_servers_empty(self, index_service):
        async with index_service:
            results, next_id = await index_service.list_servers()
            assert results == []
            assert next_id is None

    @pytest.mark.asyncio
    async def test_list_servers_basic(self, index_service):
        async with index_service:
            server_desc = McpServerDescription(
                title="Server",
                summary="Summary",
                capabilities=[],
                limitations=[]
            )

            await index_service.add_server("server1", server_desc, [0.1] * 1024, 0)
            await index_service.add_server("server2", server_desc, [0.2] * 1024, 0)

            results, next_id = await index_service.list_servers()

            assert len(results) == 2
            server_names = [r["server_name"] for r in results]
            assert "server1" in server_names
            assert "server2" in server_names

    @pytest.mark.asyncio
    async def test_list_servers_with_ignore(self, index_service):
        async with index_service:
            server_desc = McpServerDescription(
                title="Server",
                summary="Summary",
                capabilities=[],
                limitations=[]
            )

            await index_service.add_server("server1", server_desc, [0.1] * 1024, 0)
            await index_service.add_server("server2", server_desc, [0.2] * 1024, 0)
            await index_service.add_server("server3", server_desc, [0.3] * 1024, 0)

            results, next_id = await index_service.list_servers(ignore_servers=["server2"])

            assert len(results) == 2
            server_names = [r["server_name"] for r in results]
            assert "server1" in server_names
            assert "server3" in server_names
            assert "server2" not in server_names


class TestListTools:
    @pytest.mark.asyncio
    async def test_list_tools_empty(self, index_service):
        async with index_service:
            results, next_id = await index_service.list_tools("server1")
            assert results == []

    @pytest.mark.asyncio
    async def test_list_tools_basic(self, index_service):
        async with index_service:
            tool_desc = McpServerToolDescription(
                title="Tool",
                summary="Summary",
                utterances=["use"]
            )

            await index_service.add_tool("server1", "tool1", "desc", {}, [0.1] * 1024, tool_desc)
            await index_service.add_tool("server1", "tool2", "desc", {}, [0.2] * 1024, tool_desc)
            await index_service.add_tool("server2", "tool3", "desc", {}, [0.3] * 1024, tool_desc)

            results, next_id = await index_service.list_tools("server1")

            assert len(results) == 2
            tool_names = [r["tool_name"] for r in results]
            assert "tool1" in tool_names
            assert "tool2" in tool_names
            assert "tool3" not in tool_names


class TestNbServers:
    @pytest.mark.asyncio
    async def test_nb_servers_empty(self, index_service):
        async with index_service:
            count = await index_service.nb_servers()
            assert count == 0

    @pytest.mark.asyncio
    async def test_nb_servers_basic(self, index_service):
        async with index_service:
            server_desc = McpServerDescription(
                title="Server",
                summary="Summary",
                capabilities=[],
                limitations=[]
            )

            await index_service.add_server("server1", server_desc, [0.1] * 1024, 0)
            await index_service.add_server("server2", server_desc, [0.2] * 1024, 0)
            await index_service.add_server("server3", server_desc, [0.3] * 1024, 0)

            count = await index_service.nb_servers()
            assert count == 3

    @pytest.mark.asyncio
    async def test_nb_servers_with_ignore(self, index_service):
        async with index_service:
            server_desc = McpServerDescription(
                title="Server",
                summary="Summary",
                capabilities=[],
                limitations=[]
            )

            await index_service.add_server("server1", server_desc, [0.1] * 1024, 0)
            await index_service.add_server("server2", server_desc, [0.2] * 1024, 0)
            await index_service.add_server("server3", server_desc, [0.3] * 1024, 0)

            count = await index_service.nb_servers(ignore_servers=["server1", "server3"])
            assert count == 1


class TestNbTools:
    @pytest.mark.asyncio
    async def test_nb_tools_empty(self, index_service):
        async with index_service:
            count = await index_service.nb_tools()
            assert count == 0

    @pytest.mark.asyncio
    async def test_nb_tools_basic(self, index_service):
        async with index_service:
            tool_desc = McpServerToolDescription(
                title="Tool",
                summary="Summary",
                utterances=["use"]
            )

            await index_service.add_tool("server1", "tool1", "desc", {}, [0.1] * 1024, tool_desc)
            await index_service.add_tool("server1", "tool2", "desc", {}, [0.2] * 1024, tool_desc)
            await index_service.add_tool("server2", "tool3", "desc", {}, [0.3] * 1024, tool_desc)

            count = await index_service.nb_tools()
            assert count == 3

    @pytest.mark.asyncio
    async def test_nb_tools_with_ignore(self, index_service):
        async with index_service:
            tool_desc = McpServerToolDescription(
                title="Tool",
                summary="Summary",
                utterances=["use"]
            )

            await index_service.add_tool("server1", "tool1", "desc", {}, [0.1] * 1024, tool_desc)
            await index_service.add_tool("server2", "tool2", "desc", {}, [0.2] * 1024, tool_desc)
            await index_service.add_tool("server3", "tool3", "desc", {}, [0.3] * 1024, tool_desc)

            count = await index_service.nb_tools(ignore_servers=["server1"])
            assert count == 2
