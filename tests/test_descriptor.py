import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.omnimcp.services.descriptor import DescriptorService
from src.omnimcp.types import McpServerDescription, McpServerToolDescription


@pytest.fixture
def descriptor_service():
    return DescriptorService(
        openai_api_key="test-api-key",
        openai_model_name="gpt-4o-mini"
    )


class TestDescriptorServiceInit:
    def test_initialization(self, descriptor_service):
        assert descriptor_service.api_key == "test-api-key"
        assert descriptor_service.openai_model_name == "gpt-4o-mini"


class TestDescriptorServiceContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_entry(self, descriptor_service):
        async with descriptor_service as service:
            assert service.client is not None
            assert hasattr(service.client, 'chat')


class TestEnhanceQueryWithLLM:
    @pytest.mark.asyncio
    async def test_enhance_query_basic(self, descriptor_service):
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Enhanced query for file reading operations"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        async with descriptor_service:
            with patch.object(
                descriptor_service.client.chat.completions,
                'create',
                new_callable=AsyncMock,
                return_value=mock_response
            ):
                result = await descriptor_service.enhance_query_with_llm("read file")

                assert result == "Enhanced query for file reading operations"
                assert descriptor_service.client.chat.completions.create.call_count == 1

                call_args = descriptor_service.client.chat.completions.create.call_args
                assert call_args.kwargs['model'] == "gpt-4o-mini"
                assert call_args.kwargs['max_tokens'] == 384
                assert len(call_args.kwargs['messages']) == 1
                assert 'read file' in call_args.kwargs['messages'][0]['content']

    @pytest.mark.asyncio
    async def test_enhance_query_strips_whitespace(self, descriptor_service):
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "  Enhanced query with whitespace  \n"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        async with descriptor_service:
            with patch.object(
                descriptor_service.client.chat.completions,
                'create',
                new_callable=AsyncMock,
                return_value=mock_response
            ):
                result = await descriptor_service.enhance_query_with_llm("test query")

                assert result == "Enhanced query with whitespace"
                assert not result.startswith(" ")
                assert not result.endswith(" ")

    @pytest.mark.asyncio
    async def test_enhance_query_retry_on_connection_error(self, descriptor_service):
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Success after retry"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        async with descriptor_service:
            with patch.object(
                descriptor_service.client.chat.completions,
                'create',
                new_callable=AsyncMock,
                side_effect=[ConnectionError("Network issue"), mock_response]
            ):
                result = await descriptor_service.enhance_query_with_llm("query")

                assert result == "Success after retry"
                assert descriptor_service.client.chat.completions.create.call_count == 2


class TestDescribeMcpServerTool:
    @pytest.mark.asyncio
    async def test_describe_tool_basic(self, descriptor_service):
        mock_tool_desc = McpServerToolDescription(
            title="File Reader Tool",
            summary="Reads content from files on the filesystem",
            utterances=["read file", "get file content", "show file"]
        )

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.parsed = mock_tool_desc
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        async with descriptor_service:
            with patch.object(
                descriptor_service.client.beta.chat.completions,
                'parse',
                new_callable=AsyncMock,
                return_value=mock_response
            ):
                tool_schema = {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    }
                }

                result = await descriptor_service.describe_mcp_server_tool(
                    tool_name="read_file",
                    tool_description="Reads a file from disk",
                    tool_schema=tool_schema,
                    server_name="filesystem"
                )

                assert isinstance(result, McpServerToolDescription)
                assert result.title == "File Reader Tool"
                assert result.summary == "Reads content from files on the filesystem"
                assert len(result.utterances) == 3
                assert "read file" in result.utterances

                call_args = descriptor_service.client.beta.chat.completions.parse.call_args
                assert call_args.kwargs['model'] == "gpt-4o-mini"
                assert call_args.kwargs['max_tokens'] == 1024
                assert call_args.kwargs['response_format'] == McpServerToolDescription

    @pytest.mark.asyncio
    async def test_describe_tool_with_complex_schema(self, descriptor_service):
        mock_tool_desc = McpServerToolDescription(
            title="Search Tool",
            summary="Performs web searches with filters",
            utterances=["search web", "find online", "google search"]
        )

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.parsed = mock_tool_desc
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        async with descriptor_service:
            with patch.object(
                descriptor_service.client.beta.chat.completions,
                'parse',
                new_callable=AsyncMock,
                return_value=mock_response
            ):
                tool_schema = {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer"},
                        "filters": {
                            "type": "object",
                            "properties": {
                                "date_range": {"type": "string"}
                            }
                        }
                    },
                    "required": ["query"]
                }

                result = await descriptor_service.describe_mcp_server_tool(
                    tool_name="web_search",
                    tool_description="Searches the web",
                    tool_schema=tool_schema,
                    server_name="search_api"
                )

                assert result.title == "Search Tool"
                call_args = descriptor_service.client.beta.chat.completions.parse.call_args
                assert "web_search" in str(call_args.kwargs['messages'])
                assert "search_api" in str(call_args.kwargs['messages'])


