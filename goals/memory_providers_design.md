# Pluggable Memory Provider Architecture

## Overview

Design for an extensible memory provider interface that allows DexAI to swap between different memory backends (native, Mem0, Zep, SimpleMem) while preserving ADHD-safe design principles and the existing MCP tool interface.

## Research Summary

### Provider Comparison

| Provider | Cloud Option | Self-Hosted | API Key Only | Infra Required | Unique Features |
|----------|-------------|-------------|--------------|----------------|-----------------|
| **Native** | ❌ | ❌ | ❌ | ❌ | Local SQLite, hybrid BM25+semantic |
| **Mem0** | ✅ app.mem0.ai | ✅ Qdrant/etc | ✅ (cloud) | ✅ (self-hosted) | Graph memory, 24+ vector DBs |
| **Zep** | ✅ getzep.com | ✅ Neo4j+OpenSearch | ✅ (cloud) | ✅ (self-hosted) | Temporal knowledge graph, <200ms |
| **SimpleMem** | ✅ mcp.simplemem.cloud | ❌ | ✅ | ❌ | Semantic compression, 30× fewer tokens |
| **ClaudeMem** | ❌ | ✅ (local) | ❌ | ❌ | Progressive disclosure, 10× token savings, auto-capture hooks |

### Deployment Mode Decision

**Same provider, different modes** when:
- Same SDK/API with different endpoints
- Configuration-driven switching
- Shared type mappings

**Separate providers** when:
- Fundamentally different APIs
- Different data models
- No self-hosted option (SimpleMem)

**Decisions:**
- **Mem0**: Same provider with `mode: cloud | self_hosted`
- **Zep**: Same provider with `mode: cloud | self_hosted`
- **SimpleMem**: Cloud-only provider (no self-hosted option)
- **ClaudeMem**: Local-only provider (hooks-based, MCP tools, SQLite+Chroma)
- **Native**: Local-only provider (no cloud/self-hosted)

---

## Architecture

### Layer Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MCP Tools (Unchanged API)                     │
│  dexai_memory_search, dexai_memory_write, dexai_commitments_*       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                      MemoryService (Facade)                          │
│  - Loads configured provider                                         │
│  - Applies ADHD-safe transformations                                │
│  - Auto-fallback to native provider if external fails                │
│  - Delegates commitments/context to provider                         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                  MemoryProvider (Abstract Base Class)                │
│                                                                      │
│  Properties:                                                         │
│    name: str                    # Provider identifier                │
│    deployment_mode: DeploymentMode  # cloud, self_hosted, local     │
│    supports_cloud: bool         # Can use cloud API                  │
│    supports_self_hosted: bool   # Can self-host                      │
│    supports_local: bool         # Runs entirely locally              │
│                                                                      │
│  Lifecycle:                                                          │
│    check_dependencies() → DependencyStatus                           │
│    bootstrap() → BootstrapResult                                     │
│    deploy_local() → DeployResult (optional)                          │
│    teardown() → bool                                                 │
│                                                                      │
│  Core Operations:                                                    │
│    add(content, type, importance, ...) → str                        │
│    search(query, limit, filters, search_type) → list[MemoryEntry]   │
│    get(id) → MemoryEntry | None                                     │
│    update(id, ...) → bool                                            │
│    delete(id, hard) → bool                                           │
│    list(filters, limit, offset) → list[MemoryEntry]                 │
│    health_check() → HealthStatus                                     │
│                                                                      │
│  ADHD Features:                                                      │
│    add_commitment(...) → str                                         │
│    list_commitments(user_id, status) → list[dict]                   │
│    complete_commitment(id) → bool                                    │
│    capture_context(user_id, state, trigger) → str                   │
│    resume_context(user_id, snapshot_id) → dict | None               │
│    list_contexts(user_id, limit) → list[dict]                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────────────┐
        │                       │                               │
        ▼                       ▼                               ▼
