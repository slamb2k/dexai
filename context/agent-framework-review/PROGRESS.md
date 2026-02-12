# Agent Framework Review — Progress Tracker

> **Last updated:** 2026-02-12
> **Total findings across 6 reviews:** ~174 distinct items
> **Completed:** ~50 items | **Remaining:** ~71 actionable items | **Accepted risk:** ~9 items

**Source documents** (relative to `context/agent-framework-review/`):

| Alias | File | Focus |
|-------|------|-------|
| **01** | `01-core-architecture-review.md` | GOTCHA framework, SDK integration, module dependencies |
| **02** | `02-installation-deployment-review.md` | Docker, deployment, environment setup |
| **03** | `03-sandbox-security-review.md` | Runtime security, tool isolation, OWASP coverage |
| **04** | `04-session-state-review.md` | Session management, state persistence |
| **05** | `05-extensibility-integrations-review.md` | MCP tools, skills, OAuth, extensibility |
| **06** | `06-observability-operations-review.md` | Monitoring, logging, audit, operations |

**How to use source refs:** Each item includes a `Source` column with `file:lines` format. Build agents should read only the referenced lines for full context on that item.

---

## Completed Work

### PR #87 — Single-Tenant Simplification (2026-02-10)
**Impact:** 30 files changed, +627/-2,091 lines (net -1,460 lines)

| ID | Item | Source |
|----|------|--------|
| WS-1 | Memory user_id global storage (mitigated by single-tenant model) | `04:645` |
| WS-2 | hybrid_search.py queries without user filtering (mitigated) | `04:647` |
| — | Remove ChannelUser, PairingCode, identity_links (dead code) | `04:426-433` |
| — | Simplify workspace to single directory | `04:432-433, 655` |
| — | Replace user_id threading with OWNER_USER_ID constant (~50 sigs) | `04:306-361` |
| — | Drop pairing system, channel_users mapping | `04:427-431` |
| — | ~40 of 52 multi-tenancy abstractions removed/simplified | `04:435-451` |

### PR #90 — Security Hardening Quick Wins (2026-02-12)
**Impact:** 12 files changed, +263/-34 lines

| ID | Item | Source |
|----|------|--------|
| V-3/S-1 | Set `allow_unsandboxed_commands: false` | `03:152, 352, 436` |
| V-2/SC-2 | Remove `skip_verification` bypass from package installation | `03:284, 351, 437` |
| V-6/CI-3 | Remove vault CLI plaintext secret output | `03:237, 360, 440` |
| SR-1 | Dashboard authentication middleware (session + Bearer token) | `02:427-441` |
| SR-2 | Bind Docker ports to 127.0.0.1 only | `02:443-453` |
| OBS-P0-1 | Trace ID propagation through pipeline | `06:403-409` |
| OBS-P0-2 | Enable Langfuse tracing (conditional on env vars) | `06:410-415` |
| V-5 (partial) | Scoped vault `inject_env()` with optional `keys` parameter | `03:236, 359, 451` |

### PR #91 — Tier 1 Security Hardening (2026-02-12)
**Impact:** 4 files changed, +539/-47 lines

| ID | Item | Source |
|----|------|--------|
| V-1/PI-2 | Tool output sanitization — 3-layer PostToolUse hook (CVSS 9.3) | `03:205, 350, 449` |
| V-11/S-2 | Remove `docker` from sandbox excluded_commands | `03:153, 365, 439` |
| V-15/S-8 | Symlink resolution — resolve ALL paths before protected check | `03:173, 374, 441` |
| V-18/CI-5 | Block `.env` file reads via agent hook | `03:239, 377, 442` |
| V-16/S-7 | Expand protected paths: `/tmp/`, `/dev/` | `03:172, 375, 443` |
| V-8/S-12 | Workspace restriction enforcement (extensions, file size, total size) | `03:184, 362, 452` |
| V-9/N-4 | Office tool account ownership validation (fail-closed) | `03:263, 363, 453` + `05:295` |
| OAUTH-4 | Email content sanitization with isolation markers | `05:295, 405-415` |

