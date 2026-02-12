# Agent Framework Competitive Analysis

> **Last updated:** 2026-02-11
> **Scope:** Comparison of six major AI agent frameworks across extensibility, sandboxing, security, observability, multi-agent patterns, developer experience, and production readiness.
> **Context:** Evaluating alternatives and positioning for the DexAI platform architecture.

---

## Executive Summary

The AI agent framework landscape has matured rapidly through 2025-2026. Six frameworks dominate: **Claude Agent SDK** (Anthropic), **OpenAI Agents SDK** (OpenAI), **LangGraph** (LangChain), **CrewAI**, **AutoGen** (Microsoft), and **Semantic Kernel / Microsoft Agent Framework** (Microsoft). Each takes a fundamentally different architectural approach, and the right choice depends heavily on which dimension matters most to your use case.

**Key finding:** No single framework wins across all dimensions. Claude Agent SDK leads in sandboxing, security depth, and single-agent autonomy. OpenAI Agents SDK excels at lightweight multi-agent handoffs. LangGraph dominates in stateful workflow orchestration. CrewAI offers the best ergonomics for role-based multi-agent collaboration. Microsoft Agent Framework (the convergence of AutoGen and Semantic Kernel) provides the most enterprise-grade governance and observability infrastructure.

---

## Comparison Matrix

| Dimension | Claude Agent SDK | OpenAI Agents SDK | LangGraph | CrewAI | AutoGen / MS Agent Framework | Semantic Kernel / MS Agent Framework |
|-----------|-----------------|-------------------|-----------|--------|------------------------------|--------------------------------------|
| **Extensibility** | MCP-native, hooks, subagents, skills, plugins | MCP support, function tools, agents-as-tools | MCP adapters, LangChain tools, custom nodes | MCP support, custom tools, tool collections | MCP + A2A + OpenAPI, pluggable components | MCP + A2A + OpenAPI, plugins, connectors |
| **Sandboxing** | OS-level (bubblewrap/seatbelt), container, gVisor, VM | Cloud containers (Codex), Code Interpreter sandbox | External (Pyodide/Deno sandbox, Docker) | Docker-based CodeInterpreter, external sandboxes | Docker, Azure Container Apps | Inherits from MS Agent Framework |
| **Security Model** | PreToolUse hooks, permission modes, deny-first evaluation, audit | Guardrails (input/output), permission prompts | Community-managed, no built-in RBAC | RBAC (enterprise), task-scoped tool access | Azure Entra, responsible AI, prompt shields | Azure Entra, Content Safety, filters |
| **Observability** | Hooks-based (PostToolUse, Notification), Langfuse, OTel wrappers | Built-in tracing dashboard, custom trace processors | LangSmith platform, OTel export | CrewAI AMP observability, MLflow, AgentOps | Native OpenTelemetry, Azure Monitor | Native OpenTelemetry, Azure Monitor |
| **Multi-Agent** | Subagents (orchestrator-worker), Task tool delegation | Handoffs (agent-to-agent transfer), agents-as-tools | Supervisor/Swarm/custom graph patterns | Sequential/hierarchical/consensus crews | Group chat, debate, reflection, A2A protocol | Inherits from MS Agent Framework |
| **DX / Getting Started** | 2 lines to first agent, SDK-first, code-forward | Minimal abstractions, Python-first, fast prototyping | Steeper curve, graph concepts required | Role metaphor, intuitive for teams | Moderate, async-first, converging APIs | Moderate, enterprise-oriented, multi-language |
| **Production Readiness** | High (powers Claude Code), proprietary license | High (powers Codex), MIT license | High (LangSmith ecosystem), mixed licenses | Growing (enterprise tier available), Apache-2.0 | Transitioning to MS Agent Framework, MIT | Public preview, GA target Q1 2026, MIT |
| **Model Lock-in** | Claude models only (Anthropic, Bedrock, Vertex, Azure) | Provider-agnostic (100+ LLMs via OpenAI-compatible API) | Model-agnostic (any LLM provider) | Model-agnostic (any LLM provider) | Model-agnostic (OpenAI, Azure, local) | Model-agnostic (extensive connector library) |

---

## A. Extensibility & Plugin Systems

### Claude Agent SDK