┌───────────────┐    ┌─────────────────────┐    ┌──────────────────────┐
│ NativeProvider│    │ Mem0Provider        │    │ ZepProvider          │
│ (LOCAL)       │    │ (CLOUD/SELF_HOSTED) │    │ (CLOUD/SELF_HOSTED)  │
│               │    │                     │    │                      │
│ SQLite +      │    │ mode=cloud:         │    │ mode=cloud:          │
│ hybrid search │    │   → app.mem0.ai API │    │   → getzep.com API   │
│               │    │ mode=self_hosted:   │    │ mode=self_hosted:    │
│               │    │   → Qdrant + LLM    │    │   → Neo4j + OpenSearch│
└───────────────┘    └─────────────────────┘    └──────────────────────┘
        │                       │                               │
        ▼                       ▼                               ▼
┌───────────────┐    ┌─────────────────────┐    ┌──────────────────────┐
│ data/memory.db│    │ Cloud: API endpoint │    │ Cloud: API endpoint  │
│ (local file)  │    │ Self: Qdrant server │    │ Self: Neo4j cluster  │
└───────────────┘    └─────────────────────┘    └──────────────────────┘

                              │
                              ▼
                    ┌─────────────────────┐
                    │ SimpleMemProvider   │
                    │ (CLOUD only)        │
                    │                     │
                    │ mcp.simplemem.cloud │
                    │ MCP Streamable HTTP │
                    └─────────────────────┘
```

### Deployment Modes

```python
class DeploymentMode(str, Enum):
    CLOUD = "cloud"           # API-key based, no infrastructure needed
    SELF_HOSTED = "self_hosted"  # Requires running your own infrastructure
    LOCAL = "local"           # Runs entirely locally (e.g., SQLite)
```

### Provider Capabilities Matrix

| Provider | `supports_cloud` | `supports_self_hosted` | `supports_local` |
|----------|-----------------|----------------------|------------------|
| Native | ❌ | ❌ | ✅ |
| Mem0 | ✅ | ✅ | ❌ |
| Zep | ✅ | ✅ | ❌ |
| SimpleMem | ✅ | ❌ | ❌ |
| ClaudeMem | ❌ | ❌ | ✅ |

---

## Configuration Schema

```yaml
# args/memory.yaml

memory:
  # Provider selection
  provider: "native"  # Options: native, mem0, zep, simplemem

  # Provider-specific configuration
  providers:
    native:
      # LOCAL mode only - no external dependencies
      database_path: "data/memory.db"
      embedding_model: "text-embedding-3-small"
      hybrid_weights:
        semantic: 0.3
        keyword: 0.7

    mem0:
      # Deployment mode: cloud or self_hosted
      mode: "cloud"  # Options: cloud, self_hosted

      # Cloud mode configuration (mode: cloud)
      cloud:
        api_key: "${MEM0_API_KEY}"
        org_id: "${MEM0_ORG_ID}"
        project_id: "${MEM0_PROJECT_ID}"

      # Self-hosted mode configuration (mode: self_hosted)
      self_hosted:
        # Vector store backend
        vector_store:
          provider: "qdrant"  # qdrant, chroma, pinecone, pgvector, etc.
          config:
            host: "localhost"
            port: 6333
        # Embedding provider
        embedder:
          provider: "openai"
          model: "text-embedding-3-small"
        # LLM for memory extraction (optional)
        llm:
          provider: "anthropic"
          model: "claude-sonnet-4-20250514"

    zep:
      # Deployment mode: cloud or self_hosted
      mode: "cloud"  # Options: cloud, self_hosted

      # Cloud mode configuration (mode: cloud)
      cloud:
        api_key: "${ZEP_API_KEY}"
        # Optional project isolation
        project_id: "${ZEP_PROJECT_ID}"

      # Self-hosted mode configuration (mode: self_hosted)
      self_hosted:
        api_url: "http://localhost:8000"
        # Optional API key for self-hosted auth
        api_key: "${ZEP_SELF_HOSTED_API_KEY}"

    simplemem:
      # CLOUD mode only - no self-hosted option
      api_url: "https://mcp.simplemem.cloud"
      api_key: "${SIMPLEMEM_API_KEY}"
      # Optional user isolation
      user_id: "${SIMPLEMEM_USER_ID}"

    claudemem:
      # LOCAL mode only - runs on your machine
      # Source: https://github.com/thedotmack/claude-mem
      data_dir: "~/.claude-mem"  # Data storage location
      worker_port: 37777  # HTTP API port
      # Auto-capture settings (hooks-based)
      auto_capture:
        enabled: true
        session_start: true
        post_tool_use: true
        session_end: true
      # Web viewer
      web_viewer:
        enabled: true
        port: 37777  # Same as worker by default

  # ADHD-specific settings (applied regardless of provider)
  adhd:
    # Never surface guilt-inducing language
    language_filter: true
    # Forward-facing framing for commitments/context
    forward_facing: true
    # Max memories injected into system prompt
    max_context_injection: 5
    # Commitment reminder style: gentle, standard, urgent
    reminder_style: "gentle"

  # Fallback configuration
  fallback:
    enabled: true
    provider: "native"  # Fall back to native provider if primary fails
    log_fallback: true  # Log when fallback occurs
    retry_primary_after: 300  # Seconds before retrying primary provider
