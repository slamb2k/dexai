# **System Handbook: How This Architecture Operates**

## **The GOTCHA Framework**

This system uses the **GOTCHA Framework** — a 6-layer architecture for agentic systems:

**GOT** (The Engine):
- **Goals** (`goals/`) — What needs to happen (process definitions)
- **Orchestration** — The AI manager (you) that coordinates execution
- **Tools** (`tools/`) — Deterministic scripts that do the actual work

**CHA** (The Context):
- **Context** (`context/`) — Reference material and domain knowledge
- **Hard prompts** (`hardprompts/`) — Reusable instruction templates
- **Args** (`args/`) — Behavior settings that shape how the system acts

You're the manager of a multi-layer agentic system. LLMs are probabilistic (educated guesses). Business logic is deterministic (must work the same way every time).
This structure exists to bridge that gap through **separation of concerns**.

---

## **Why This Structure Exists**

When AI tries to do everything itself, errors compound fast.
90% accuracy per step sounds good until you realize that's ~59% accuracy over 5 steps.

The solution:

* Push **reliability** into deterministic code (tools)
* Push **flexibility and reasoning** into the LLM (manager)
* Push **process clarity** into goals
* Push **behavior settings** into args files
* Push **domain knowledge** into the context layer
* Keep each layer focused on a single responsibility

You make smart decisions. Tools execute perfectly.

---

## **Quick Reference: Where to Find Information**

| Need | Location | Purpose |
|------|----------|---------|
| **Product vision & roadmap** | `goals/prd_dexai_v1.md` | Full PRD with personas, features, phases |
| **Phase status & task index** | `goals/manifest.md` | What's done, what's planned, all goal files |
| **Available tools** | `tools/manifest.md` | Every tool with description and location |
| **ADHD design principles** | `context/adhd_design_principles.md` | Core UX philosophy (RSD-safe, one-thing, etc.) |
| **Architecture decisions** | `context/dexai_vs_claude_sdk_comparison.md` | SDK integration rationale |
| **Competitive context** | `context/gap_analysis.md` | Why features exist, market positioning |
| **Security infrastructure** | `tools/security/` | Vault, RBAC, audit, sanitizer, rate limiting |
| **Office integration** | `tools/office/` + `args/office_integration.yaml` | OAuth, email, calendar, automation |
| **Agent SDK config** | `args/agent.yaml` | Model, tools, ADHD settings |
| **Model routing** | `args/routing.yaml` + `tools/agent/model_router/` | OpenRouter integration, complexity-based routing |
| **Deployment** | `docker-compose.yml`, `Dockerfile`, `install.sh` | Docker, Caddy, Tailscale profiles |
| **Environment vars** | `.env.example` | All configurable settings with documentation |

**Use `/prime` to load key architectural context into the conversation.**

---

## **Development Environment**

**Python Version:** 3.11+ (3.12 used in Docker)

**Package Manager:** Always use `uv` (not pip/pip3)
```bash
# Create venv and install dependencies
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,channels]"

# Install specific extras
uv pip install -e ".[telegram]"   # Just Telegram
uv pip install -e ".[all]"        # Everything

# Install memory providers
uv pip install -e ".[memory-providers]"  # Mem0 + Zep

# Install office integrations
uv pip install -e ".[office]"  # Google + Microsoft OAuth
```

**CLI Entry Point:**
```bash
dexai  # Runs tools.cli:main
```

**Key Dependencies:**
- `anthropic` - Claude API client
- `claude-agent-sdk` - Claude Code agent SDK
- `fastapi` + `uvicorn` - Dashboard backend
- `textual` + `rich` - TUI setup wizard
- `httpx` - HTTP client

---

## **Docker Deployment**

**Quick Start:**
```bash
# Core services (backend + frontend)
docker compose up -d

# With Caddy reverse proxy (HTTPS)
docker compose --profile proxy up -d

# With Tailscale VPN
docker compose --profile tailscale up -d
```

**Memory Limits:** (prevent OOM in WSL/constrained environments)
- Backend: 4GB (`mem_limit: 4g`)
- Frontend: 8GB (`mem_limit: 8g`) + `NODE_OPTIONS=--max-old-space-size=4096`

