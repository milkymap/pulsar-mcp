import asyncio
import click

from omnimcp.log import logger
from omnimcp.settings import ApiKeysSettings
from omnimcp.mcp_engine import MCPEngine
from omnimcp.mcp_server import MCPServer
from omnimcp.utilities import load_mcp_config
from dotenv import load_dotenv


def build_settings(**cli_overrides) -> ApiKeysSettings:
    """Build ApiKeysSettings with CLI overrides (non-None values take precedence)."""
    overrides = {k: v for k, v in cli_overrides.items() if v is not None}
    return ApiKeysSettings(**overrides)


@click.group()
def cli():
    """OmniMCP - Semantic router for MCP ecosystems"""
    pass


@cli.command()
@click.option('--config-path', 'CONFIG_PATH', type=click.Path(exists=True, dir_okay=False, readable=True), default=None, envvar='CONFIG_PATH', help='Path to the MCP server configuration file.')
@click.option('--openai-api-key', 'OPENAI_API_KEY', type=str, default=None, envvar='OPENAI_API_KEY', help='OpenAI API key.')
@click.option('--qdrant-data-path', 'QDRANT_DATA_PATH', type=str, default=None, envvar='QDRANT_DATA_PATH', help='Path to Qdrant local storage, or ":memory:" for in-memory.')
@click.option('--qdrant-url', 'QDRANT_URL', type=str, default=None, envvar='QDRANT_URL', help='URL for remote Qdrant server (Docker or Cloud).')
@click.option('--qdrant-api-key', 'QDRANT_API_KEY', type=str, default=None, envvar='QDRANT_API_KEY', help='API key for Qdrant Cloud authentication.')
@click.option('--tool-offloaded-data-path', 'TOOL_OFFLOADED_DATA_PATH', type=str, default=None, envvar='TOOL_OFFLOADED_DATA_PATH', help='Path to tool offloaded data storage.')
@click.option('--descriptor-model-name', 'DESCRIPTOR_MODEL_NAME', type=str, default=None, envvar='DESCRIPTOR_MODEL_NAME', help='Model for generating descriptions.')
@click.option('--embedding-model-name', 'EMBEDDING_MODEL_NAME', type=str, default=None, envvar='EMBEDDING_MODEL_NAME', help='Model for embeddings.')
@click.option('--vision-model-name', 'VISION_MODEL_NAME', type=str, default=None, envvar='VISION_MODEL_NAME', help='Model for vision/image description.')
@click.option('--dimensions', 'DIMENSIONS', type=int, default=None, envvar='DIMENSIONS', help='Embedding dimensions.')
@click.option('--index-name', 'INDEX_NAME', type=str, default=None, envvar='INDEX_NAME', help='Name of the vector index.')
@click.option('--max-result-tokens', 'MAX_RESULT_TOKENS', type=int, default=None, envvar='MAX_RESULT_TOKENS', help='Max tokens before chunking results.')
@click.option('--describe-images/--no-describe-images', 'DESCRIBE_IMAGES', default=None, envvar='DESCRIBE_IMAGES', help='Use vision to describe images.')
def index(**kwargs) -> None:
    """Index MCP servers for semantic search."""
    load_dotenv()
    settings = build_settings(**kwargs)
    mcp_config = load_mcp_config(settings.CONFIG_PATH)

    async def async_index():
        logger.info("Starting indexing...")
        async with MCPEngine(
            api_keys_settings=settings,
            mcp_config=mcp_config,
            mode="index"
        ) as mcp_engine:
            await mcp_engine.index_mcp_servers()
        logger.info("Indexing completed.")

    asyncio.run(async_index())


@cli.command()
@click.option('--config-path', 'CONFIG_PATH', type=click.Path(exists=True, dir_okay=False, readable=True), default=None, envvar='CONFIG_PATH', help='Path to the MCP server configuration file.')
@click.option('--transport', 'TRANSPORT', type=click.Choice(["stdio", "http"]), default=None, envvar='TRANSPORT', help='Transport method.')
@click.option('--host', 'HOST', type=str, default=None, envvar='HOST', help='Host for HTTP transport.')
@click.option('--port', 'PORT', type=int, default=None, envvar='PORT', help='Port for HTTP transport.')
@click.option('--openai-api-key', 'OPENAI_API_KEY', type=str, default=None, envvar='OPENAI_API_KEY', help='OpenAI API key.')
@click.option('--qdrant-data-path', 'QDRANT_DATA_PATH', type=str, default=None, envvar='QDRANT_DATA_PATH', help='Path to Qdrant local storage, or ":memory:" for in-memory.')
@click.option('--qdrant-url', 'QDRANT_URL', type=str, default=None, envvar='QDRANT_URL', help='URL for remote Qdrant server (Docker or Cloud).')
@click.option('--qdrant-api-key', 'QDRANT_API_KEY', type=str, default=None, envvar='QDRANT_API_KEY', help='API key for Qdrant Cloud authentication.')
@click.option('--tool-offloaded-data-path', 'TOOL_OFFLOADED_DATA_PATH', type=str, default=None, envvar='TOOL_OFFLOADED_DATA_PATH', help='Path to tool offloaded data storage.')
@click.option('--descriptor-model-name', 'DESCRIPTOR_MODEL_NAME', type=str, default=None, envvar='DESCRIPTOR_MODEL_NAME', help='Model for generating descriptions.')
@click.option('--embedding-model-name', 'EMBEDDING_MODEL_NAME', type=str, default=None, envvar='EMBEDDING_MODEL_NAME', help='Model for embeddings.')
@click.option('--vision-model-name', 'VISION_MODEL_NAME', type=str, default=None, envvar='VISION_MODEL_NAME', help='Model for vision/image description.')
@click.option('--dimensions', 'DIMENSIONS', type=int, default=None, envvar='DIMENSIONS', help='Embedding dimensions.')
@click.option('--index-name', 'INDEX_NAME', type=str, default=None, envvar='INDEX_NAME', help='Name of the vector index.')
@click.option('--max-result-tokens', 'MAX_RESULT_TOKENS', type=int, default=None, envvar='MAX_RESULT_TOKENS', help='Max tokens before chunking results.')
@click.option('--describe-images/--no-describe-images', 'DESCRIBE_IMAGES', default=None, envvar='DESCRIBE_IMAGES', help='Use vision to describe images.')
def serve(**kwargs) -> None:
    """Index (if needed) and start the MCP server."""
    load_dotenv()
    settings = build_settings(**kwargs)
    mcp_config = load_mcp_config(settings.CONFIG_PATH)

    async def async_serve():
        async with MCPEngine(
            api_keys_settings=settings,
            mcp_config=mcp_config,
            mode="serve"
        ) as mcp_engine:
            await mcp_engine.index_mcp_servers()
            mcp_server = MCPServer(mcp_engine=mcp_engine)
            await mcp_server.run_server(
                transport=settings.TRANSPORT,
                host=settings.HOST,
                port=settings.PORT
            )

    asyncio.run(async_serve())




def main():
    cli()