```

---

## Provider Implementation Guide

### Mem0Provider (Cloud + Self-Hosted)

```python
class Mem0Provider(MemoryProvider):
    """
    Mem0 memory provider supporting both cloud and self-hosted modes.

    Cloud Mode (app.mem0.ai):
        - API key authentication
        - No infrastructure required
        - Includes graph memory, webhooks, analytics
        - Pricing: Free (10K memories) → Pro ($249/mo)

    Self-Hosted Mode:
        - Requires vector store (Qdrant, Chroma, Pinecone, etc.)
        - Requires embedding provider (OpenAI, local)
        - Full control over data
        - 24+ vector database options

    Both modes use the same Python SDK (mem0ai).
    """

    def __init__(self, config: dict):
        self._mode = DeploymentMode(config.get("mode", "cloud"))

        if self._mode == DeploymentMode.CLOUD:
            self._client = Memory(
                api_key=config["cloud"]["api_key"],
                org_id=config["cloud"].get("org_id"),
                project_id=config["cloud"].get("project_id"),
            )
        else:
            # Self-hosted configuration
            self._client = Memory(config=config["self_hosted"])

    @property
    def name(self) -> str:
        return "mem0"

    @property
    def deployment_mode(self) -> DeploymentMode:
        return self._mode

    @property
    def supports_cloud(self) -> bool:
        return True

    @property
    def supports_self_hosted(self) -> bool:
        return True

    async def check_dependencies(self) -> DependencyStatus:
        if self._mode == DeploymentMode.CLOUD:
            # Cloud mode: just check API key validity
            deps = {"api_key": bool(self._config["cloud"].get("api_key"))}
            return DependencyStatus(
                ready=all(deps.values()),
                dependencies=deps,
                missing=[k for k, v in deps.items() if not v],
            )
        else:
            # Self-hosted: check vector store and embedder
            deps = {}
            missing = []

            # Check vector store
            try:
                # Ping vector store
                deps["vector_store"] = await self._ping_vector_store()
            except Exception:
                deps["vector_store"] = False
                missing.append("vector_store")

            # Check embedder API key
            deps["embedder"] = bool(os.getenv("OPENAI_API_KEY"))
            if not deps["embedder"]:
                missing.append("embedder")

            return DependencyStatus(
                ready=len(missing) == 0,
                dependencies=deps,
                missing=missing,
                instructions=self._get_setup_instructions(missing),
            )