### PR #65–67 — Workspace Isolation & Package Security (2026-02-02–04)

| ID | Item | Source |
|----|------|--------|
| S-10 (partial) | Per-user workspace directories with scope policies | `03:182` |
| — | Path traversal detection in hooks.py | `03:173` |
| — | Package security: PyPI validation, typosquatting, blocklist | `03:283-288` |

### PR #93 — Tier 2 Security Hardening (2026-02-12)
**Impact:** 8 files changed — egress filtering, bash AST parsing, PKCE, per-tool MCP auth, env sanitization, medium-risk blocking

| ID | Item | Source |
|----|------|--------|
| V-4/N-1/N-2 | Egress filtering — domain allowlist for WebFetch/WebSearch (CVSS 8.5) | `03:255-256, 358, 450` |
| V-7/S-6 | Bash AST parsing via bashlex with regex fallback (CVSS 7.8) | `03:171, 361, 454` |
| V-14/PI-1 | Sanitizer medium-risk patterns now blocked (CVSS 6.5) | `03:204, 373` |
| V-12/SC-6 | Package install environment sanitized (CVSS 7.0) | `03:288, 366` |
| OAUTH-1 | PKCE (S256) added to OAuth authorization + token exchange | `05:292, 397-403` |
| MCP-1 | Per-tool MCP authorization replaces wildcard `mcp__dexai__*` | `05:172-174, 417-428` |

### PR #94 — Tier 3 Architecture + Tier 4 Observability & Operations (2026-02-12)
**Impact:** 15 files modified, 3 new modules created — migration framework, structured logging, consolidated audit, memory auditing, hook metrics persistence, cost tracking, budget alerting, SQLite backup

| ID | Item | Source |
|----|------|--------|
| OPS-3 | Database migration framework (forward-only, numbered SQL files) | `06:287-293, 467-471` |
| OBS-P0-3/LOG-1 | Structured JSON logging via structlog wrapping stdlib | `06:81-82, 416-421` |
| OBS-P1-4/AUDIT-2 | Consolidated dual audit trail into single source (security/audit.py) | `06:130-147, 424-430` |
| OBS-P1-7 | Memory access auditing for all 6 memory MCP tools | `06:114-119, 444-449` |
| OBS-P1-5/LOG-4 | Hook metrics persistence with 60s periodic flush | `06:93-95, 431-437` |
| COST-1 | Persistent per-conversation cost tracking (per-API-call) | `06:175-176, 482` |
| OBS-P1-6/COST-2 | Budget alerting at 80%/95%/100% thresholds (audit + dashboard) | `06:177-178, 437-443` |
| OPS-4/OPS-5 | WAL-safe SQLite backup with gzip compression and retention | `06:295-306, 459-466` |

---

## Remaining Work — By Priority Tier

### Tier 3: Architecture & State (Medium Impact, Medium Effort)

