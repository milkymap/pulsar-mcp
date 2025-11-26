import pytest
from src.omnimcp.types import (
    McpStartupConfig,
    McpServersConfig,
    McpServerDescription,
    McpServerToolDescription,
)


class TestMcpStartupConfig:
    def test_minimal_config(self):
        config = McpStartupConfig(command="npx")
        assert config.command == "npx"
        assert config.args == []
        assert config.env == {}
        assert config.timeout == 30.0
        assert config.overwrite is False
        assert config.ignore is False
        assert config.hints is None
        assert config.blocked_tools is None

    def test_full_config(self):
        config = McpStartupConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
            env={"HOME": "/home/user"},
            timeout=60.0,
            overwrite=True,
            ignore=False,
            hints=["file operations", "read/write"],
            blocked_tools=["delete_file", "execute_command"]
        )
        assert config.command == "npx"
        assert config.args == ["-y", "@modelcontextprotocol/server-filesystem"]
        assert config.env == {"HOME": "/home/user"}
        assert config.timeout == 60.0
        assert config.overwrite is True
        assert config.hints == ["file operations", "read/write"]
        assert config.blocked_tools == ["delete_file", "execute_command"]

    def test_blocked_tools_list(self):
        config = McpStartupConfig(
            command="test",
            blocked_tools=["tool1", "tool2", "tool3"]
        )
        assert "tool1" in config.blocked_tools
        assert "tool2" in config.blocked_tools
        assert "tool4" not in config.blocked_tools

    def test_ignore_flag(self):
        config = McpStartupConfig(command="test", ignore=True)
        assert config.ignore is True

    def test_overwrite_flag(self):
        config = McpStartupConfig(command="test", overwrite=True)
        assert config.overwrite is True


class TestMcpServersConfig:
    def test_empty_config(self):
        config = McpServersConfig(mcpServers={})
        assert config.mcpServers == {}

    def test_single_server(self):
        config = McpServersConfig(
            mcpServers={
                "filesystem": McpStartupConfig(command="npx", args=["-y", "fs-server"])
            }
        )
        assert "filesystem" in config.mcpServers
        assert config.mcpServers["filesystem"].command == "npx"

    def test_multiple_servers(self):
        config = McpServersConfig(
            mcpServers={
                "filesystem": McpStartupConfig(command="npx"),
                "github": McpStartupConfig(command="uvx", blocked_tools=["delete_repo"]),
                "ignored": McpStartupConfig(command="test", ignore=True)
            }
        )
        assert len(config.mcpServers) == 3
        assert config.mcpServers["github"].blocked_tools == ["delete_repo"]
        assert config.mcpServers["ignored"].ignore is True


class TestMcpServerDescription:
    def test_description(self):
        desc = McpServerDescription(
            title="Filesystem Server",
            summary="Provides file system operations",
            capabilities=["read files", "write files", "list directories"],
            limitations=["no network access", "sandboxed paths"]
        )
        assert desc.title == "Filesystem Server"
        assert len(desc.capabilities) == 3
        assert len(desc.limitations) == 2


class TestMcpServerToolDescription:
    def test_tool_description(self):
        desc = McpServerToolDescription(
            title="Read File Tool",
            summary="Reads content from a file",
            utterances=["read the file", "get file content", "show me the file"]
        )
        assert desc.title == "Read File Tool"
        assert len(desc.utterances) == 3