```

### ZepProvider (Cloud + Self-Hosted)

```python
class ZepProvider(MemoryProvider):
    """
    Zep memory provider with temporal knowledge graph.

    Cloud Mode (getzep.com):
        - <200ms latency
        - SOC2 Type 2 / HIPAA compliance
        - Managed scaling
        - No infrastructure required

    Self-Hosted Mode:
        - Requires Neo4j, Falkor, or Neptune
        - Requires OpenSearch for full-text search
        - Full data residency control
        - Can deploy in your own VPC
    """

    @property
    def supports_cloud(self) -> bool:
        return True

    @property
    def supports_self_hosted(self) -> bool:
        return True

    async def check_dependencies(self) -> DependencyStatus:
        if self._mode == DeploymentMode.CLOUD:
            return DependencyStatus(
                ready=bool(self._config["cloud"].get("api_key")),
                dependencies={"api_key": bool(self._config["cloud"].get("api_key"))},
                missing=[] if self._config["cloud"].get("api_key") else ["api_key"],
            )
        else:
            # Self-hosted requires Neo4j + OpenSearch
            deps = {}
            missing = []

            # Check Neo4j
            if not await self._ping_neo4j():
                deps["neo4j"] = False
                missing.append("neo4j")
            else:
                deps["neo4j"] = True

            # Check OpenSearch (optional but recommended)
            if not await self._ping_opensearch():
                deps["opensearch"] = False
                # Not blocking, but warn

            return DependencyStatus(
                ready="neo4j" not in missing,
                dependencies=deps,
                missing=missing,
                instructions="Run: docker-compose up -d neo4j opensearch" if missing else None,
            )
```

### SimpleMemProvider (Cloud Only)

```python
class SimpleMemProvider(MemoryProvider):
    """
    SimpleMem memory provider - cloud-hosted only.

    Features:
        - Semantic lossless compression
        - 30× fewer inference tokens vs Mem0
        - +26.4% avg F1 improvement
        - 50.2% faster retrieval
        - MCP Streamable HTTP transport

    No self-hosted option available.
    """

    def __init__(self, config: dict):
        self._mode = DeploymentMode.CLOUD  # Always cloud
        self._api_url = config.get("api_url", "https://mcp.simplemem.cloud")
        self._api_key = config.get("api_key")

    @property
    def name(self) -> str:
        return "simplemem"

    @property
    def deployment_mode(self) -> DeploymentMode:
        return DeploymentMode.CLOUD

    @property
    def supports_cloud(self) -> bool:
        return True

    @property
    def supports_self_hosted(self) -> bool:
        return False  # No self-hosted option

    @property
    def supports_local(self) -> bool:
        return False

    async def deploy_local(self) -> DeployResult:
        raise NotImplementedError(
            "SimpleMem is cloud-only. No self-hosted deployment available. "
            "Register at https://mcp.simplemem.cloud for API access."
        )
