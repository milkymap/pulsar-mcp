<div align="center">

# Pulsar MCP

**Semantic router for MCP ecosystems**

*Discover and execute tools across multiple MCP servers without context bloat*

[![PyPI](https://img.shields.io/pypi/v/pulsar-mcp.svg)](https://pypi.org/project/pulsar-mcp)
[![License](https://img.shields.io/github/license/milkymap/pulsar-mcp.svg)](https://github.com/milkymap/pulsar-mcp/blob/main/LICENSE)
[![Tests](https://github.com/milkymap/pulsar-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/milkymap/pulsar-mcp/actions)

</div>

---

![alt text](pulsar-mcp.jpeg)

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

### Why this matters

**Context bloat kills performance.** When tool definitions consume 50-100K tokens, you're left with limited space for actual conversation, documents, and reasoning. The model spends attention on tool schemas instead of your task.

**More tools = more hallucinations.** With 50+ similar tools (like `notification-send-user` vs `notification-send-channel`), models pick wrong tools and hallucinate parameters. Tool selection accuracy drops as the toolset grows.

**Dynamic tool loading breaks caching.** Loading tools on-demand during inference seems smart, but it invalidates prompt caches. Every new tool added mid-conversation means reprocessing the entire context. Your "optimization" becomes a performance tax.

**Tool results bloat context too.** A single file read can return 50K tokens. An image is 1K+ tokens base64-encoded. These pile up in conversation history, pushing out earlier context.

## The Solution

Pulsar exposes a **single `semantic_router` tool** as the only entry point to your entire MCP ecosystem. The LLM never sees individual tool definitions—just one unified interface.

```
Traditional: 58 tools → 55K tokens in tool definitions
Pulsar:      1 tool   → ~500 tokens (semantic_router)
```

**How it works:**

1. **Semantic search** → Find relevant tools by intent, not name. Tools are pre-indexed with embeddings, searched at runtime, returned as text results (not tool definitions)
2. **Lazy server loading** → Servers start only when needed, shutdown when done
3. **Progressive schema loading** → Full JSON schema fetched only before execution, returned as text in conversation
4. **Content offloading** → Large results chunked, images described, stored for retrieval

**Key insight:** Tool schemas appear in conversation text, not in tool definitions. This means:
- Prompt caching stays intact (tool definition never changes)
- Only relevant schemas enter context (via search results)
- No hallucination from similar tool names (model sees 3-5 tools, not 50+)

From ~60K tokens to ~3K. Access to everything, cost of almost nothing.

## Real-World Example

**Multi-server orchestration in action:**

Claude Code generated a video using Pulsar to coordinate multiple MCP servers.

🎥 https://github.com/user-attachments/assets/c8715bdd-815a-4f92-9e8f-95043450474b

**The process:**

1. **Exa (background mode)** - Parallel web searches to gather latest news
2. **Modal Sandbox** - Computed and generated video from news data
3. **Filesystem** - Retrieved the video file from Modal's output
4. **ffmpeg** - Transformed video to GIF format

**The workflow:**
```
search_tools("web search news")
  → execute_tool(exa, search, in_background=True) × 3 parallel calls
  → poll_task_result() → aggregate results
  → execute_tool(modal-sandbox, generate_video, data)
  → execute_tool(filesystem, read_file, video_path)
  → execute_tool(modal-sandbox, ffmpeg_convert, video_to_gif)
```

**What this demonstrates:**
- **Semantic discovery** - Finding the right tools across servers without knowing their exact names
- **Background execution** - Parallel Exa searches without blocking the conversation
- **Cross-server coordination** - Modal → Filesystem → Modal pipeline with automatic state management
- **Single interface** - All operations through one `semantic_router` tool

Without Pulsar: 50+ tool definitions, complex orchestration, context overflow.
With Pulsar: Discover → Execute → Coordinate. Seamlessly.

## Installation

```bash
uv pip install pulsar-mcp
```

## Configuration

### Environment Variables

Pulsar requires several environment variables to operate. You must configure these before running `index` or `serve` commands.

**Required variables:**

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for embeddings and descriptions | `sk-proj-...` |
| `QDRANT_STORAGE_PATH` | Path to Qdrant vector database storage | `/home/user/qdrant_data` |
| `CONTENT_STORAGE_PATH` | Path for storing offloaded content (large results, images) | `/home/user/content_storage` |

**Optional variables (with defaults):**

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL_NAME` | `text-embedding-3-small` | OpenAI embedding model |
| `DESCRIPTOR_MODEL_NAME` | `gpt-4.1-mini` | Model for generating tool descriptions |
| `VISION_MODEL_NAME` | `gpt-4.1-mini` | Model for describing images |
| `MAX_RESULT_TOKENS` | `5000` | Chunk threshold for large results |
| `DESCRIBE_IMAGES` | `true` | Use vision to describe images |
| `DIMENSIONS` | `1024` | Embedding dimensions |

**Setup methods:**

**Option 1: Export directly**
```bash
export OPENAI_API_KEY="sk-proj-..."
export QDRANT_STORAGE_PATH="/home/user/qdrant_data"
export CONTENT_STORAGE_PATH="/home/user/content_storage"
```

**Option 2: Create a `.env` file**
```bash
# .env
OPENAI_API_KEY=sk-proj-...
QDRANT_STORAGE_PATH=/home/user/qdrant_data
CONTENT_STORAGE_PATH=/home/user/content_storage
```

Then source it before running commands:
```bash
source .env  # or use: export $(cat .env | xargs)
uvx pulsar-mcp index --config mcp-servers.json
```

**Note:** For stdio transport, environment variables must also be included in your MCP client config (see [stdio transport section](#stdio-transport) below).

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

**3. Index your servers** (recommended before serving):

```bash
uvx pulsar-mcp index --config mcp-servers.json
```

**4. Run the server**:

```bash
# Default: HTTP transport (recommended)
uvx pulsar-mcp serve --config mcp-servers.json --transport http --host 0.0.0.0 --port 8000

# stdio transport (for local MCP clients - requires pre-indexing)
uvx pulsar-mcp serve --config mcp-servers.json --transport stdio
```

## Transport Modes

Pulsar supports two transport protocols, each optimized for different deployment scenarios:

### HTTP Transport (Default - Recommended)

Best for most use cases: remote access, web integrations, or when using with `mcp-remote` or `mcp-proxy`.

```bash
uvx pulsar-mcp serve --config mcp-servers.json --transport http --host 0.0.0.0 --port 8000
```

**Use cases:**
- **Remote access** - Serve Pulsar on a server, connect from anywhere
- **Multiple clients** - Share one Pulsar instance across multiple agents
- **Web integrations** - REST API access to your MCP ecosystem
- **mcp-remote/mcp-proxy** - Expose Pulsar through MCP proxy layers

**Example with [mcp-remote](https://www.npmjs.com/package/mcp-remote)**:
```bash
npm install mcp-remote
```

```json
{
  "mcpServers": {
    "pulsar-remote": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://your-server:port/mcp"]
    }
  }
}
```

**HTTP mode advantages:**
- Indexing happens once on server startup
- Multiple clients share the same indexed data

### stdio Transport

Best for local MCP clients that communicate via standard input/output (Claude Desktop, Cline, etc.).

**⚠️ IMPORTANT: You MUST run `uvx pulsar-mcp index` before using stdio mode to avoid slow startup times.**

```bash
uvx pulsar-mcp serve --config mcp-servers.json --transport stdio
```

**Recommended workflow:**
1. **Index first** - Run `pulsar-mcp index` before adding to your MCP client config
2. **Then mount** - Add Pulsar to your client's MCP configuration
3. **Start serving** - Client launches Pulsar automatically via stdio

**Example client config** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "pulsar": {
      "command": "uvx",
      "args": ["pulsar-mcp", "serve", "--config", "/path/to/mcp-servers.json", "--transport", "stdio"],
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "QDRANT_STORAGE_PATH": "/path/to/qdrant",
        "CONTENT_STORAGE_PATH": "/path/to/content"
        // add other env keys
      }
    }
  }
}
```

**Why index before mounting?** Indexing can take time with many servers. Pre-indexing ensures instant startup when your MCP client launches Pulsar.

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
  "command": "npx|uvx|docker",
  "args": ["arg0", "arg1", "...", "argN"],
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

## Related Research

Pulsar MCP builds on emerging research in scalable tool selection for LLM agents:

### ScaleMCP: Dynamic and Auto-Synchronizing Model Context Protocol Tools

[Lumer et al. (2025)](https://doi.org/10.48550/arXiv.2505.06416) introduce **ScaleMCP**, addressing similar challenges in MCP tool selection at scale. Their approach emphasizes:

- **Dynamic tool retrieval** - Giving agents autonomy to discover and add tools during multi-turn interactions
- **Auto-synchronizing storage** - Using MCP servers as the single source of truth via CRUD operations
- **Tool Document Weighted Average (TDWA)** - Novel embedding strategy that selectively emphasizes critical tool document components

Their evaluation across 5,000 financial metric servers demonstrates substantial improvements in tool retrieval and agent invocation performance, validating the importance of semantic search in MCP ecosystems.

**Key insight**: Both Pulsar and ScaleMCP recognize that traditional monolithic tool repositories don't scale. The future requires dynamic, semantic-first approaches to tool discovery.

### Anthropic's Advanced Tool Use

[Anthropic's Tool Search feature](https://www.anthropic.com/engineering/advanced-tool-use) (2025) introduces three capabilities that align with Pulsar's architecture:

- **Tool Search Tool** - Discover thousands of tools without consuming context window
- **Programmatic Tool Calling** - Invoke tools in code execution environments to reduce context impact
- **Tool Use Examples** - Learn correct usage patterns beyond JSON schema definitions

**Quote from Anthropic**: *"Tool results and definitions can sometimes consume 50,000+ tokens before an agent reads a request. Agents should discover and load tools on-demand, keeping only what's relevant for the current task."*

This mirrors Pulsar's core philosophy: expose minimal interface upfront (single `semantic_router` tool), discover tools semantically, load schemas progressively.

### Convergent Evolution

These independent efforts converge on similar principles:

1. **Semantic discovery** over exhaustive enumeration
2. **Progressive loading** over upfront tool definitions
3. **Agent autonomy** to query and re-query tool repositories
4. **Context efficiency** as a first-class design constraint

Pulsar MCP implements these principles through semantic routing, lazy server loading, and content offloading—making large-scale MCP ecosystems practical today.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<div align="center">

*Built after research on scaling MCP ecosystems*

</div>