**Required Environment Variables:** (in `.env`)
```bash
# Required
DEXAI_MASTER_KEY=your-secure-password    # Vault encryption
ANTHROPIC_API_KEY=sk-ant-...             # Claude API
OPENAI_API_KEY=sk-...                    # Embeddings

# Optional - channels
TELEGRAM_BOT_TOKEN=...
DISCORD_BOT_TOKEN=...
SLACK_BOT_TOKEN=...

# Optional - deployment
DEXAI_DOMAIN=localhost                   # For Caddy
TAILSCALE_AUTHKEY=tskey-auth-...         # For Tailscale
OPENROUTER_API_KEY=...                   # For model routing

# Optional - additional providers
GOOGLE_API_KEY=...                       # Direct Gemini access
HELICONE_API_KEY=...                     # LLM observability
```

**Volume Mounts:**
- `.claude/` is mounted into the container for agent-created skills persistence

---

## **Intelligent Model Routing**

DexAI uses OpenRouter for multi-provider model routing with complexity-based selection.

**Architecture:**
```
User Request → Local Router (complexity classification)
             → ClaudeAgentOptions.env (model ID)
             → Agent SDK → OpenRouter → Provider
```

**Configuration:** `args/routing.yaml`

**Routing Profiles:**
| Profile | Description |
|---------|-------------|
| `anthropic_only` | Only Anthropic models (default, safest) |
| `quality_first` | Best model per complexity tier |
| `balanced` | Mix providers for cost-quality balance |
| `cost_optimised` | Minimize cost, use budget models |
| `multi_provider` | Best price/performance across all providers |
| `auto_router` | Delegate to OpenRouter's Auto Router |

**Complexity Tiers:** (based on heuristic scoring)
- `trivial` (0-1): Greetings, simple questions → Haiku
- `low` (2-3): Basic requests → Haiku
- `moderate` (4-6): Typical tasks → Sonnet
- `high` (7-10): Complex multi-step → Sonnet + Exacto
- `critical` (11+): Requires best model → Opus

**Key Features:**
- Up to 73% cost savings on simple tasks
- Subagent downscaling for trivial parent tasks
- Exacto for improved tool-calling accuracy
- ADHD-aware routing (energy level, urgency)
- Budget controls (per-session, per-day, per-user limits)

**Documentation:** `tools/agent/model_router/ROUTING_ARCHITECTURE.md`

---

# **The Layered Structure**

## **1. Process Layer — Goals (`goals/`)**

* Task-specific instructions in clear markdown
* Each goal defines: objective, inputs, which tools to use, expected outputs, edge cases
* Written like you're briefing someone competent
* Only modified with explicit permission
* Goals tell the system **what** to achieve, not how it should behave today

---

## **2. Orchestration Layer — Manager (AI Role)**

* Reads the relevant goal
* Decides which tools (scripts) to use and in what order
* Applies args settings to shape behavior
* References context for domain knowledge (voice, ICP, examples, etc.)
* Handles errors, asks clarifying questions, makes judgment calls
* Never executes work — it delegates intelligently
* Example: Don't scrape websites yourself. Read `goals/research_lead.md`, understand requirements, then call `tools/lead_gen/scrape_linkedin.py` with the correct parameters.

---

## **3. Execution Layer — Tools (`tools/`)**

* Python scripts organized by workflow
* Each has **one job**: API calls, data processing, file operations, database work, etc.
* Fast, documented, testable, deterministic
* They don't think. They don't decide. They just execute.
* Credentials + environment variables handled via `.env`
* All tools must be listed in `tools/manifest.md` with a one-sentence description

---

## **4. Args Layer — Behavior (`args/`)**

* YAML/JSON files controlling how the system behaves right now
* Examples: daily themes, frameworks, modes, lengths, schedules, model choices
* Changing args changes behavior without editing goals or tools
* The manager reads args before running any workflow

---

## **5. Context Layer — Domain Knowledge (`context/`)**

* Static reference material the system uses to reason
* Examples: tone rules, writing samples, ICP descriptions, case studies, negative examples
* Shapes quality and style — not process or behavior

---

## **6. Hard Prompts Layer — Instruction Templates (`hardprompts/`)**

* Reusable text templates for LLM sub-tasks
* Example: outline → post, rewrite in voice, summarize transcript, create visual brief
* Hard prompts are fixed instructions, not context or goals