| ID | Item | Severity | Effort | Files | Source |
|----|------|----------|--------|-------|--------|
| AD-1/R-1 | Split `sdk_client.py` (1557 lines) into focused modules | High | Medium | sdk_client.py → 3+ files | `01:441, 512-520` |
| AD-2/R-6 | Extract channel-specific handlers from `sdk_handler.py` | Medium | Medium | sdk_handler.py | `01:442, 567-574` |
| AD-5/R-3 | Migrate session storage from JSON to SQLite | Medium | Low-Medium | session_manager.py | `01:445, 537-543` |
| AD-7/R-2 | Add per-user message queue (asyncio.Lock) | High | Medium | router.py | `01:452, 522-534` |
| WS-3 | Persist Claude Agent SDK session IDs for cross-restart resumption | High | Medium | session_manager.py | `04:131-132, 647` |
| AD-4/R-4 | Add config validation (Pydantic models for args/*.yaml) | Medium | Low | New module | `01:444, 545-556` |
| WS-4 | Crash recovery for extraction queue | Medium | Low | daemon.py | `04:653-654` |

### Tier 4: Observability & Operations — COMPLETED (PR #94)

All 8 items completed. See Completed Work section above.

### Tier 5: Deployment & Ergonomics (Low-Medium Impact, Low Effort)

| ID | Item | Severity | Effort | Files | Source |
|----|------|----------|--------|-------|--------|
| SR-3 | Remove `.env.dev` with real API keys (rotate keys) | High | 15 min | .env.dev | `02:456-467` |
| SR-4 | Stop writing API keys to `.env` during setup | Medium-High | 30 min | setup_flow.py | `02:470-491` |
| FP-5 | Remove `local_certs` hardcoding in Caddyfile | Low | 15 min | Caddyfile | `02:545-558` |
| FP-7 | Remove duplicated `python-telegram-bot` dependency | Low | 5 min | pyproject.toml | `02:574-581` |
| EI-4 | Add systemd hardening directives | Low | 15 min | systemd unit | `02:631-647` |
| EI-5 | Add `.dockerignore` to reduce image size | Low | 10 min | New | `02:650-669` |
| EI-6 | Content-Security-Policy header | Low | 30 min | backend | `02:671-680` |
| AD-9 | Remove dead TUI dependencies (textual, rich ~30MB) | Low | Low | pyproject.toml | `01:454` |
| V-19/S-3 | Fix sandbox default in code (False→True in sdk_client.py:623) | Medium | 1 line | sdk_client.py | `03:154, 378, 438` |

### Tier 6: Advanced / Long-Term (High Impact, High Effort)

| ID | Item | Severity | Effort | Files | Source |
|----|------|----------|--------|-------|--------|
| V-10/S-4 | Container-based execution per user session (OS-level isolation) | High (CVSS 7.2) | Architecture change | Major | `03:155, 364, 461` |
| SC-4 | Package hash pinning / lock file | Medium | ~50 lines | dependency_tools.py | `03:286, 463` |
| V-20/SC-1 | Dynamic malicious package feed (OSV/PyPI advisory API) | Medium | New integration | package_security.py | `03:283, 379, 462` |
| V-24 | Secret rotation mechanism | Low | ~100 lines | vault.py | `03:238, 388, 465` |
| CI-1/V-17 | Vault salt stored as plaintext file | Medium (CVSS 5.5) | Medium | vault.py | `03:235, 376` |
| FP-2 | Rewrite install.sh (1078 lines, complex/fragile) | Medium | 2-3 hours | install.sh | `02:512-522` |
| FP-4 | Database migration framework | Medium | 2-4 hours | New | `02:536-543` |
| FP-6 | Master key rotation (re-encryption logic) | Medium | 2-3 hours | vault.py | `02:561-571` |
| EI-1 | `dexai doctor` diagnostic command | Medium | 3-4 hours | New | `02:585-603` |
| EXT-1 | Skill testing & validation MCP tool | High | High | New | `05:119, 383-395` |
| EXT-2 | Skill versioning & updates | Medium | Medium | Skills system | `05:120, 438-446` |
| OAUTH-2 | Automated token refresh | Medium | Medium | oauth_manager.py | `05:293, 430-436` |
| OBS-P2-11/TRANS-3 | "Show Your Work" mode for transparency | Medium | ~6 hours | New | `06:323-328, 474-479` |
| OBS-P3-13 | Circuit breaker for external APIs (OpenRouter, Anthropic) | Medium | ~4 hours | New | `06:483` |
| OBS-P3-14 | Prometheus-compatible metrics endpoint | Low | ~3 hours | New | `06:484` |
| OBS-P3-16/AUDIT-1 | Hash chain on audit entries (tamper evidence) | Medium | ~4 hours | audit.py | `06:123-128, 486` |
| OBS-P2-8 | Operational runbooks (9 scenarios identified) | High | ~3 hours | docs/ | `06:378-392, 452-457` |

### Items Not Prioritized (Design Limitations / Accepted Risk)

| ID | Item | Rationale | Source |
|----|------|-----------|--------|
| PI-3/V-25 | Backtick regex false positives on code | Low impact, would break legitimate code blocks | `03:206, 389` |
| V-26/S-11 | Workspace key no length limit | Low impact in single-tenant mode | `03:183, 390` |
| PI-4 | Pattern only checks line start | Low severity, mitigated by output sanitization | `03:207` |
| PI-6 | System prompt extraction patterns detection-only | Mitigated by output sanitization V-1 fix | `03:209` |
| PI-7 | No channel-specific attack vector filtering | Medium; channels have their own sanitization | `03:215` |
| AD-13 | Hardcoded message limits per channel | Low; values are correct for each platform | `01:463` |
| V-21 | System prompt contains user data | Accepted; single-tenant, user is the owner | `03:380` |
| V-22/N-3 | DALL-E prompt may contain PII | Medium; user controls their own data | `03:257, 381` |
| V-23/S-5 | Auto-allow bash if sandboxed reduces RBAC | Accepted; ADHD friction reduction tradeoff | `03:156, 382` |

---

## Progress Summary

```
Review 01 (Core Architecture):     3/13 items addressed  (23%)
Review 02 (Installation/Deploy):   2/17 items addressed  (12%)
Review 03 (Sandbox/Security):     23/58 items addressed  (40%)  ← Tier 2 PR
Review 04 (Session/State):         8/12 items addressed  (67%)  ← Single-tenant PR
Review 05 (Extensibility):         4/17 items addressed  (24%)  ← PKCE + MCP auth
Review 06 (Observability):        10/39 items addressed  (26%)  ← Tier 4 PR
                                  ─────────────────────────────
Overall:                          ~50/156 items addressed (32%)
```

### What's been done well
- **All Critical/CVSS 9+ vulnerabilities addressed** (V-1, V-2, V-3)
- **All Tier 1 and Tier 2 security items shipped** (PR #90, #91, #93)
- **Single-tenant simplification** removed ~1,460 lines of unnecessary abstraction
- **Defense-in-depth layers** now include: sandbox, hooks, RBAC, output sanitization, workspace restrictions, egress filtering, AST bash analysis
- **Fail-closed security model** in new code (office tools, workspace hooks, egress filter)
- **OAuth hardened with PKCE (S256)** — code_challenge/code_verifier flow for Google and Microsoft
- **MCP tool access scoped** — per-tool authorization replaces wildcard pattern
- **Full Tier 4 Observability shipped** — structured logging, consolidated audit, cost tracking, budget alerting, migration framework, backup system

### Highest-value next steps
1. **Tier 5 Quick Fixes** — `.env.dev` cleanup (SR-3), sandbox default fix (V-19), dependency dedup (FP-7) are minutes each
2. **Tier 3 Architecture** — `sdk_client.py` split and session SQLite migration reduce maintenance burden
3. **Tier 6 Advanced** — Operational runbooks (OBS-P2-8) and "Show Your Work" mode (OBS-P2-11) build on the new observability foundation

---

## Build Agent Usage

To give a build agent context for a specific item, provide:

```
Read context/agent-framework-review/<file> lines <start>-<end>
```

**Example:** To implement V-4 (egress filtering), an agent needs:
```
Read context/agent-framework-review/03-sandbox-security-review.md lines 255-263   # Finding details
Read context/agent-framework-review/03-sandbox-security-review.md lines 358       # Vulnerability entry
Read context/agent-framework-review/03-sandbox-security-review.md lines 449-455   # Hardening roadmap
```

For items spanning multiple reviews, read the source from each listed file. The first reference is typically the finding detail, subsequent references are the vulnerability rating and remediation guidance.

---

*Generated from cross-referencing 6 review documents against git history (PRs #65–67, #87, #89–91, #93–94).*