class TestDescribeMcpServer:
    @pytest.mark.asyncio
    async def test_describe_server_basic(self, descriptor_service):
        enhanced_tools = [
            McpServerToolDescription(
                title="Read File",
                summary="Reads files",
                utterances=["read", "get file"]
            ),
            McpServerToolDescription(
                title="Write File",
                summary="Writes files",
                utterances=["write", "save file"]
            )
        ]

        mock_server_desc = McpServerDescription(
            title="Filesystem MCP Server",
            summary="Provides file system operations",
            capabilities=["Read files", "Write files", "List directories"],
            limitations=["No network access", "Limited to local filesystem"]
        )

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.parsed = mock_server_desc
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        async with descriptor_service:
            with patch.object(
                descriptor_service.client.chat.completions,
                'parse',
                new_callable=AsyncMock,
                return_value=mock_response
            ):
                result = await descriptor_service.describe_mcp_server(
                    server_name="filesystem",
                    enhanced_tools=enhanced_tools
                )

                assert isinstance(result, McpServerDescription)
                assert result.title == "Filesystem MCP Server"
                assert result.summary == "Provides file system operations"
                assert len(result.capabilities) == 3
                assert len(result.limitations) == 2
                assert "Read files" in result.capabilities

                call_args = descriptor_service.client.chat.completions.parse.call_args
                assert call_args.kwargs['model'] == "gpt-4o-mini"
                assert call_args.kwargs['max_tokens'] == 2048
                assert call_args.kwargs['response_format'] == McpServerDescription

    @pytest.mark.asyncio
    async def test_describe_server_with_single_tool(self, descriptor_service):
        enhanced_tools = [
            McpServerToolDescription(
                title="Echo Tool",
                summary="Returns input as output",
                utterances=["echo", "repeat"]
            )
        ]

        mock_server_desc = McpServerDescription(
            title="Echo Server",
            summary="Simple echo functionality",
            capabilities=["Echo text"],
            limitations=["Only echoes text"]
        )

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.parsed = mock_server_desc
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        async with descriptor_service:
            with patch.object(
                descriptor_service.client.chat.completions,
                'parse',
                new_callable=AsyncMock,
                return_value=mock_response
            ):
                result = await descriptor_service.describe_mcp_server(
                    server_name="echo_server",
                    enhanced_tools=enhanced_tools
                )

                assert result.title == "Echo Server"
                call_args = descriptor_service.client.chat.completions.parse.call_args
                messages = call_args.kwargs['messages']
                assert len(messages) == 2
                assert messages[0]['role'] == 'system'
                assert messages[1]['role'] == 'user'

    @pytest.mark.asyncio
    async def test_describe_server_includes_all_tools(self, descriptor_service):
        enhanced_tools = [
            McpServerToolDescription(
                title=f"Tool {i}",
                summary=f"Does task {i}",
                utterances=[f"task{i}"]
            )
            for i in range(5)
        ]

        mock_server_desc = McpServerDescription(
            title="Multi-Tool Server",
            summary="Server with multiple tools",
            capabilities=["Multiple operations"],
            limitations=["Rate limited"]
        )

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.parsed = mock_server_desc
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        async with descriptor_service:
            with patch.object(
                descriptor_service.client.chat.completions,
                'parse',
                new_callable=AsyncMock,
                return_value=mock_response
            ):
                result = await descriptor_service.describe_mcp_server(
                    server_name="multi_tool",
                    enhanced_tools=enhanced_tools
                )

                assert result.title == "Multi-Tool Server"
                call_args = descriptor_service.client.chat.completions.parse.call_args
                user_message = call_args.kwargs['messages'][1]
                # Should have system prompt text + 5 tool descriptions
                assert len(user_message['content']) == 6