---

# **How to Operate**

### **1. Check for existing goals first**

Before starting a task, check `goals/manifest.md` for a relevant workflow.
If a goal exists, follow it — goals define the full process for common tasks.

---

### **2. Check for existing tools**

Before writing new code, read `tools/manifest.md`.
This is the index of all available tools.

If a tool exists, use it.
If you create a new tool script, you **must** add it to the manifest with a 1-sentence description.

---

### **3. When tools fail, fix and document**

* Read the error and stack trace carefully
* Update the tool to handle the issue (ask if API credits are required)
* Add what you learned to the goal (rate limits, batching rules, timing quirks)
* Example: tool hits 429 → find batch endpoint → refactor → test → update goal
* If a goal exceeds a reasonable length, propose splitting it into a primary goal + technical reference

---

### **4. Treat goals as living documentation**

* Update only when better approaches or API constraints emerge
* Never modify/create goals without explicit permission
* Goals are the instruction manual for the entire system

---

### **5. Communicate clearly when stuck**

If you can't complete a task with existing tools and goals:

* Explain what's missing
* Explain what you need
* Do not guess or invent capabilities

---

### **6. Guardrails — Learned Behaviors**

Document Claude-specific mistakes here (not script bugs—those go in goals):

* Always check `tools/manifest.md` before writing a new script
* Verify tool output format before chaining into another tool
* Don't assume APIs support batch operations—check first
* When a workflow fails mid-execution, preserve intermediate outputs before retrying
* Read the full goal before starting a task—don't skim
* **NEVER DELETE YOUTUBE VIDEOS** — Video deletion is irreversible. The MCP server blocks this intentionally. If deletion is ever truly needed, ask the user 3 times and get 3 confirmations before proceeding. Direct user to YouTube Studio instead.

*(Add new guardrails as mistakes happen. Keep this under 15 items.)*

---

### **7. Git Workflow — Branch Protection Enforced**

**Direct pushes to `main` are blocked.** Branch protection is enabled on GitHub and enforced locally via pre-push hook.

**Required workflow for all changes:**

```
1. SYNC MAIN
   git checkout main
   git pull origin main

2. CREATE FEATURE BRANCH
   git checkout -b feature/descriptive-name
   # Or: fix/bug-name, phase/phase-name, docs/topic

3. MAKE CHANGES & COMMIT IN GROUPS
   # Commit related changes together with detailed messages
   git add <specific-files>
   git commit -m "feat(scope): description

   - Detail 1
   - Detail 2

   Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

4. PUSH TO FEATURE BRANCH
   git push -u origin feature/descriptive-name

5. CREATE PR WITH DETAILS
   gh pr create --title "feat: Title" --body "## Summary
   - Change 1
   - Change 2

   ## Test Plan
   - [ ] Test step 1
   - [ ] Test step 2"

6. FIX BUILD ERRORS
   # If CI fails, fix and push again
   git add . && git commit -m "fix: address CI feedback"
   git push

7. MERGE & CLEANUP
   # Squash merge via GitHub UI or:
   gh pr merge --squash --delete-branch

8. SYNC MAIN FOR NEXT WORK
   git checkout main
   git pull origin main
```

**Commit message conventions:**
- `feat(scope):` — New feature
- `fix(scope):` — Bug fix
- `docs(scope):` — Documentation
- `refactor(scope):` — Code refactoring
- `chore(scope):` — Maintenance tasks
- `phase(N):` — Phase completion

**When to commit:**
- Phase completion
- Security fixes (immediately)
- Bug fixes
- Logical feature groups
- Before switching context

**Branch naming:**
- `feature/add-heartbeat-engine`
- `fix/scheduler-timezone-bug`
- `phase/4-automation`
- `docs/update-readme`

---

### **8. First Run Initialization**

**On first session in a new environment, check if memory infrastructure exists. If not, create it:**

1. Check if `memory/MEMORY.md` exists
2. If missing, this is a fresh environment — initialize:

```bash
# Create directory structure
mkdir -p memory/logs
mkdir -p data

# Create MEMORY.md with default template
cat > memory/MEMORY.md << 'EOF'
# Persistent Memory

> This file contains curated long-term facts, preferences, and context that persist across sessions.
> The AI reads this at the start of each session. You can edit this file directly.

## User Preferences

- (Add your preferences here)

## Key Facts

- (Add key facts about your work/projects)

## Learned Behaviors

- Always check tools/manifest.md before creating new scripts
- Follow GOTCHA framework: Goals, Orchestration, Tools, Context, Hardprompts, Args

## Current Projects

- (List active projects)

## Technical Context

- Framework: GOTCHA (6-layer agentic architecture)

---

*Last updated: (date)*
*This file is the source of truth for persistent facts. Edit directly to update.*
EOF

# Create today's log file
echo "# Daily Log: $(date +%Y-%m-%d)" > "memory/logs/$(date +%Y-%m-%d).md"
echo "" >> "memory/logs/$(date +%Y-%m-%d).md"
echo "> Session log for $(date +'%A, %B %d, %Y')" >> "memory/logs/$(date +%Y-%m-%d).md"
echo "" >> "memory/logs/$(date +%Y-%m-%d).md"
echo "---" >> "memory/logs/$(date +%Y-%m-%d).md"
echo "" >> "memory/logs/$(date +%Y-%m-%d).md"
echo "## Events & Notes" >> "memory/logs/$(date +%Y-%m-%d).md"
echo "" >> "memory/logs/$(date +%Y-%m-%d).md"

# Initialize core databases (they auto-create tables on first connection)
python3 -c "
import sqlite3
from pathlib import Path

data_dir = Path('data')
data_dir.mkdir(exist_ok=True)

# Memory database
conn = sqlite3.connect('data/memory.db')
conn.execute('''CREATE TABLE IF NOT EXISTS memory_entries (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    entry_type TEXT DEFAULT 'fact',
    importance INTEGER DEFAULT 5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()
conn.close()

# Activity/task tracking database
conn = sqlite3.connect('data/activity.db')
conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    source TEXT,
    request TEXT,
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    summary TEXT
)''')
conn.commit()
conn.close()

print('Memory infrastructure initialized!')
"
```

3. Confirm to user: "Memory system initialized. I'll remember things across sessions now."

---

### **9. Memory Protocol**

The system has persistent memory across sessions. At session start, read the memory context:

**Load Memory:**
1. Read `memory/MEMORY.md` for curated facts and preferences
2. Read today's log: `memory/logs/YYYY-MM-DD.md`
3. Read yesterday's log for continuity

```bash
python tools/memory/memory_read.py --format markdown
```

**During Session:**
- Append notable events to today's log: `python tools/memory/memory_write.py --content "event" --type event`
- Add facts to the database: `python tools/memory/memory_write.py --content "fact" --type fact --importance 7`
- For truly persistent facts (always loaded), update MEMORY.md: `python tools/memory/memory_write.py --update-memory --content "New preference" --section user_preferences`

**Search Memory:**
- Keyword search: `python tools/memory/memory_db.py --action search --query "keyword"`
- Semantic search: `python tools/memory/semantic_search.py --query "related concept"`
- Hybrid search (best): `python tools/memory/hybrid_search.py --query "what does user prefer"`

**Memory Types:**
- `fact` - Objective information
- `preference` - User preferences
- `event` - Something that happened
- `insight` - Learned pattern or realization
- `task` - Something to do
- `relationship` - Connection between entities

---

### **10. Task System — Efficient Work Orchestration**

Claude Code has a built-in task system for tracking work across sessions. Use it for any non-trivial work.

**When to Use Tasks:**
- Multi-step implementations (3+ steps)
- Phase-based development (like this project)
- Work that spans multiple sessions
- Complex debugging requiring multiple attempts

**Task Patterns:**

| Pattern | When to Use | Example |
|---------|-------------|---------|
| **Sequential** | Tasks depend on previous output | DB migration → Verify → Build tools |
| **Parallel** | Tasks are independent | Build audit.py, sanitizer.py, ratelimit.py simultaneously |
| **Fan-out** | One task spawns many | "Build security layer" → 6 independent tool tasks |
| **Fan-in** | Many tasks feed one | All adapters complete → Integration testing |

**Execution Rules:**

