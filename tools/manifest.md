# Tools Manifest

Master list of all available tools. Check here before creating new scripts.

---

## Memory Tools (`tools/memory/`)

| Tool | Description |
|------|-------------|
| `memory_db.py` | Database operations for memory entries (CRUD, search) |
| `memory_read.py` | Read memory context (MEMORY.md, logs, recent entries) |
| `memory_write.py` | Write entries to memory (facts, events, preferences) |
| `embed_memory.py` | Generate embeddings for memory entries |
| `semantic_search.py` | Vector-based semantic search across memory |
| `hybrid_search.py` | Combined keyword + semantic search (best results) |
| `migrate_db.py` | Database schema migration tool |

---

## Security Tools (`tools/security/`)

| Tool | Description |
|------|-------------|
| `audit.py` | Append-only security event logging for forensics and compliance |
| `vault.py` | Encrypted secrets storage with AES-256-GCM encryption |
| `sanitizer.py` | Input validation, HTML stripping, and prompt injection detection |
| `ratelimit.py` | Token bucket rate limiting with cost tracking |
| `session.py` | Session management with secure tokens and idle timeout |
| `permissions.py` | Role-based access control (RBAC) with 5 default roles |

---

## Channel Tools (`tools/channels/`)

| Tool | Description |
|------|-------------|
| `models.py` | Canonical data structures for cross-platform messaging (UnifiedMessage, Attachment, ChannelUser) |
| `inbox.py` | Message storage, cross-channel identity linking, and user preferences |
| `router.py` | Central message routing hub with integrated security pipeline |
| `gateway.py` | WebSocket server for real-time communication backbone |
| `telegram.py` | Telegram bot adapter using python-telegram-bot (polling mode) |
| `discord.py` | Discord bot adapter using discord.py (slash commands) |
| `slack.py` | Slack app adapter using slack-bolt (Socket Mode) |

---

## Shell Scripts (`scripts/`)

| Script | Description |
|--------|-------------|
| `claude-tasks.sh` | Shell helpers for Claude Code task system — aliases for init, status, clear |

---

*Update this manifest when adding new tools.*
