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

## Architecture: Meta-Tool Pattern

Pulsar uses the **meta-tool pattern**, similar to Claude Code's Agent Skills system. Instead of exposing dozens of individual tools, it exposes a single `semantic_router` meta-tool that acts as a gateway to your entire MCP ecosystem.

### 
![alt text](pulsar_paradigm.jpeg)

### How It Works

**Traditional MCP approach:**
```
tools: [
  {name: "github_create_issue", description: "..."},
  {name: "github_create_pr", description: "..."},
  {name: "filesystem_read", description: "..."},
  // ... 50+ more tools
]
```
❌ Problems: Context bloat, tool hallucination, no caching

**Pulsar's meta-tool approach:**
```json
{
  "tools": [
    {
      "name": "semantic_router",
      "description": "Universal gateway to MCP ecosystem...\n
        OPERATIONS: search_tools, get_server_info, execute_tool...\n
        LIST OF INDEXED SERVERS:\n
        filesystem: 8 tools (file operations, read/write)\n
        github: 35 tools (issues, PRs, repos)\n
        ...",
      "input_schema": {
        "operation": "search_tools | execute_tool | ..."
      }
    }
  ]
}
```
✅ Benefits: Single tool definition, server list in description, dynamic discovery

### Parallel to Claude Skills

Claude Skills and Pulsar share the same architectural insight:

| Aspect | Claude Skills | Pulsar MCP |
|--------|--------------|------------|
| **Meta-tool** | `Skill` tool | `semantic_router` tool |
| **Discovery** | Skill descriptions in tool description | Server list + hints in tool description |
| **Invocation** | `Skill(command="skill-name")` | `semantic_router(operation="execute_tool", server_name=...)` |
| **Context injection** | Skill instructions loaded on invocation | Tool schemas fetched on-demand, returned as text |
| **Cache-friendly** | Tool definition never changes | Tool definition never changes |
| **Dynamic list** | `<available_skills>` section | `LIST OF INDEXED SERVERS` section |
| **Behavioral hints** | Skill descriptions guide LLM | Server `hints` field guides LLM |

**Key insight:** Both systems inject instructions through **prompt expansion** rather than traditional function calling. The tool description becomes a dynamic directory that the LLM reads and reasons about, while actual execution details are loaded lazily.

**Example of behavioral guidance:**

Claude Skills:
```
<available_skills>
  skill-creator: "When user wants to create a new skill..."
  internal-comms: "When user wants to write internal communications..."
</available_skills>
```

Pulsar `hints`:
```json
{
  "elevenlabs": {
    "hints": [
      "When the user requests audio generation (speech or music), always execute in background mode",
      "Proactively offer to play audio using the ElevenLabs tool when contextually relevant"
    ]
  }
}
```

Both inject **behavioral instructions** that shape how the LLM uses the tools, not just what they do.

## Real-World Example

**Multi-server orchestration in action:**