```
SEQUENTIAL (use blockedBy):
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Task 1  │────▶│ Task 2  │────▶│ Task 3  │
└─────────┘     └─────────┘     └─────────┘
  DB Setup       Migrate         Verify

PARALLEL (no dependencies):
┌─────────┐
│ Task 1  │──┐
└─────────┘  │
┌─────────┐  │  ┌─────────┐
│ Task 2  │──┼─▶│ Final   │
└─────────┘  │  └─────────┘
┌─────────┐  │
│ Task 3  │──┘
└─────────┘
 All independent, run together

FAN-OUT then FAN-IN:
              ┌─────────┐
           ┌─▶│ Sub 1   │──┐
┌────────┐ │  └─────────┘  │  ┌─────────┐
│ Parent │─┤  ┌─────────┐  ├─▶│ Verify  │
└────────┘ │  │ Sub 2   │──┤  └─────────┘
           │  └─────────┘  │
           └─▶┌─────────┐  │
              │ Sub 3   │──┘
              └─────────┘
```

**Task Commands:**
```python
# Create task (always provide activeForm for spinner)
TaskCreate(subject="Build audit logger", description="...", activeForm="Building audit logger")

# Set dependencies (Task 2 waits for Task 1)
TaskUpdate(taskId="2", addBlockedBy=["1"])

# Mark in progress BEFORE starting work
TaskUpdate(taskId="1", status="in_progress")

# Mark complete AFTER verifying success
TaskUpdate(taskId="1", status="completed")

# Check what's available
TaskList()
```

**Best Practices:**
1. Create all tasks upfront for visibility
2. Set dependencies immediately after creation
3. Mark `in_progress` before starting (shows spinner to user)
4. Only mark `completed` after verification passes
5. Use `TaskGet` to read full description before starting
6. Clean up stale tasks periodically

---

# **The Continuous Improvement Loop**

Every failure strengthens the system:

1. Identify what broke and why
2. Fix the tool script
3. Test until it works reliably
4. Update the goal with new knowledge
5. Next time → automatic success

---

# **File Structure**

**Where Things Live:**

* `goals/` — Process Layer (what to achieve)
* `tools/` — Execution Layer (organized by workflow)
* `tools/agent/` — Claude Agent SDK integration (ADHD-aware client, MCP tools)
* `tools/agent/model_router/` — Intelligent model routing (OpenRouter, complexity classification)
* `tools/dashboard/` — Web dashboard (backend: FastAPI, frontend: Next.js)
* `args/` — Args Layer (behavior settings)
* `context/` — Context Layer (domain knowledge)
* `hardprompts/` — Hard Prompts Layer (instruction templates)
* `.tmp/` — Temporary work (scrapes, raw data, intermediate files). Disposable.
* `.claude/` — Claude Code configuration and agent-created skills
* `.env` — API keys + environment variables
* `credentials.json`, `token.json` — OAuth credentials (ignored by Git)
* `goals/manifest.md` — Index of available goal workflows
* `tools/manifest.md` — Master list of tools and their functions
* `args/agent.yaml` — Claude Agent SDK configuration (model, tools, ADHD settings)

---

## **Design Documents & Specs**

**Where design documents live:**

| Type | Location | Purpose |
|------|----------|---------|
| **PRD / Product Spec** | `goals/prd_dexai_v1.md` | Complete product requirements, roadmap, personas |
| **Phase Plans** | `goals/phase{N}_{name}.md` | Tactical implementation guides per phase |
| **Competitive Analysis** | `context/openclaw_research.md` | Deep dive on competitors |
| **Gap Analysis** | `context/gap_analysis.md` | Feature comparison, roadmap justification |
| **Methodologies** | `goals/build_app.md`, `goals/task_orchestration.md` | Reusable workflows |
| **Goals Index** | `goals/manifest.md` | Quick reference to all goals |
| **Tools Index** | `tools/manifest.md` | Master list of all implementations |
| **LLM Templates** | `hardprompts/{category}/` | Reusable instruction templates |

**Summary:**
- `goals/` = WHAT to achieve (specs, PRDs, phase plans)
- `context/` = WHY decisions were made (research, analysis)
- `hardprompts/` = HOW to instruct LLMs (templates)
- `tools/` = Implementations (Python scripts)
- `args/` = Configuration (behavior settings)

---

## **Adding New Features — Checklist**