- **Tool registration:** Static via `allowed_tools` parameter and dynamic via MCP servers configured in code or `.mcp.json` files. Tools are named with convention `mcp__<server>__<action>`. ([SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview))
- **MCP support:** First-class, native. Anthropic created and maintains the MCP standard. Hundreds of community MCP servers available. ([MCP Docs](https://platform.claude.com/docs/en/agent-sdk/mcp))
- **Plugin system:** Skills (`.claude/skills/SKILL.md`), slash commands (`.claude/commands/*.md`), and programmatic plugins via `plugins` option. ([SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview))
- **Hot-reloading:** MCP servers can be configured per-query; skills are loaded dynamically from filesystem. No runtime hot-swap of built-in tools.
- **Versioning:** Skills are file-based markdown; versioning via source control. No built-in registry or marketplace.

### OpenAI Agents SDK

- **Tool registration:** Function tools with automatic schema generation from Python type hints. Any Python function becomes a tool. ([OpenAI Agents SDK Docs](https://openai.github.io/openai-agents-python/))
- **MCP support:** Built-in MCP server integration that works identically to function tools. ([OpenAI Agents SDK](https://openai.github.io/openai-agents-python/))
- **Plugin system:** Agents-as-tools pattern where agents themselves serve as tools for other agents. AGENTS.md convention for repository-level agent configuration. ([New tools for building agents](https://openai.com/index/new-tools-for-building-agents/))
- **Hot-reloading:** Not built-in. Tools are registered at agent definition time.
- **Versioning:** No built-in versioning or marketplace.

### LangGraph

- **Tool registration:** Via LangChain tool decorators, ToolNode graph nodes, or MCP-compliant adapters. Supports both static and dynamic tool binding. ([LangGraph GitHub](https://github.com/langchain-ai/langgraph))
- **MCP support:** MCP-compliant adapters for tool invocation and context sharing. ([LangGraph & MCP](https://healthark.ai/orchestrating-multi-agent-systems-with-lang-graph-mcp/))
- **Plugin system:** Extensive LangChain ecosystem with hundreds of integrations. LangGraph Pre-Builts provide common agent architectures. ([LangChain](https://www.langchain.com/langgraph))
- **Hot-reloading:** LangGraph Studio v2 supports prompt updates via UI. Tool changes require graph recompilation.
- **Versioning:** LangSmith supports prompt versioning and dataset management.

### CrewAI

- **Tool registration:** Custom tools via `BaseTool` subclasses, decorator-based tools, or MCP server tool collections (`ToolCollection.from_mcp`). ([CrewAI Tools GitHub](https://github.com/crewAIInc/crewAI-tools))
- **MCP support:** Full MCP support via `crewai-tools[mcp]` extra. Supports stdio, HTTP, and SSE transport types. Direct agent integration via `mcps` field. ([CrewAI MCP Docs](https://docs.crewai.com/en/mcp/overview))
- **Plugin system:** crewai-tools package with built-in tools for web scraping, file processing, API interactions. Community-contributed tool collections.
- **Hot-reloading:** Not documented as a built-in feature.
- **Versioning:** No built-in versioning or marketplace.

### AutoGen / Microsoft Agent Framework

- **Tool registration:** Via OpenAPI specs, MCP servers, or A2A protocol. Pluggable components for custom agents, tools, memory, and models. ([AutoGen GitHub](https://github.com/microsoft/autogen))
- **MCP support:** Native MCP support plus A2A (Agent-to-Agent) protocol and OpenAPI for tool calling. ([Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview))
- **Plugin system:** Semantic Kernel plugins and connectors. YAML/JSON declarative agent definitions. ([Microsoft Agent Framework Blog](https://devblogs.microsoft.com/foundry/introducing-microsoft-agent-framework-the-open-source-engine-for-agentic-ai-apps/))
- **Hot-reloading:** Agents can discover tools dynamically via A2A Agent Cards.
- **Versioning:** YAML/JSON declarative definitions support version-controlled workflows.

### Semantic Kernel / Microsoft Agent Framework

- Converging with AutoGen into unified Microsoft Agent Framework. All capabilities listed above apply.
- **Additional:** Extensive connector library for Azure AI Foundry, Microsoft Graph, SharePoint, Redis, Elastic. ([Semantic Kernel Docs](https://learn.microsoft.com/en-us/semantic-kernel/overview/))

---

## B. Sandboxing & Isolation

### Claude Agent SDK

**Rating: Best-in-class**

- **OS-level sandboxing:** Uses Linux `bubblewrap` and macOS `sandbox-exec` (Seatbelt) for filesystem and network isolation at the OS level. Open-sourced as `@anthropic-ai/sandbox-runtime`. ([Claude Code Sandboxing Blog](https://www.anthropic.com/engineering/claude-code-sandboxing))
- **Container support:** Full Docker support with detailed security hardening guidance (`--cap-drop ALL`, `--network none`, `--read-only`, seccomp profiles). ([Secure Deployment Docs](https://platform.claude.com/docs/en/agent-sdk/secure-deployment))
- **gVisor support:** Documented with performance tradeoff analysis. Recommended for multi-tenant deployments. ([Secure Deployment Docs](https://platform.claude.com/docs/en/agent-sdk/secure-deployment))
- **VM isolation:** Firecracker microVM support documented with vsock architecture for network control. ([Secure Deployment Docs](https://platform.claude.com/docs/en/agent-sdk/secure-deployment))
- **Network restrictions:** Unix socket proxy architecture for domain allowlisting. Agent has no network interfaces; all traffic routes through controlled proxy. ([Secure Deployment Docs](https://platform.claude.com/docs/en/agent-sdk/secure-deployment))
- **Resource limiting:** Memory, CPU, PID limits via container configuration.
- **Impact:** Sandboxing reduces permission prompts by 84% in internal usage. ([InfoQ](https://www.infoq.com/news/2025/11/anthropic-claude-code-sandbox/))

### OpenAI Agents SDK

- **Cloud sandbox:** Codex runs in isolated OpenAI-managed containers with internet access disabled during execution. ([OpenAI Codex Security](https://developers.openai.com/codex/security/))
- **Code Interpreter:** Python execution in sandboxed containers ($0.03/session). ([OpenAI Pricing](https://platform.openai.com/docs/pricing))
- **Self-hosted:** The SDK itself does not ship an integrated sandbox runtime. Developers use external sandbox solutions (E2B, Daytona, Docker). ([5 Code Sandboxes for AI Agents](https://www.kdnuggets.com/5-code-sandbox-for-your-ai-agents))
- **Network restrictions:** Codex-managed environments block internet by default. Self-hosted requires manual configuration.

### LangGraph

- **No built-in sandbox.** LangGraph itself is an orchestration layer; sandboxing is the developer's responsibility.
- **LangChain Sandbox:** Separate package (`langchain-sandbox`) using Pyodide and Deno for untrusted Python execution with network restriction via `allow_net`. ([LangChain Sandbox GitHub](https://github.com/langchain-ai/langchain-sandbox))
- **Container support:** Documentation recommends Docker containers for code-generating agents. No native integration.
- **Kubernetes:** Compatible with Agent Sandbox Kubernetes controller for gVisor-based isolation. ([Agent Sandbox K8s](https://www.infoq.com/news/2025/12/agent-sandbox-kubernetes/))

### CrewAI

- **Docker-based CodeInterpreter:** Runs code in isolated Docker containers by default. Falls back to restricted Python environment if Docker unavailable. ([CrewAI Code Interpreter Docs](https://docs.crewai.com/en/tools/ai-ml/codeinterpretertool))
- **Custom Dockerfile support:** `user_dockerfile_path` parameter for custom container images.
- **Known issues:** Code execution in Docker-in-Docker scenarios (CrewAI itself running in Docker) has documented bugs. ([GitHub Issue #3028](https://github.com/crewAIInc/crewAI/issues/3028))
- **`unsafe_mode`:** Escape hatch that executes code directly on host. Documented but discouraged.

### AutoGen / Microsoft Agent Framework

- **Docker executor:** `DockerCommandLineCodeExecutor` runs LLM-generated code in Docker containers. ([AutoGen Guide](https://www.microsoft.com/en-us/research/project/autogen/))
- **Azure Container Apps:** Cloud-native sandboxing with managed container environments. ([Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview))
- **Enterprise compliance:** When used with Azure, includes encryption at rest/transit, network isolation via VNets, compliance with SOC 2, ISO 27001, HIPAA. ([BayTech Consulting](https://www.baytechconsulting.com/blog/microsoft-autogen))

---

## C. Security Model

### Claude Agent SDK

**Rating: Most comprehensive**

- **Permission system:** Three modes: `bypassPermissions` (auto-approve all), `acceptEdits` (auto-approve reads, prompt for writes), and default (prompt for everything). `allowed_tools` whitelist restricts which tools are available. ([SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview))
- **PreToolUse hooks:** Programmatic deny/allow/ask decisions before any tool executes. Deny-first evaluation: any hook returning `deny` blocks the operation regardless of other hooks. ([Hooks Docs](https://platform.claude.com/docs/en/agent-sdk/hooks))
- **Prompt injection defense:** Web search results summarized before entering context. Static analysis on bash commands. Sandbox isolation as defense-in-depth. ([Secure Deployment Docs](https://platform.claude.com/docs/en/agent-sdk/secure-deployment))
- **Tool output validation:** PostToolUse hooks enable validation/transformation of tool outputs.
- **Audit logging:** PostToolUse hooks can log every tool call with full input/output to audit trails.
- **Credential management:** Proxy pattern recommended; credentials injected outside agent boundary. Support for `ANTHROPIC_BASE_URL` and `HTTP_PROXY`/`HTTPS_PROXY`. ([Secure Deployment Docs](https://platform.claude.com/docs/en/agent-sdk/secure-deployment))

### OpenAI Agents SDK

- **Guardrails:** Input and output guardrails run in parallel with agent execution. Fail-fast when checks do not pass. ([OpenAI Agents SDK Docs](https://openai.github.io/openai-agents-python/))
- **Permission system:** No built-in RBAC. Tool access controlled at agent definition time.
- **Prompt injection defense:** Not documented as built-in SDK feature. Relies on model-level safety.
- **Audit logging:** Tracing system captures all events but is observability-focused, not security-focused.

### LangGraph

- **Permission system:** No built-in RBAC or permission system.
- **Security vulnerability:** CVE-2025-68664 (LangGrinch) demonstrated critical serialization injection vulnerability enabling secret exfiltration and code execution. ([Cyata Blog](https://cyata.ai/blog/langgrinch-langchain-core-cve-2025-68664/))
- **Scoped tool access:** LangChain supports scoped tool access and permission boundaries at the application level. ([LangChain Security Policy](https://docs.langchain.com/oss/python/security-policy))
- **Audit logging:** Via LangSmith trace platform (external service).

### CrewAI

- **RBAC (Enterprise):** Organization-level roles and automation-level visibility controls in CrewAI AMP. HIPAA and SOC2 compliant. ([CrewAI RBAC Docs](https://docs.crewai.com/en/enterprise/features/rbac))
- **Task-scoped tools:** Task.tools overrides Agent.tools, enforcing least-privilege per step. Defense-in-depth model combining RBAC with task-scoped assignment. ([CrewAI RBAC Docs](https://docs.crewai.com/en/enterprise/features/rbac))
- **Guardrails:** LLMGuardrail for output validation. Hallucination detection guardrail in Enterprise. ([CrewAI Changelog](https://docs.crewai.com/en/changelog))
- **Audit logging:** Via CrewAI AMP observability platform (enterprise feature).

### AutoGen / Microsoft Agent Framework

- **Azure Entra integration:** Enterprise identity and access management. ([Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview))
- **Responsible AI features:** Task adherence (keep agents on-task), prompt shields with spotlighting (prompt injection protection), PII detection. ([Microsoft Agent Framework Blog](https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-oct-nov-2025/))
- **Azure Content Safety:** Built-in content moderation integration.
- **Secrets management:** Azure Key Vault integration. ([BayTech Consulting](https://www.baytechconsulting.com/blog/microsoft-autogen))
- **Compliance:** SOC 2, ISO 27001, HIPAA when used with Azure. ([BayTech Consulting](https://www.baytechconsulting.com/blog/microsoft-autogen))

---

## D. Observability

### Claude Agent SDK

- **Hook-based observability:** PostToolUse, SubagentStop, Notification, SessionStart/End hooks provide execution event streams. ([Hooks Docs](https://platform.claude.com/docs/en/agent-sdk/hooks))
- **OpenTelemetry:** Not built-in. Community wrapper (`claude_telemetry`) provides OTel integration for Logfire, Sentry, Honeycomb, Datadog. ([claude_telemetry GitHub](https://github.com/TechNickAI/claude_telemetry))
- **Langfuse integration:** Official integration for trace visualization and analytics. ([Langfuse Claude Agent SDK](https://langfuse.com/integrations/frameworks/claude-agent-sdk))
- **Cost tracking:** Token usage available in message stream. No built-in cost dashboard.
- **Agent reasoning:** Full transcript available via `transcript_path`. Subagent transcripts tracked separately.

### OpenAI Agents SDK

- **Built-in tracing:** Automatic collection of LLM generations, tool calls, handoffs, guardrails, and custom events. Traces dashboard for visualization. ([OpenAI Tracing Docs](https://openai.github.io/openai-agents-python/tracing/))
- **Custom trace processors:** Extensible tracing system with custom event support.
- **Cost tracking:** Via OpenAI platform usage dashboard. SDK surfaces token counts.
- **Agent reasoning:** Full trace of agent decisions visible in tracing dashboard.

### LangGraph

**Rating: Most mature observability platform**

- **LangSmith:** Dedicated observability platform with agent-specific metrics, tool calling analysis, trajectory tracking. ([LangSmith Observability](https://www.langchain.com/langsmith/observability))
- **OpenTelemetry:** Bidirectional: export LangSmith traces to OTel backends, or ingest OTel data into LangSmith. ([LangSmith](https://www.langchain.com/langsmith/observability))
- **LangGraph Studio v2:** Agent IDE for visualizing and debugging agent interactions. Runs locally without desktop app. ([LangChain Blog](https://blog.langchain.com/interrupt-2025-recap/))
- **Cost tracking:** Per-node execution costs tracked ($0.001/node). Trace-level cost aggregation.
- **Open Evals:** Open-source evaluation catalog for agent trajectories. ([LangChain Blog](https://blog.langchain.com/interrupt-2025-recap/))

### CrewAI

- **CrewAI AMP:** Enterprise observability with real-time monitoring, tracing, and actionable insights. ([CrewAI AMP](https://blog.crewai.com/how-crewai-is-evolving-beyond-orchestration-to-create-the-most-powerful-agentic-ai-platform/))
- **Third-party integrations:** MLflow tracing, AgentOps, Langfuse, Amazon CloudWatch. ([AWS CrewAI Guide](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/crewai.html))
- **JSON logging:** Structured JSON format logging for pipeline integration. ([CrewAI Changelog](https://docs.crewai.com/en/changelog))
- **Cost tracking:** Not built-in to open-source; available in AMP tier.

### AutoGen / Microsoft Agent Framework

- **Native OpenTelemetry:** Built-in instrumentation capturing distributed traces of agent actions, tool invocations, multi-agent workflows. ([AutoGen Telemetry Docs](https://microsoft.github.io/autogen/stable//user-guide/core-user-guide/framework/telemetry.html))
- **Azure Monitor:** Direct integration with Application Insights. ([Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/tutorials/agents/enable-observability))
- **Standards contribution:** Microsoft contributed standardized tracing for agentic systems to the OpenTelemetry project. ([OpenTelemetry Blog](https://opentelemetry.io/blog/2025/ai-agent-observability/))
- **Langfuse integration:** Community integration available. ([Langfuse AutoGen](https://langfuse.com/integrations/frameworks/autogen))

---

## E. Multi-Agent Patterns

### Claude Agent SDK

- **Subagents:** Specialized agents defined with custom instructions, tool sets, and independent context windows. Invoked via `Task` tool. ([Subagents Docs](https://platform.claude.com/docs/en/agent-sdk/subagents))
- **Orchestrator-worker pattern:** Lead agent (e.g., Opus 4) coordinates multiple specialized subagents (e.g., Sonnet 4) working in parallel. ([Claude Code Sub-Agents Guide](https://claudefa.st/blog/guide/agents/sub-agent-best-practices))
- **Context isolation:** Each subagent runs in its own context window. `parent_tool_use_id` tracks lineage. ([SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview))
- **Session management:** Session IDs with resume capability. Fork sessions for exploration. ([SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview))
- **Limitation:** No peer-to-peer agent communication; all coordination flows through parent agent.

### OpenAI Agents SDK

- **Handoffs:** Core primitive for agent-to-agent delegation. Conversation context transfers with the handoff. LLM sees handoff targets as callable functions. ([Handoffs Docs](https://openai.github.io/openai-agents-python/handoffs/))
- **Agents-as-tools:** Agents can be used as tools by other agents for specific subtasks. ([OpenAI Agents SDK](https://openai.github.io/openai-agents-python/))
- **History management:** `handoff_history_mapper` controls context transfer. `nest_handoff_history` option per handoff. ([Handoffs Docs](https://openai.github.io/openai-agents-python/handoffs/))
- **Session management:** Sessions provide persistent memory within agent loops. ([OpenAI Agents SDK](https://openai.github.io/openai-agents-python/))
- **Realtime agents:** Voice agents with interruption detection and context management. ([OpenAI Agents SDK](https://openai.github.io/openai-agents-python/))

### LangGraph

- **Graph-based orchestration:** Agents defined as nodes in a stateful graph. Edges define transitions with conditional routing. ([LangGraph GitHub](https://github.com/langchain-ai/langgraph))
- **Pre-built patterns:** Supervisor, Swarm, and tool-calling agent architectures available as pre-builts. ([LangChain Blog](https://blog.langchain.com/interrupt-2025-recap/))
- **Cyclic graphs:** Agents can revisit previous steps and adapt to changing conditions. ([LangGraph](https://www.langchain.com/langgraph))
- **State persistence:** Checkpointers save state at every super-step. Enables human-in-the-loop, time travel, and fault tolerance. ([LangGraph Persistence Docs](https://docs.langchain.com/oss/python/langgraph/persistence))

### CrewAI

**Rating: Most intuitive multi-agent metaphor**

- **Role-based crews:** Agents assigned distinct roles mimicking real-world organizational structures. ([CrewAI](https://www.crewai.com/))
- **Process types:** Sequential (ordered tasks), hierarchical (manager coordinates), consensus-based. ([CrewAI GitHub](https://github.com/crewAIInc/crewAI))
- **Memory:** Agents learn from past interactions and improve over time. Shared crew memory. ([CrewAI](https://www.crewai.com/))
- **Flows:** Enterprise production architecture for complex multi-agent workflows. ([CrewAI](https://www.crewai.com/open-source))

### AutoGen / Microsoft Agent Framework

- **A2A Protocol:** Agent-to-Agent communication standard (originated at Google, donated to Linux Foundation). Enables cross-framework agent interoperability. ([A2A Protocol](https://a2a-protocol.org/latest/))
- **Group chat:** Multiple agents participate in structured conversations. ([AutoGen Multi-Agent Patterns](https://sparkco.ai/blog/deep-dive-into-autogen-multi-agent-patterns-2025))
- **Orchestration patterns:** Sequential, concurrent, and group chat coordination. ([AutoGen GitHub](https://github.com/microsoft/autogen))
- **Debate and reflection:** Experimental orchestration patterns for agent deliberation. ([Microsoft Agent Framework Blog](https://cloudsummit.eu/blog/microsoft-agent-framework-production-ready-convergence-autogen-semantic-kernel))
- **Agent Cards:** Dynamic capability discovery via A2A Agent Cards. ([A2A Protocol](https://a2a-protocol.org/latest/))

---

## F. Developer Experience

### Claude Agent SDK

- **API surface:** Minimal. Single `query()` function with `ClaudeAgentOptions`. Two lines to first working agent. ([SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview))
- **Documentation:** Comprehensive official docs with code examples in both Python and TypeScript. Detailed security deployment guide. ([Anthropic Docs](https://platform.claude.com/docs/en/agent-sdk/overview))
- **Getting-started friction:** Low. Install SDK, set API key, call `query()`. Built-in tools work immediately without implementation.
- **Solo developer friendly:** Excellent. Code-forward approach, no infrastructure requirements beyond API key.
- **Community:** Growing ecosystem with 100+ community subagents. Claude Developers Discord. ([awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents))
- **Language support:** Python and TypeScript.

### OpenAI Agents SDK

- **API surface:** Minimal abstractions. Agents, Handoffs, Guardrails as core primitives. ([OpenAI Agents SDK](https://openai.github.io/openai-agents-python/))
- **Documentation:** Strong official docs with cookbook examples. Active community contributions. ([OpenAI Cookbook](https://cookbook.openai.com/topic/agents))
- **Getting-started friction:** Very low. Python-first with automatic schema generation from type hints.
- **Solo developer friendly:** Excellent. Lightweight framework with minimal boilerplate.
- **Community:** Large OpenAI developer community. Provider-agnostic design attracts broad adoption.
- **Language support:** Python and JavaScript/TypeScript.

### LangGraph

- **API surface:** More complex. Requires understanding of graph concepts (nodes, edges, state, channels, checkpointers). ([LangGraph GitHub](https://github.com/langchain-ai/langgraph))
- **Documentation:** Extensive but sprawling across LangChain/LangGraph/LangSmith. Can be overwhelming.
- **Getting-started friction:** Moderate to high. Graph-based mental model takes time to internalize.
- **Solo developer friendly:** Moderate. More infrastructure overhead (LangSmith for observability).
- **Community:** Largest ecosystem. 93k+ GitHub stars for LangChain. Annual Interrupt conference. ([LangChain Blog](https://blog.langchain.com/interrupt-2025-recap/))
- **Language support:** Python and JavaScript.

### CrewAI

- **API surface:** Intuitive role-based metaphor. Define agents with roles, goals, and backstories. ([CrewAI](https://www.crewai.com/))
- **Documentation:** Clean, focused. AWS has published prescriptive guidance. ([AWS CrewAI Guide](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/crewai.html))
- **Getting-started friction:** Low. Role metaphor is immediately understandable.
- **Solo developer friendly:** Good. Simple setup but scaling requires more infrastructure planning.
- **Community:** Active community forum. Growing but smaller than LangChain/OpenAI ecosystems.
- **Language support:** Python only (no TypeScript SDK).

### AutoGen / Microsoft Agent Framework

- **API surface:** Moderate complexity. Async-first, event-driven architecture. APIs in transition from AutoGen to unified framework. ([AutoGen GitHub](https://github.com/microsoft/autogen))
- **Documentation:** In flux due to framework convergence. Migration guides available. ([Microsoft Agent Framework Docs](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview))
- **Getting-started friction:** Moderate. Framework convergence creates temporary documentation confusion.
- **Solo developer friendly:** Moderate. Enterprise-oriented design can feel heavy for small projects.
- **Community:** Strong Microsoft developer community. Academic research backing.
- **Language support:** Python and .NET (C#). Java support in Semantic Kernel.

---

## G. Production Readiness

### Claude Agent SDK

- **Maturity:** High. Powers Claude Code, which is used in production by thousands of developers. Renamed from "Claude Code SDK" to reflect broader scope. ([SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview))
- **Known issues:** TypeScript SDK has more hook types than Python SDK. Some hooks (SessionStart, SessionEnd, Notification) are TypeScript-only. ([Hooks Docs](https://platform.claude.com/docs/en/agent-sdk/hooks))
- **Enterprise adoption:** Growing. Multi-cloud support (Anthropic direct, AWS Bedrock, Google Vertex AI, Azure Foundry).
- **Deployment:** Container-based with detailed production hardening guides. ([Secure Deployment Docs](https://platform.claude.com/docs/en/agent-sdk/secure-deployment))
- **License:** Anthropic Commercial Terms of Service (proprietary). ([SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview))
- **Cost model:** API usage-based (per-token). SDK itself is free.

### OpenAI Agents SDK

- **Maturity:** High. Successor to Swarm framework. Powers Codex. Released March 2025. ([OpenAI Blog](https://openai.com/index/new-tools-for-building-agents/))
- **Known issues:** Relatively new; evolving rapidly. AgentKit adds managed hosting but at the cost of data control.
- **Enterprise adoption:** Strong via OpenAI enterprise relationships.
- **Deployment:** Self-hosted or via OpenAI managed infrastructure.
- **License:** MIT (open source). ([OpenAI Agents SDK GitHub](https://github.com/openai/openai-agents-python))
- **Cost model:** SDK is free. Model usage fees + tool fees (Code Interpreter $0.03/session, File Search $0.10/GB/day). ([OpenAI Pricing](https://platform.openai.com/docs/pricing))

### LangGraph

- **Maturity:** High. LangGraph Platform reached standard accessibility May 2025. Large production user base. ([LangChain](https://www.langchain.com/langgraph))
- **Known issues:** CVE-2025-68664 was a critical vulnerability in langchain-core. Ecosystem complexity can create dependency management challenges. ([Cyata Blog](https://cyata.ai/blog/langgrinch-langchain-core-cve-2025-68664/))
- **Enterprise adoption:** Strong. LangSmith available on AWS Marketplace. Self-hosted and BYOC options. ([AWS Marketplace LangSmith](https://aws.amazon.com/marketplace/pp/prodview-vmzygmggk4gms))
- **Deployment:** LangGraph Platform (managed), self-hosted, BYOC.
- **License:** LangGraph is MIT. LangSmith is proprietary SaaS.
- **Cost model:** Developer tier free. Plus $39/seat/month. Enterprise custom. Usage: $0.001/node execution, traces from $2.50/1k. ([LangSmith Pricing](https://www.langchain.com/pricing))

### CrewAI

- **Maturity:** Growing. Open-source core is stable. Enterprise tier (AMP) adds governance. ([CrewAI](https://www.crewai.com/))
- **Known issues:** Docker-in-Docker code execution bugs. Python-only limits adoption. ([GitHub Issue #3028](https://github.com/crewAIInc/crewAI/issues/3028))
- **Enterprise adoption:** Growing via AWS partnership. HIPAA and SOC2 compliant (Enterprise). ([AWS CrewAI Guide](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/crewai.html))
- **Deployment:** Self-hosted or CrewAI AMP (cloud/on-premise).
- **License:** Apache 2.0 (open source). ([CrewAI GitHub](https://github.com/crewAIInc/crewAI))
- **Cost model:** Open-source core is free. AMP enterprise pricing on request.

### AutoGen / Microsoft Agent Framework

- **Maturity:** Transitioning. AutoGen in maintenance mode. Microsoft Agent Framework in public preview (Oct 2025), GA target Q1 2026. ([VentureBeat](https://venturebeat.com/ai/microsoft-retires-autogen-and-debuts-agent-framework-to-unify-and-govern))
- **Known issues:** Framework convergence creates migration burden. Two codebases merging creates temporary instability. ([AutoGen Update Discussion](https://github.com/microsoft/autogen/discussions/7066))
- **Enterprise adoption:** Strong via Azure ecosystem. Finance, manufacturing, and customer support early adopters. ([Microsoft Agent Framework Blog](https://devblogs.microsoft.com/foundry/introducing-microsoft-agent-framework-the-open-source-engine-for-agentic-ai-apps/))
- **Deployment:** Azure AI Foundry (managed) or self-hosted.
- **License:** MIT (open source). ([AutoGen GitHub](https://github.com/microsoft/autogen))
- **Cost model:** Framework is free. Azure Foundry Agent Service has managed runtime costs.

---

## Decision Framework

### If your priority is... choose:

| Priority | Recommended Framework | Rationale |
|----------|----------------------|-----------|
| **Maximum security & sandboxing** | Claude Agent SDK | OS-level sandboxing, defense-in-depth documentation, proxy-based credential isolation, PreToolUse deny-first evaluation. No other framework matches the depth of its security deployment guide. |
| **Lightweight multi-agent handoffs** | OpenAI Agents SDK | Purpose-built handoff primitive with context preservation. Minimal abstractions. MIT license. Provider-agnostic. |
| **Complex stateful workflows** | LangGraph | Graph-based orchestration with checkpointing, time travel, and fault tolerance. LangSmith provides the most mature observability platform. |
| **Team-based agent collaboration** | CrewAI | Role-based metaphor is the most intuitive for multi-agent teams. Sequential/hierarchical/consensus processes match real organizational structures. |
| **Enterprise governance & compliance** | Microsoft Agent Framework | Azure Entra, native OTel, responsible AI features, A2A interoperability. Best for Azure-native organizations. |
| **Model flexibility & avoiding lock-in** | OpenAI Agents SDK or LangGraph | Both are fully model-agnostic. Claude Agent SDK is locked to Claude models. |
| **Solo developer / fastest start** | Claude Agent SDK or OpenAI Agents SDK | Both offer 2-3 line getting-started experiences. Claude SDK has richer built-in tools; OpenAI SDK has simpler abstractions. |
| **Open-source with no proprietary dependencies** | CrewAI (Apache 2.0) or OpenAI Agents SDK (MIT) | Fully open-source with no proprietary SaaS dependencies for core functionality. |
| **Voice / realtime agents** | OpenAI Agents SDK | Only framework with built-in realtime agent support including interruption detection. |
| **Self-managing AI assistant platform** | Claude Agent SDK | Built-in tools (Read, Write, Edit, Bash, Glob, Grep), skills system, CLAUDE.md memory, session resume, subagent orchestration. Closest to a self-managing platform out of the box. |

---

## Framework-Specific Strengths and Weaknesses

### Claude Agent SDK

**Strengths:**
- Deepest security model of any framework (OS-level sandboxing, hook-based RBAC, proxy credential isolation)
- Built-in tools eliminate need to implement file operations, search, and command execution
- Session resume and fork capabilities enable long-running autonomous workflows
- MCP creator advantage: first-class protocol support with the largest MCP ecosystem
- Skills and CLAUDE.md provide a self-managing knowledge layer

**Weaknesses:**
- Model lock-in to Claude (Anthropic, Bedrock, Vertex, Azure Foundry only)
- Proprietary license (Anthropic Commercial Terms of Service)
- Python SDK has fewer hook types than TypeScript SDK
- No built-in OpenTelemetry; requires community wrappers
- No peer-to-peer agent communication; hierarchical only

### OpenAI Agents SDK

**Strengths:**
- Lightest abstraction layer; minimal learning curve
- Provider-agnostic (100+ LLMs via compatible APIs)
- Handoff primitive is elegant and well-designed
- MIT license, fully open source
- Built-in tracing with dashboard
- Voice/realtime agent support

**Weaknesses:**
- No OS-level sandboxing (Codex sandbox is cloud-only)
- Guardrails are input/output only; no PreToolUse intercept pattern
- No built-in tools for file operations; must implement or use MCP
- Younger ecosystem (released March 2025)
- AgentKit (managed hosting) reduces data control

### LangGraph

**Strengths:**
- Most flexible orchestration model (arbitrary graph topologies)
- Checkpointing enables time travel, fault tolerance, and human-in-the-loop
- LangSmith is the most mature LLM observability platform
- Bidirectional OTel integration
- Largest community and ecosystem

**Weaknesses:**
- Steepest learning curve; graph concepts are non-trivial
- Critical security vulnerability history (CVE-2025-68664)
- No built-in sandboxing; must integrate external solutions
- Ecosystem complexity creates dependency management challenges
- LangSmith costs can scale quickly ($2.50-$5.00 per 1k traces)

### CrewAI

**Strengths:**
- Most intuitive multi-agent metaphor (roles, goals, crews)
- Task-scoped tool access provides fine-grained least-privilege
- Enterprise RBAC with HIPAA/SOC2 compliance
- Apache 2.0 license
- AWS partnership with Bedrock integration
- Clean, focused documentation

**Weaknesses:**
- Python-only (no TypeScript/JavaScript SDK)
- Docker-in-Docker code execution bugs
- Smaller community than LangChain or OpenAI ecosystems
- Enterprise features (AMP) are proprietary
- No built-in sandboxing beyond CodeInterpreter Docker container

### AutoGen / Microsoft Agent Framework

**Strengths:**
- A2A protocol enables cross-framework agent interoperability
- Native OpenTelemetry (contributed to the OTel standard for agents)
- Azure ecosystem integration (Entra, Key Vault, Monitor, Content Safety)
- Responsible AI features (task adherence, prompt shields, PII detection)
- Most comprehensive enterprise compliance (SOC2, ISO 27001, HIPAA)
- Multi-language support (Python, .NET, Java)

**Weaknesses:**
- Framework in transition; AutoGen entering maintenance mode
- Migration burden from AutoGen to Microsoft Agent Framework
- Documentation in flux during convergence
- GA timeline uncertainty (target Q1 2026 for MAF 1.0)
- Azure-centric; self-hosted path is less documented
- Heavier framework for simple use cases

---

## Relevance to DexAI Architecture

DexAI currently uses the Claude Agent SDK as its primary agent infrastructure. Based on this analysis:

**Current positioning is strong because:**
1. DexAI's ADHD-focused design benefits from Claude Agent SDK's built-in tools (no implementation overhead for file operations, search, command execution)
2. The PreToolUse hook system maps directly to DexAI's security pipeline (bash security, file path validation, audit logging in `tools/agent/hooks.py`)
3. Subagent architecture enables DexAI's ADHD subagents (task-decomposer, energy-matcher, commitment-tracker, friction-solver)
4. Session management enables context continuity across the SessionManager
5. MCP provides the extensibility layer for DexAI's custom tools (memory, tasks, ADHD communication)
6. The security deployment guide aligns with DexAI's Docker-based deployment

**Potential gaps to monitor:**
1. **Model lock-in:** If multi-provider model routing becomes critical, consider OpenAI Agents SDK or LangGraph as orchestration layers with Claude Agent SDK as the primary executor
2. **Observability:** DexAI's hook-based approach works but lacks standardized OTel integration; consider adding `claude_telemetry` or Langfuse
3. **Multi-agent interoperability:** A2A protocol adoption could be valuable if DexAI needs to interact with agents built on other frameworks
4. **Peer-to-peer agents:** Claude Agent SDK's hierarchical-only subagent model may be limiting for future complex multi-agent scenarios

---

## Sources

All claims are sourced from 2025-2026 publications unless noted otherwise.

### Claude Agent SDK
- [Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview) - Anthropic, 2025
- [Hooks Documentation](https://platform.claude.com/docs/en/agent-sdk/hooks) - Anthropic, 2025
- [Secure Deployment Guide](https://platform.claude.com/docs/en/agent-sdk/secure-deployment) - Anthropic, 2025
- [MCP Documentation](https://platform.claude.com/docs/en/agent-sdk/mcp) - Anthropic, 2025
- [Claude Code Sandboxing Blog](https://www.anthropic.com/engineering/claude-code-sandboxing) - Anthropic Engineering, 2025
- [Building Agents with Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk) - Anthropic Engineering, 2025
- [Subagents Documentation](https://platform.claude.com/docs/en/agent-sdk/subagents) - Anthropic, 2025
- [Claude Agent SDK Python GitHub](https://github.com/anthropics/claude-agent-sdk-python) - Anthropic
- [Claude Agent SDK TypeScript GitHub](https://github.com/anthropics/claude-agent-sdk-typescript) - Anthropic
- [Langfuse Claude Agent SDK Integration](https://langfuse.com/integrations/frameworks/claude-agent-sdk) - Langfuse, 2025
- [claude_telemetry GitHub](https://github.com/TechNickAI/claude_telemetry) - Community, 2025
- [Claude Code Sandbox InfoQ](https://www.infoq.com/news/2025/11/anthropic-claude-code-sandbox/) - InfoQ, Nov 2025
- [Sub-Agent Best Practices](https://claudefa.st/blog/guide/agents/sub-agent-best-practices) - ClaudeFast, 2025

### OpenAI Agents SDK
- [OpenAI Agents SDK Documentation](https://openai.github.io/openai-agents-python/) - OpenAI, 2025
- [OpenAI Agents SDK GitHub](https://github.com/openai/openai-agents-python) - OpenAI
- [Tracing Documentation](https://openai.github.io/openai-agents-python/tracing/) - OpenAI, 2025
- [Handoffs Documentation](https://openai.github.io/openai-agents-python/handoffs/) - OpenAI, 2025
- [New Tools for Building Agents](https://openai.com/index/new-tools-for-building-agents/) - OpenAI, March 2025
- [OpenAI Codex Security](https://developers.openai.com/codex/security/) - OpenAI, 2025
- [OpenAI for Developers 2025](https://developers.openai.com/blog/openai-for-developers-2025/) - OpenAI, 2025
- [Introducing AgentKit](https://openai.com/index/introducing-agentkit/) - OpenAI, 2025

### LangGraph
- [LangGraph Product Page](https://www.langchain.com/langgraph) - LangChain, 2025
- [LangGraph GitHub](https://github.com/langchain-ai/langgraph) - LangChain
- [LangSmith Observability](https://www.langchain.com/langsmith/observability) - LangChain, 2025
- [LangSmith Pricing](https://www.langchain.com/pricing) - LangChain, 2025
- [LangGraph Persistence Docs](https://docs.langchain.com/oss/python/langgraph/persistence) - LangChain, 2025
- [LangChain Security Policy](https://docs.langchain.com/oss/python/security-policy) - LangChain, 2025
- [LangChain Sandbox GitHub](https://github.com/langchain-ai/langchain-sandbox) - LangChain, 2025
- [CVE-2025-68664 LangGrinch](https://cyata.ai/blog/langgrinch-langchain-core-cve-2025-68664/) - Cyata, 2025
- [Interrupt 2025 Recap](https://blog.langchain.com/interrupt-2025-recap/) - LangChain Blog, 2025
- [LangGraph & MCP Integration](https://healthark.ai/orchestrating-multi-agent-systems-with-lang-graph-mcp/) - HealthArk AI, 2025
- [AWS Marketplace LangSmith](https://aws.amazon.com/marketplace/pp/prodview-vmzygmggk4gms) - AWS, 2025

### CrewAI
- [CrewAI Website](https://www.crewai.com/) - CrewAI, 2025
- [CrewAI GitHub](https://github.com/crewAIInc/crewAI) - CrewAI
- [CrewAI MCP Documentation](https://docs.crewai.com/en/mcp/overview) - CrewAI, 2025
- [CrewAI RBAC Documentation](https://docs.crewai.com/en/enterprise/features/rbac) - CrewAI, 2025
- [CrewAI Code Interpreter Docs](https://docs.crewai.com/en/tools/ai-ml/codeinterpretertool) - CrewAI, 2025
- [CrewAI Changelog](https://docs.crewai.com/en/changelog) - CrewAI, 2025
- [CrewAI Tools GitHub](https://github.com/crewAIInc/crewAI-tools) - CrewAI
- [CrewAI Docker Issue #3028](https://github.com/crewAIInc/crewAI/issues/3028) - GitHub, 2025
- [AWS CrewAI Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/crewai.html) - AWS, 2025
- [CrewAI Platform Evolution Blog](https://blog.crewai.com/how-crewai-is-evolving-beyond-orchestration-to-create-the-most-powerful-agentic-ai-platform/) - CrewAI Blog, 2025

### AutoGen / Microsoft Agent Framework
- [AutoGen GitHub](https://github.com/microsoft/autogen) - Microsoft
- [Microsoft Agent Framework Overview](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview) - Microsoft Learn, 2025
- [Introducing Microsoft Agent Framework](https://devblogs.microsoft.com/foundry/introducing-microsoft-agent-framework-the-open-source-engine-for-agentic-ai-apps/) - Microsoft Foundry Blog, Oct 2025
- [AutoGen Tracing Docs](https://microsoft.github.io/autogen/stable//user-guide/agentchat-user-guide/tracing.html) - AutoGen, 2025
- [AutoGen OpenTelemetry Docs](https://microsoft.github.io/autogen/stable//user-guide/core-user-guide/framework/telemetry.html) - AutoGen, 2025
- [Microsoft Agent Framework Observability](https://learn.microsoft.com/en-us/agent-framework/tutorials/agents/enable-observability) - Microsoft Learn, 2025
- [AutoGen Update Discussion](https://github.com/microsoft/autogen/discussions/7066) - GitHub, 2025
- [Microsoft Retires AutoGen - VentureBeat](https://venturebeat.com/ai/microsoft-retires-autogen-and-debuts-agent-framework-to-unify-and-govern) - VentureBeat, 2025
- [European AI Summit: MAF Convergence](https://cloudsummit.eu/blog/microsoft-agent-framework-production-ready-convergence-autogen-semantic-kernel) - European Cloud Summit, 2025
- [Visual Studio Magazine: SK + AutoGen](https://visualstudiomagazine.com/articles/2025/10/01/semantic-kernel-autogen--open-source-microsoft-agent-framework.aspx) - Visual Studio Magazine, Oct 2025
- [Microsoft AutoGen Executive Guide](https://www.baytechconsulting.com/blog/microsoft-autogen) - BayTech Consulting, 2025

### Semantic Kernel
- [Semantic Kernel Overview](https://learn.microsoft.com/en-us/semantic-kernel/overview/) - Microsoft Learn, 2025
- [Semantic Kernel Blog](https://devblogs.microsoft.com/semantic-kernel/) - Microsoft, 2025
- [SK and MAF Announcement](https://devblogs.microsoft.com/semantic-kernel/semantic-kernel-and-microsoft-agent-framework/) - Microsoft, 2025

### Cross-Framework & Industry
- [A2A Protocol](https://a2a-protocol.org/latest/) - Linux Foundation, 2025
- [A2A Protocol IBM](https://www.ibm.com/think/topics/agent2agent-protocol) - IBM, 2025
- [OpenTelemetry AI Agent Observability](https://opentelemetry.io/blog/2025/ai-agent-observability/) - OpenTelemetry, 2025
- [Agent Sandbox Kubernetes](https://www.infoq.com/news/2025/12/agent-sandbox-kubernetes/) - InfoQ, Dec 2025
- [Top 9 AI Agent Frameworks Feb 2026](https://www.shakudo.io/blog/top-9-ai-agent-frameworks) - Shakudo, 2026
- [AI Agent Frameworks Comparison - Turing](https://www.turing.com/resources/ai-agent-frameworks) - Turing, 2025
- [Developer's Guide to Agentic Frameworks 2026](https://pub.towardsai.net/a-developers-guide-to-agentic-frameworks-in-2026-3f22a492dc3d) - Towards AI, Dec 2025
- [Agent Orchestration 2026 Guide](https://iterathon.tech/blog/ai-agent-orchestration-frameworks-2026) - Iterathon, 2026
- [Docker Sandboxes Blog](https://www.docker.com/blog/docker-sandboxes-run-claude-code-and-other-coding-agents-unsupervised-but-safely/) - Docker, 2025
- [5 Code Sandboxes for AI Agents](https://www.kdnuggets.com/5-code-sandbox-for-your-ai-agents) - KDnuggets, 2025
- [OpenAI AgentKit vs Claude Agent SDK](https://blog.getbind.co/2025/10/07/openai-agentkit-vs-claude-agents-sdk-which-is-better/) - Bind AI, Oct 2025
- [AI Framework Comparison 2025](https://enhancial.substack.com/p/choosing-the-right-ai-framework-a) - Enhancial, 2025
