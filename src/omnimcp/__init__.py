import asyncio
import click

from omnimcp.log import logger
from omnimcp.settings import ApiKeysSettings
from omnimcp.mcp_engine import MCPEngine
from omnimcp.mcp_server import MCPServer
from omnimcp.utilities import load_mcp_config
from dotenv import load_dotenv


@click.group()
def cli():
    """OmniMCP - Semantic router for MCP ecosystems"""
    pass


@cli.command()
@click.option(
    '--config',
    type=click.Path(exists=True, dir_okay=False, readable=True),
    required=True,
    help='Path to the MCP server configuration file.'
)
def index(config: str) -> None:
    """Index MCP servers for semantic search."""
    load_dotenv()
    api_keys_settings = ApiKeysSettings()
    mcp_config = load_mcp_config(config)

    async def async_index():
        logger.info("Starting indexing...")
        async with MCPEngine(
            api_keys_settings=api_keys_settings,
            mcp_config=mcp_config,
            mode="index"
        ) as mcp_engine:
            await mcp_engine.index_mcp_servers()
        logger.info("Indexing completed.")

    asyncio.run(async_index())


@cli.command()
@click.option(
    '--config',
    type=click.Path(exists=True, dir_okay=False, readable=True),
    required=True,
    help='Path to the MCP server configuration file.'
)
@click.option("--transport", type=click.Choice(["stdio", "http"]), default="http", help="Transport method.")
@click.option("--host", type=str, default="localhost", help="Host for HTTP transport.")
@click.option("--port", type=int, default=8000, help="Port for HTTP transport.")
def serve(config: str, transport: str, host: str, port: int) -> None:
    """Index (if needed) and start the MCP server."""
    load_dotenv()
    api_keys_settings = ApiKeysSettings()
    mcp_config = load_mcp_config(config)

    async def async_serve():
        async with MCPEngine(
            api_keys_settings=api_keys_settings,
            mcp_config=mcp_config,
            mode="serve"
        ) as mcp_engine:
            await mcp_engine.index_mcp_servers()
            mcp_server = MCPServer(mcp_engine=mcp_engine)
            await mcp_server.run_server(
                transport=transport,
                host=host,
                port=port
            )

    asyncio.run(async_serve())




def main():
    cli()