When implementing a new feature or phase, follow this checklist:

### 1. Create or Update Phase Plan
**Location:** `goals/phase{N}_{name}.md`

Include:
- Objective and prerequisites
- Tools to build (with database schemas, CLI interfaces)
- Implementation order
- Verification checklist

### 2. Update Goals Manifest
**File:** `goals/manifest.md`

Add entry to the goals table and update phase status.

### 3. Build the Tools
**Location:** `tools/{category}/`

Follow existing patterns:
- `__init__.py` with path constants (PROJECT_ROOT, DB_PATH, CONFIG_PATH)
- Each tool has CLI interface + programmatic API
- Returns `{"success": bool, ...}` format
- Database tables created in `get_connection()` function

### 4. Update Tools Manifest
**File:** `tools/manifest.md`

Add one-line description for each new tool.

### 5. Update Permissions (if needed)
**File:** `tools/security/permissions.py`

Add new permission strings to appropriate roles in `DEFAULT_ROLES`.
Also update the database if roles already exist.

### 6. Create Configuration (if needed)
**File:** `args/{feature}.yaml`

Add YAML config with sensible defaults.

### 7. Update PRD (if scope changes)
**File:** `goals/prd_dexai_v1.md`

Update feature list, roadmap, or requirements.

### 8. Commit in Logical Groups
Use conventional commit format: `feat(scope): description`

**Quick Reference Checklist:**
```
□ Phase plan exists in goals/ (or update existing)
□ goals/manifest.md updated
□ Tools built in tools/{category}/
□ tools/manifest.md updated
□ permissions.py updated (if new permissions needed)
□ args/{config}.yaml created (if configurable)
□ Database schema in data/ (if persistent)
□ Commits use conventional format
```

---

## **Deliverables vs Scratch**

* **Deliverables**: outputs needed by the user (Sheets, Slides, processed data, etc.)
* **Scratch Work**: temp files (raw scrapes, CSVs, research). Always disposable.
* Never store important data in `.tmp/`.

---

## **Claude Agent SDK Integration**

DexAI uses the Claude Agent SDK for agentic capabilities while preserving unique ADHD features.

**Architecture:**
```
Telegram/Discord/Slack → Router (security pipeline) → SDK Handler → DexAIClient
                                                           ↓
                                                    Claude Agent SDK
                                                    (Read, Write, Bash, etc.)
                                                           +
                                                    DexAI MCP Tools
                                                    (ADHD-specific features)
```

**Key Components:**

| Component | Location | Purpose |
|-----------|----------|---------|
| DexAIClient | `tools/agent/sdk_client.py` | SDK wrapper with ADHD-aware prompts |
| ModelRouter | `tools/agent/model_router/model_router.py` | Complexity-based routing via OpenRouter |
| Permission callback | `tools/agent/permissions.py` | Maps RBAC to SDK tool access |
| SDK Handler | `tools/channels/sdk_handler.py` | Channel message handler |
| Memory MCP Tools | `tools/agent/mcp/memory_tools.py` | Hybrid search, commitments, context |
| Task MCP Tools | `tools/agent/mcp/task_tools.py` | Decomposition, friction, current step |
| ADHD MCP Tools | `tools/agent/mcp/adhd_tools.py` | Response formatting, language filter |

**What SDK Provides (Use These):**
- File operations: Read, Write, Edit, Glob, Grep, LS
- Command execution: Bash (sandboxed)
- Web access: WebSearch, WebFetch
- Task tracking: TaskCreate, TaskList, TaskUpdate, TaskGet

**What DexAI Adds (Unique Value):**
- Hybrid memory search (BM25 + semantic embeddings)
- Commitment tracking (RSD-safe promise surfacing)
- Context capture/resume (20-45min recovery savings)
- Task decomposition (LLM-powered breakdown)
- Friction solving (pre-solve hidden blockers)
- Current step (ONE action, not lists)
- Energy matching (route tasks to capacity)
- RSD-safe language filtering

**Configuration:** `args/agent.yaml`

---

# **Your Job in One Sentence**

You sit between what needs to happen (goals) and getting it done (tools).
Read instructions, apply args, use context, delegate well, handle failures, and strengthen the system with each run.

Be direct.
Be reliable.
Get shit done.