```

### ClaudeMemProvider (Local Only)

```python
class ClaudeMemProvider(MemoryProvider):
    """
    ClaudeMem memory provider - local-only.

    Source: https://github.com/thedotmack/claude-mem

    Features:
        - Progressive disclosure (3-layer retrieval pattern)
        - ~10× token savings vs full context
        - Automatic observation capture via hooks
        - SQLite + Chroma hybrid storage
        - Web viewer UI at localhost:37777
        - MCP tools interface (search, timeline, get_observations, save_memory)

    Requirements:
        - Node.js 18.0.0+
        - Bun (auto-installed)
        - SQLite 3 (bundled)
        - Local only - data stored in ~/.claude-mem/

    License: AGPL-3.0
    """

    def __init__(self, config: dict):
        self._mode = DeploymentMode.LOCAL  # Always local
        self._data_dir = Path(config.get("data_dir", "~/.claude-mem")).expanduser()
        self._worker_port = config.get("worker_port", 37777)
        self._worker_url = f"http://localhost:{self._worker_port}"

    @property
    def name(self) -> str:
        return "claudemem"

    @property
    def deployment_mode(self) -> DeploymentMode:
        return DeploymentMode.LOCAL

    @property
    def supports_cloud(self) -> bool:
        return False

    @property
    def supports_self_hosted(self) -> bool:
        return False

    @property
    def supports_local(self) -> bool:
        return True

    async def check_dependencies(self) -> DependencyStatus:
        deps = {}
        missing = []

        # Check Node.js
        try:
            result = subprocess.run(["node", "--version"], capture_output=True)
            version = result.stdout.decode().strip()
            deps["nodejs"] = version >= "v18"
            if not deps["nodejs"]:
                missing.append("nodejs")
        except FileNotFoundError:
            deps["nodejs"] = False
            missing.append("nodejs")

        # Check Bun
        try:
            subprocess.run(["bun", "--version"], capture_output=True)
            deps["bun"] = True
        except FileNotFoundError:
            deps["bun"] = False
            missing.append("bun")

        # Check worker service
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._worker_url}/health", timeout=2.0)
                deps["worker"] = resp.status_code == 200
        except:
            deps["worker"] = False
            missing.append("worker")

        return DependencyStatus(
            ready=len(missing) == 0,
            dependencies=deps,
            missing=missing,
            instructions=(
                "Install claude-mem: npx @thedotmack/claude-mem install\n"
                "Start worker: claude-mem start"
            ) if missing else None,
        )

    async def bootstrap(self) -> BootstrapResult:
        # ClaudeMem auto-initializes on first use
        return BootstrapResult(
            success=True,
            message="ClaudeMem auto-initializes on first use",
            created=[],
        )

    # MCP tool integration
    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: SearchFilters | None = None,
        search_type: str = "hybrid",
    ) -> list[MemoryEntry]:
        """
        Uses ClaudeMem's 3-layer retrieval pattern:
        1. search (compact index) → get IDs
        2. get_observations (full details) → get content
        """
        async with httpx.AsyncClient() as client:
            # First layer: search for IDs
            resp = await client.post(
                f"{self._worker_url}/mcp/search",
                json={"query": query, "limit": limit}
            )
            ids = resp.json().get("ids", [])

            if not ids:
                return []

            # Second layer: get full observations
            resp = await client.post(
                f"{self._worker_url}/mcp/get_observations",
                json={"ids": ids}
            )
            observations = resp.json().get("observations", [])

            return [self._to_memory_entry(obs) for obs in observations]
```

---

## Type Mappings

### Memory Type Mapping

| DexAI Type | Mem0 | Zep | SimpleMem | ClaudeMem |
|------------|------|-----|-----------|-----------|
| `fact` | metadata.type=fact | Entity | memory.fact | observation |
| `preference` | metadata.type=preference | Entity+Attribute | memory.preference | observation |
| `event` | metadata.type=event | Episode | memory.event | observation |
| `insight` | metadata.type=insight | Community Summary | memory.insight | summary |
| `task` | metadata.type=task | Episode | memory.task | observation |
| `relationship` | metadata.type=relationship | Edge/Relationship | memory.relationship | observation |

### Search Type Mapping

| DexAI Search | Mem0 | Zep | SimpleMem | ClaudeMem |
|--------------|------|-----|-----------|-----------|
| `semantic` | vector search | embedding search | semantic retrieval | Chroma vector |
| `keyword` | N/A (semantic only) | full-text search | N/A | SQLite FTS |
| `hybrid` | semantic + filters | graph + search | intent-aware hybrid | Chroma + SQLite |

---

## CLI Commands

```bash
# Check provider status and dependencies
dexai memory check
# Output:
# Provider: mem0 (cloud mode)
# Status: Ready ✓
# Dependencies:
#   ✓ api_key: configured
#   ✓ org_id: configured

# Interactive setup wizard
dexai memory setup
# → Prompts for provider selection
# → Validates credentials
# → Tests connectivity
# → Writes args/memory.yaml

# Deploy local dependencies (self-hosted only)
dexai memory deploy
# → Starts Docker containers (Qdrant, Neo4j, etc.)
# → Waits for services to be ready
# → Runs bootstrap

# Migrate between providers
dexai memory migrate --from native --to mem0
# → Exports all memories from native
# → Imports to mem0
# → Verifies migration

