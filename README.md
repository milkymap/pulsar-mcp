<div align="center">

# Pulsar MCP

**Semantic router for MCP ecosystems**

*Discover and execute tools across multiple servers without context bloat*

[![PyPI](https://img.shields.io/pypi/v/pulsar-mcp.svg)](https://pypi.org/project/pulsar-mcp)
[![License](https://img.shields.io/github/license/milkymap/pulsar-mcp.svg)](https://github.com/milkymap/pulsar-mcp/blob/main/LICENSE)
[![Tests](https://github.com/milkymap/pulsar-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/milkymap/pulsar-mcp/actions)

</div>

---

## The Problem

MCP tool definitions consume tokens fast. A typical setup:

| Server | Tools | Tokens |
|--------|-------|--------|
| GitHub | 35 | ~26K |
| Slack | 11 | ~21K |
| Filesystem | 8 | ~5K |
| Database | 12 | ~8K |

That's **60K+ tokens** before the conversation starts. Add more servers and you're competing with your actual context.

## The Solution

Pulsar loads tools on-demand through semantic search. Instead of stuffing all schemas upfront:

1. **Semantic search** → Find relevant tools by intent, not name
2. **Lazy server loading** → Start servers only when needed
3. **Progressive schema loading** → Fetch full details only before execution
4. **Content offloading** → Chunk large results, describe images, store for retrieval

From ~60K tokens to ~3K. Access to everything, cost of almost nothing.

## Installation

```bash
uv pip install pulsar-mcp
```

## Quick Start

**1. Create your MCP servers config** (`mcp-servers.json`):

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
      "hints": ["file operations", "read write files"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "..."},
      "blocked_tools": ["delete_repository"]
    }
  }
}
```

**2. Set environment variables**:

```bash
export OPENAI_API_KEY="sk-..."
export QDRANT_STORAGE_PATH="/path/to/qdrant"
export CONTENT_STORAGE_PATH="/path/to/content"
```

**3. Index your servers**:

```bash
pulsar-mcp index --config mcp-servers.json
```

**4. Run the server**:

```bash
pulsar-mcp serve --config mcp-servers.json
```

## How It Works

Pulsar exposes a single `semantic_router` tool that acts as a gateway to your entire MCP ecosystem:

```
search_tools("read CSV files and analyze data")
    → Returns: filesystem.read_file, database.query (ranked by relevance)

get_tool_details("filesystem", "read_file")
    → Returns: Full JSON schema with parameters

manage_server("filesystem", "start")
    → Launches the server process

execute_tool("filesystem", "read_file", {"path": "/data/sales.csv"})
    → Returns: File content (chunked if large)
```

### Operations

| Operation | Description |
|-----------|-------------|
| `search_tools` | Semantic search across all indexed tools |
| `get_server_info` | View server capabilities and limitations |
| `list_server_tools` | Browse tools on a specific server |
| `get_tool_details` | Get full schema before execution |
| `manage_server` | Start or shutdown server instances |
| `list_running_servers` | Show active servers |
| `execute_tool` | Run tools with optional background mode |
| `poll_task_result` | Check background task status |
| `get_content` | Retrieve offloaded content by reference |

## Configuration

### Server Options

```json
{
  "command": "npx",
  "args": ["-y", "server-package"],
  "env": {"API_KEY": "..."},
  "timeout": 30.0,
  "hints": ["optional", "discovery hints"],
  "blocked_tools": ["dangerous_tool"],
  "ignore": false,
  "overwrite": false
}
```

| Field | Description |
|-------|-------------|
| `hints` | Help semantic search find this server |
| `blocked_tools` | Tools indexed but blocked at runtime |
| `ignore` | Skip indexing entirely |
| `overwrite` | Re-index even if already indexed |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | required | OpenAI API key |
| `QDRANT_STORAGE_PATH` | required | Qdrant vector storage path |
| `CONTENT_STORAGE_PATH` | required | Offloaded content storage |
| `MAX_RESULT_TOKENS` | 5000 | Chunk threshold for large results |
| `DESCRIBE_IMAGES` | true | Use vision to describe images |
| `EMBEDDING_MODEL_NAME` | text-embedding-3-small | Embedding model |
| `DESCRIPTOR_MODEL_NAME` | gpt-4.1-mini | Description generation model |

## Content Management

Large tool results are automatically handled:

- **Text** > 5000 tokens → Chunked, preview returned with reference ID
- **Images** → Offloaded, described with GPT-4 vision, reference returned
- **Audio** → Offloaded, reference returned

Retrieve full content with `get_content(ref_id, chunk_index)`.

## Background Execution

For long-running tools:

```python
# Queue for background execution
execute_tool("server", "slow_tool", args, in_background=True, priority=1)
# Returns: task_id

# Check status
poll_task_result(task_id)
# Returns: status, result when done
```

## Development

```bash
git clone https://github.com/milkymap/pulsar-mcp.git
cd pulsar-mcp
uv sync
uv run pytest
```

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<div align="center">

*Built after mass research on scaling MCP ecosystems*

</div>