Claude Code generated a video using Pulsar to coordinate multiple MCP servers.
![world_news_2025](https://github.com/user-attachments/assets/1f540910-3570-427a-881b-d769cb69abdf)
🎥 (high quality) https://github.com/user-attachments/assets/c8715bdd-815a-4f92-9e8f-95043450474b

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
uv pip install pulsar-mcp // or uv add pulsar-mcp 
```

## Configuration

### Environment Variables

Pulsar requires several environment variables to operate. You must configure these before running `index` or `serve` commands.

**Required variables:**

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for embeddings and descriptions | `sk-proj-...` |
| `QDRANT_STORAGE_PATH` | Path to local directory for embedded Qdrant vector database (no separate server needed) | `/path/to/qdrant_data` |
| `CONTENT_STORAGE_PATH` | Path for storing offloaded content (large results, images) | `/path/to/content_storage` |

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
export QDRANT_STORAGE_PATH="/path/to/qdrant_data"
export CONTENT_STORAGE_PATH="/path/to/content_storage"
```

**Option 2: Create a `.env` file**
```bash
# .env
OPENAI_API_KEY=sk-proj-...
QDRANT_STORAGE_PATH=/path/to/qdrant_data
CONTENT_STORAGE_PATH=/path/to/content_storage
```

Then source it before running commands:
```bash
source .env  # or use: export $(cat .env | xargs)
uvx pulsar-mcp index --config mcp-servers.json
```

**Note:** For stdio transport, environment variables must also be included in your MCP client config (see [stdio transport section](#stdio-transport) below).

## Quick Start

**1. Create your MCP servers config** (`mcp-servers.json`):

This is an enhanced schema of Claude Desktop's MCP configuration with additional Pulsar-specific fields.

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",  // or "uvx", "docker", any executable
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/directory"],
      "env": {},  // optional: environment variables for this server
      "timeout": 30.0,  // optional: seconds to wait for MCP server startup (default: 30)
      "hints": ["file operations", "read write files"],  // optional: help semantic search discover this server
      "blocked_tools": [],  // optional: tools to index but block at runtime
      "ignore": false,  // optional: skip indexing this server entirely
      "overwrite": false  // optional: force re-indexing even if already indexed
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "..."},
      "blocked_tools": ["delete_repository", "fork_repository"]  // indexed but execution blocked
    },
    "elevenlabs": {
      "command": "uvx",
      "args": ["elevenlabs-mcp"],
      "env": {"ELEVENLABS_API_KEY": "..."},
      "hints": [
        "When the user requests audio generation (speech or music), always execute in background mode",
        "Proactively offer to play audio using the ElevenLabs tool when contextually relevant"
      ]
    },
    "exa": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.exa.ai/mcp"],
      "env": {"EXA_API_KEY": "..."},
      "hints": [
        "Always execute web searches in background mode to avoid blocking the conversation",
        "Multiple Exa tool calls can be fired in parallel to efficiently gather information from different sources"
      ]
    }
  }
}
```

**Enhanced Configuration Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `command` | string | Executable to run (npx, uvx, docker, python, etc.) |
| `args` | array | Command-line arguments passed to the executable |
| `env` | object | Environment variables for this MCP server |
| `timeout` | number | Seconds to wait for server startup (default: 30.0) |
| `hints` | array | **Powerful!** Guide the LLM on how to use this server. Used for both discovery and execution instructions. Examples: "Always execute in background mode", "Multiple calls can be fired in parallel", "Proactively offer when contextually relevant" |
| `blocked_tools` | array | Tool names that will be indexed but blocked from execution |
| `ignore` | boolean | If true, skip indexing this server entirely (default: false) |
| `overwrite` | boolean | If true, force re-index even if already indexed (default: false) |

**Note:** The `command`, `args`, and `env` fields are standard MCP configuration. The other fields are Pulsar enhancements for better control and discovery.

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

### Troubleshooting `uvx` Issues

**Error: `spawn uvx ENOENT` or `command not found: uvx`**

This means `uv` is not installed or not in your PATH. [Detailed troubleshooting guide](https://gist.github.com/gregelin/b90edaef851f86252c88ecc066c93719) • [Official MCP docs](https://modelcontextprotocol.io/docs/develop/build-server).

**Quick fixes:**

1. **Install uv** (if not installed):
   ```bash
   # macOS/Linux
   brew install uv

   # or official installer
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Ensure uv is in PATH** (macOS/Linux):
   ```bash
   # Check if installed
   which uvx

   # If not found, add to PATH (add to ~/.zshrc or ~/.bashrc)
   export PATH="$HOME/.local/bin:$PATH"

   # Or create symlink
   sudo ln -s ~/.local/bin/uvx /usr/local/bin/uvx
   ```

3. **Use absolute path** in config (find with `which uvx`):
   ```json
   "command": "/Users/you/.local/bin/uvx"  // macOS
   "command": "C:\\Users\\you\\.local\\bin\\uvx.exe"  // Windows
   ```

**Alternative: Use mcp-remote for HTTP mode**

If `uvx` issues persist, run Pulsar via HTTP and connect through `mcp-remote`:

```bash
# Terminal 1: Run Pulsar HTTP server
uvx pulsar-mcp serve --config mcp-servers.json --transport http --port 8000
```

```json
// Claude Desktop config
{
  "mcpServers": {
    "pulsar": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/mcp"]
    }
  }
}
```

This bypasses stdio issues and works reliably across platforms.

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

**Built after several months of research and development**

*Multiple architectural iterations • Real-world agent deployments • Extensive testing across diverse MCP ecosystems*

Pulsar emerged from solving actual problems in production agent systems where traditional approaches failed. Every feature—from semantic routing to background execution to content offloading—was battle-tested against the challenges of scaling MCP ecosystems beyond toy examples.

We hope Pulsar will be useful to the community in building more capable and efficient agent systems.

</div>