# Provider health check
dexai memory health
# Output:
# Provider: mem0 (cloud)
# Latency: 45ms
# Status: Healthy
# Memories: 1,234
# Commitments: 12
# Contexts: 45
```

---

## Implementation Plan

### Phase 1: Core Infrastructure

| Task | Description | Files |
|------|-------------|-------|
| 1.1 | ~~Create base classes~~ | `providers/__init__.py`, `providers/base.py` |
| 1.2 | Create configuration schema | `args/memory.yaml` |
| 1.3 | Create MemoryService facade | `service.py` |
| 1.4 | Create CLI commands | `cli.py`, update `tools/cli.py` |

### Phase 2: Native Provider (Refactor)

| Task | Description | Files |
|------|-------------|-------|
| 2.1 | Refactor as NativeProvider | `providers/native.py` |
| 2.2 | Update MCP tools | `agent/mcp/memory_tools.py` |
| 2.3 | Update SDK client | `agent/sdk_client.py` |

### Phase 3: External Providers (Parallel)

| Task | Description | Files |
|------|-------------|-------|
| 3.1 | Mem0Provider (cloud+self-hosted) | `providers/mem0_provider.py` |
| 3.2 | ZepProvider (cloud+self-hosted) | `providers/zep_provider.py` |
| 3.3 | SimpleMemProvider (cloud-only) | `providers/simplemem_provider.py` |
| 3.4 | ClaudeMemProvider (local-only) | `providers/claudemem_provider.py` |

### Phase 4: Testing & Documentation

| Task | Description | Files |
|------|-------------|-------|
| 4.1 | Unit tests | `tests/unit/memory/test_providers.py` |
| 4.2 | Integration tests | `tests/integration/test_memory_*.py` |
| 4.3 | Update manifest | `tools/manifest.md` |
| 4.4 | Update pyproject.toml | `pyproject.toml` |

---

## Dependencies

```toml
# pyproject.toml additions

[project.optional-dependencies]
# Individual provider packages
mem0 = ["mem0ai>=0.1.0"]
zep = ["zep-python>=2.0.0"]
simplemem = ["httpx>=0.25.0"]  # Uses HTTP API
claudemem = ["httpx>=0.25.0"]  # Uses local HTTP API (Node.js worker must be installed separately)

# All memory providers
memory-providers = ["mem0ai", "zep-python", "httpx"]

# Cloud-only providers (no infrastructure required)
memory-cloud = ["mem0ai", "zep-python", "httpx"]

# Development dependencies for self-hosted testing
memory-dev = [
    "docker>=7.0.0",  # For local deployment
    "pytest-docker>=2.0.0",
]
```

**Note:** ClaudeMem requires Node.js 18+ and Bun, which must be installed separately:
```bash
# Install claude-mem
npx @thedotmack/claude-mem install

# Start worker service
claude-mem start
```

---

## Migration Strategy

### For Existing Users

1. Default remains `provider: native` (no change required)
2. Data stays in `data/memory.db`
3. MCP tool signatures unchanged

### Switching Providers

```bash
# 1. Configure new provider
dexai memory setup --provider mem0

# 2. Migrate data
dexai memory migrate --from native --to mem0

# 3. Verify
dexai memory health
dexai memory search "test query"
```

---

## ADHD Safety Principles (Preserved)

Regardless of provider, `MemoryService` enforces:

1. **No guilt language** - Filter responses through `tools/adhd/language_filter.py`
2. **Forward-facing framing** - Transform "you forgot" → "ready to continue"
3. **One-thing mode** - Limit context injection to prevent overwhelm
4. **Graceful fallback** - Auto-fallback to native provider ensures no data loss

---

## Sources

- [Mem0 Documentation](https://docs.mem0.ai/)
- [Mem0 Self-Host Guide](https://www.self-host.app/services/mem0)
- [SimpleMem MCP Server](https://mcp.simplemem.cloud/)
- [SimpleMem GitHub](https://github.com/aiming-lab/SimpleMem)
- [Zep Pricing](https://www.getzep.com/pricing/)
- [Zep LangChain Integration](https://docs.langchain.com/oss/python/integrations/providers/zep)
- [ClaudeMem GitHub](https://github.com/thedotmack/claude-mem)
