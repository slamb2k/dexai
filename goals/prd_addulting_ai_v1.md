# Product Requirements Document (PRD)
# addulting-ai: Personal AI Agent Platform

**Version:** 1.0
**Date:** 2026-02-02
**Status:** Draft
**Owner:** Product Team

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-02 | Product Team | Initial PRD based on OpenClaw gap analysis |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Product Vision & Strategy](#3-product-vision--strategy)
4. [Target Users](#4-target-users)
5. [Security Philosophy](#5-security-philosophy)
6. [Feature Requirements](#6-feature-requirements)
7. [Technical Architecture](#7-technical-architecture)
8. [Release Roadmap](#8-release-roadmap)
9. [Success Metrics](#9-success-metrics)
10. [Risks & Mitigations](#10-risks--mitigations)
11. [Dependencies & Constraints](#11-dependencies--constraints)
12. [Out of Scope](#12-out-of-scope)
13. [Open Questions](#13-open-questions)
14. [Appendices](#14-appendices)

---

## 1. Executive Summary

### 1.1 Product Overview

**addulting-ai** is a security-first, self-hosted AI personal agent that helps users automate their digital lives through natural conversation across messaging platforms they already use.

### 1.2 Key Differentiators

| Differentiator | Description |
|----------------|-------------|
| **Security-First** | Built with security as the foundation, not an afterthought |
| **Channel-Native** | Accessible via WhatsApp, Telegram, Slack, Discord—not another app |
| **Proactive** | Initiates helpful actions, doesn't just respond |
| **Local-First** | Data stays on user's hardware by default |
| **Open & Extensible** | Skills ecosystem with trust levels |

### 1.3 Current State

addulting-ai has a **production-ready persistent memory system** (100% feature parity with OpenClaw) built on the GOTCHA framework. It needs to add messaging channels, system access, and proactive automation to become a complete AI agent platform.

### 1.4 Target Outcome

Transform addulting-ai from a memory backend into a full AI agent that users interact with daily through their existing messaging apps, competing directly with OpenClaw while differentiating on security and trust.

---

## 2. Problem Statement

### 2.1 User Problems

| Problem | Impact | Current Solutions | Gap |
|---------|--------|-------------------|-----|
| AI assistants require switching apps | Friction reduces usage | ChatGPT, Claude web | No messaging integration |
| AI forgets context between sessions | Users repeat themselves | Limited memory in most tools | OpenClaw solves this |
| AI can only advise, not act | Limited utility | Manual execution | OpenClaw has full system access |
| AI waits for prompts | Misses opportunities to help | All reactive | OpenClaw has heartbeat/cron |
| AI agent security is poor | Data/credential exposure | OpenClaw has known vulnerabilities | Opportunity to differentiate |

### 2.2 Market Context

**OpenClaw (formerly Moltbot/Clawdbot)** achieved 144k GitHub stars in days by solving the first four problems. However, security researchers have identified significant vulnerabilities:

- Network exposure risks
- Plain-text credential storage
- Prompt injection vectors
- Supply chain risks from community skills
- Excessive OAuth scope requests

**Opportunity:** Build a security-first alternative that matches OpenClaw's capabilities while addressing its weaknesses.

### 2.3 Why Now

1. **Market validation:** OpenClaw proved demand for personal AI agents
2. **Security concerns:** Enterprise and privacy-conscious users need alternatives
3. **Foundation ready:** addulting-ai memory system is production-ready
4. **Competitive window:** OpenClaw's security issues create opportunity

---

## 3. Product Vision & Strategy

### 3.1 Vision Statement

> **"An AI agent you can trust with your digital life."**

addulting-ai will be the personal AI agent that security-conscious users, developers, and enterprises choose because it prioritizes their safety while delivering the same powerful capabilities as competitors.

### 3.2 Strategic Principles

| Principle | Implication |
|-----------|-------------|
| **Security is a feature** | Security architecture comes before features |
| **Meet users where they are** | Messaging-first, not app-first |
| **Local by default** | Data stays on user hardware unless explicitly shared |
| **Transparency over magic** | Users understand what the agent does and costs |
| **Quality over quantity** | 10 trusted skills > 700 untrusted skills |

### 3.3 Competitive Positioning

```
                    HIGH SECURITY
                         │
                         │
         Enterprise      │     addulting-ai
         Solutions       │     (target)
                         │
    ─────────────────────┼─────────────────────
    LOW                  │                 HIGH
    CAPABILITY           │            CAPABILITY
                         │
         Basic           │     OpenClaw
         Chatbots        │     (current leader)
                         │
                    LOW SECURITY
```

### 3.4 Go-to-Market Strategy

**Phase 1: Developer Early Adopters**
- Target: Developers frustrated with OpenClaw security
- Channel: GitHub, Hacker News, dev communities
- Message: "The secure OpenClaw alternative"

**Phase 2: Privacy-Conscious Users**
- Target: Users who want AI but distrust cloud services
- Channel: Privacy forums, self-hosted communities
- Message: "Your AI agent, your hardware, your data"

**Phase 3: Enterprise Teams**
- Target: Teams needing AI automation with compliance
- Channel: Direct sales, enterprise channels
- Message: "AI agents with audit trails and access controls"

---

## 4. Target Users

### 4.1 Primary Persona: The Security-Conscious Developer

**Name:** Alex
**Role:** Senior Software Engineer
**Age:** 32

**Context:**
- Tried OpenClaw, concerned about security
- Wants AI automation but won't compromise credentials
- Comfortable with self-hosting
- Values open source and transparency

**Goals:**
- Automate repetitive tasks (email, calendar, research)
- Access AI from Slack/Discord during work
- Keep sensitive data off third-party servers
- Understand exactly what the AI has access to

**Pain Points:**
- OpenClaw's security model is "opt-in" not "default"
- Enterprise AI tools are expensive and locked down
- Setting up secure self-hosted solutions is time-consuming

**Quote:** *"I want an AI assistant, but I'm not giving it my SSH keys unless I can verify how they're stored."*

---

### 4.2 Secondary Persona: The Productivity Enthusiast

**Name:** Jordan
**Role:** Freelance Consultant
**Age:** 28

**Context:**
- Heavy user of Notion, Todoist, calendar apps
- Active on multiple messaging platforms
- Wants to consolidate and automate workflows
- Less technical, but willing to follow setup guides

**Goals:**
- Morning briefings without opening multiple apps
- Automated task capture from conversations
- Cross-platform memory (remembers across Telegram, WhatsApp, etc.)
- Voice notes transcribed and organized

**Pain Points:**
- Context-switching between apps kills productivity
- Forgets to check things; wants proactive reminders
- Worried about AI costs spiraling out of control

**Quote:** *"I just want to text my AI and have it handle the boring stuff."*

---

### 4.3 Tertiary Persona: The Enterprise Team Lead

**Name:** Morgan
**Role:** Engineering Manager
**Age:** 40

**Context:**
- Manages team of 8 developers
- Needs AI assistance but compliance matters
- IT security team requires audit trails
- Budget for tooling, but needs justification

**Goals:**
- Team-wide AI assistant in Slack
- Audit logs for all AI actions
- Role-based access (junior devs can't run prod commands)
- Cost tracking and budgets per user

**Pain Points:**
- OpenClaw is "too risky" for enterprise
- Cloud AI tools don't integrate with internal systems
- No visibility into what AI is doing

**Quote:** *"Show me the audit log and I'll get budget approval."*

---

## 5. Security Philosophy

### 5.1 Core Security Principles

| Principle | Implementation |
|-----------|----------------|
| **Secure by default** | No capabilities until explicitly enabled |
| **Defense in depth** | Multiple security layers, not single points |
| **Least privilege** | Minimum permissions for each operation |
| **Explicit over implicit** | Users approve access, not opt-out |
| **Audit everything** | Immutable logs of all actions |
| **Fail secure** | Errors deny access, not grant it |

### 5.2 Security Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SECURITY ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ LAYER 1: PERIMETER                                               │    │
│  │ • Input sanitization (all messages)                              │    │
│  │ • Rate limiting (per user, per channel, per endpoint)            │    │
│  │ • DM pairing (unknown senders require approval)                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ LAYER 2: AUTHENTICATION & AUTHORIZATION                          │    │
│  │ • Session tokens with expiration                                 │    │
│  │ • Role-based access control (RBAC)                               │    │
│  │ • Permission levels (read / write / execute)                     │    │
│  │ • Elevation prompts for sensitive operations                     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ LAYER 3: SECRETS MANAGEMENT                                      │    │
│  │ • Encrypted vault (AES-256 at rest)                              │    │
│  │ • Environment variable injection (never in code)                 │    │
│  │ • Key rotation support                                           │    │
│  │ • Secret access audit trail                                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ LAYER 4: EXECUTION SANDBOXING                                    │    │
│  │ • Docker containers for all commands                             │    │
│  │ • Filesystem isolation (no access to host by default)            │    │
│  │ • Network isolation (loopback only, explicit allowlist)          │    │
│  │ • Resource limits (CPU, memory, time, disk)                      │    │
│  │ • Unprivileged execution (no root, no sudo)                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ LAYER 5: AUDIT & MONITORING                                      │    │
│  │ • Immutable append-only logs                                     │    │
│  │ • All commands recorded with user, timestamp, result             │    │
│  │ • Cost tracking per operation                                    │    │
│  │ • Anomaly detection and alerting                                 │    │
│  │ • Incident response playbooks                                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Trust Levels for Skills

| Level | Name | Permissions | Requirements |
|-------|------|-------------|--------------|
| 0 | Untrusted | No system/network, memory read-only, sandbox required | Default for new skills |
| 1 | Verified | Read-only system, allowlisted network, memory read/write | Automated security scan |
| 2 | Trusted | Full system/network/memory access | Manual security audit |
| 3 | Core | Elevated privileges, can modify platform | First-party, signed |

### 5.4 Security Requirements by Feature

| Feature | Security Requirements |
|---------|----------------------|
| Messaging Channels | Encrypted credential storage, session tokens, DM pairing |
| System Access | Docker sandbox, command allowlist, resource limits |
| Browser Automation | Isolated profile, network controls, no cookie access to host |
| Proactive Automation | Budget caps, approval queues, iteration limits |
| Skills | Code signing, dependency scanning, trust levels |
| Memory | Encryption at rest option, access logging, retention policies |

---

## 6. Feature Requirements

### 6.1 Phase 1: Security Foundation

**Goal:** Establish security infrastructure before adding risky capabilities.

**Duration:** Weeks 1-4

---

#### F1.1: Secrets Vault

**Priority:** P0
**Effort:** M

**Description:**
Encrypted storage for API keys, OAuth tokens, and other credentials. Secrets are never stored in plain text and are injected into the environment at runtime.

**User Stories:**
- As a user, I want my API keys encrypted so that a database breach doesn't expose them
- As a user, I want to rotate credentials without reconfiguring the entire system
- As an admin, I want to see which secrets exist without seeing their values

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F1.1.1 | Encrypt secrets with AES-256-GCM at rest | Must |
| F1.1.2 | Derive encryption key from user master password | Must |
| F1.1.3 | Support key rotation without re-encryption of all secrets | Should |
| F1.1.4 | Inject secrets as environment variables at runtime | Must |
| F1.1.5 | Log all secret access (read, write, delete) without logging values | Must |
| F1.1.6 | CLI for add/list/delete/rotate operations | Must |
| F1.1.7 | Support multiple secret "namespaces" (e.g., per-skill) | Should |
| F1.1.8 | Auto-expire secrets after configurable TTL | Could |

**Non-Functional Requirements:**

| ID | Requirement | Target |
|----|-------------|--------|
| NF1.1.1 | Secret retrieval latency | <50ms |
| NF1.1.2 | Vault unlock time | <2s |
| NF1.1.3 | Maximum secrets stored | 10,000+ |

**Security Requirements:**

| ID | Requirement |
|----|-------------|
| S1.1.1 | Master password never stored, only derived key |
| S1.1.2 | Memory wiped after secret access |
| S1.1.3 | Failed unlock attempts rate-limited (3 attempts, then 30s backoff) |

**Acceptance Criteria:**
- [ ] Secrets encrypted at rest, verified with hex dump
- [ ] Secret values never appear in logs
- [ ] Key rotation works without service interruption
- [ ] CLI operations complete in <1s

---

#### F1.2: Input Sanitizer

**Priority:** P0
**Effort:** S

**Description:**
Pipeline that cleans all incoming messages before processing, preventing injection attacks and enforcing message constraints.

**User Stories:**
- As the system, I need to strip malicious content from user messages
- As a user, I expect my messages to work even if I accidentally include special characters

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F1.2.1 | Strip HTML/script tags from all input | Must |
| F1.2.2 | Enforce maximum message length (configurable, default 10KB) | Must |
| F1.2.3 | Detect and flag potential prompt injection patterns | Should |
| F1.2.4 | Normalize Unicode to prevent homograph attacks | Should |
| F1.2.5 | Log sanitization actions for debugging | Must |
| F1.2.6 | Configurable sanitization rules per channel | Could |

**Acceptance Criteria:**
- [ ] Script tags removed from messages
- [ ] Messages exceeding limit are rejected with clear error
- [ ] Prompt injection attempts logged and flagged

---

#### F1.3: Rate Limiter

**Priority:** P0
**Effort:** S

**Description:**
Request throttling system that prevents abuse and controls costs at multiple levels.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F1.3.1 | Per-user rate limits (messages per minute) | Must |
| F1.3.2 | Per-channel rate limits | Must |
| F1.3.3 | Global rate limits (system-wide) | Must |
| F1.3.4 | Cost-based limits ($ per hour/day) | Must |
| F1.3.5 | Configurable limits via args file | Must |
| F1.3.6 | Clear error messages when rate limited | Must |
| F1.3.7 | Rate limit headers in responses | Should |
| F1.3.8 | Burst allowance for bursty workloads | Should |

**Default Limits:**

| Limit Type | Default Value |
|------------|---------------|
| Messages per user per minute | 20 |
| Messages per channel per minute | 100 |
| API cost per user per hour | $1.00 |
| API cost per user per day | $10.00 |

**Acceptance Criteria:**
- [ ] Users receive clear message when rate limited
- [ ] Limits configurable without code changes
- [ ] Cost tracking accurate to $0.01

---

#### F1.4: Audit Logger

**Priority:** P0
**Effort:** M

**Description:**
Immutable, append-only log of all system actions for security forensics and compliance.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F1.4.1 | Log all commands executed with user, timestamp, input, output | Must |
| F1.4.2 | Log all authentication events (login, logout, failure) | Must |
| F1.4.3 | Log all secret access (without secret values) | Must |
| F1.4.4 | Log all permission changes | Must |
| F1.4.5 | Append-only storage (no modification or deletion) | Must |
| F1.4.6 | Structured format (JSON) for machine parsing | Must |
| F1.4.7 | Log rotation with compression | Should |
| F1.4.8 | Log export for external SIEM systems | Should |
| F1.4.9 | Cryptographic integrity verification (hash chain) | Could |

**Log Entry Schema:**
```json
{
  "id": "uuid",
  "timestamp": "ISO8601",
  "event_type": "command|auth|secret|permission|error",
  "user_id": "string",
  "session_id": "string",
  "channel": "telegram|discord|slack|...",
  "action": "string",
  "input": "string (sanitized)",
  "output": "string (truncated)",
  "duration_ms": "number",
  "cost_usd": "number",
  "success": "boolean",
  "error": "string|null",
  "metadata": {}
}
```

**Acceptance Criteria:**
- [ ] All commands appear in audit log
- [ ] Logs cannot be modified after writing
- [ ] Log search returns results in <1s for 1M entries

---

#### F1.5: Session Manager

**Priority:** P1
**Effort:** M

**Description:**
Token-based authentication system managing user sessions across channels.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F1.5.1 | Generate secure session tokens (256-bit random) | Must |
| F1.5.2 | Token expiration (configurable, default 24h) | Must |
| F1.5.3 | Token refresh without re-authentication | Should |
| F1.5.4 | Session binding to channel/device | Must |
| F1.5.5 | Force logout (invalidate all sessions) | Must |
| F1.5.6 | List active sessions for user | Should |
| F1.5.7 | Session activity tracking (last used) | Should |
| F1.5.8 | Concurrent session limits | Could |

**Acceptance Criteria:**
- [ ] Sessions expire after configured TTL
- [ ] Stolen token cannot be used from different device/channel
- [ ] Users can view and terminate their sessions

---

#### F1.6: Permission System

**Priority:** P1
**Effort:** M

**Description:**
Role-based access control (RBAC) for granular permission management.

**Roles:**

| Role | Permissions |
|------|-------------|
| Guest | Read memory, basic chat |
| User | Read/write memory, execute safe commands |
| Power User | All User + execute elevated commands |
| Admin | All Power User + manage users, configure system |
| Owner | All Admin + manage admins, access audit logs |

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F1.6.1 | Define permission levels for all operations | Must |
| F1.6.2 | Assign roles to users | Must |
| F1.6.3 | Check permissions before every action | Must |
| F1.6.4 | Elevation prompt for sensitive operations | Must |
| F1.6.5 | Custom role creation | Should |
| F1.6.6 | Time-limited permission grants | Could |
| F1.6.7 | Permission inheritance | Could |

**Acceptance Criteria:**
- [ ] Unauthorized actions are blocked with clear error
- [ ] Elevation prompt works via messaging channel
- [ ] Permission changes logged in audit trail

---

### 6.2 Phase 2: Messaging Channels

**Goal:** Connect to users via messaging platforms they already use.

**Duration:** Weeks 5-12

---

#### F2.1: Gateway Architecture

**Priority:** P0
**Effort:** L

**Description:**
Central hub that routes messages between channels and the agent, managing sessions and tool orchestration.

**Architecture:**

```
┌─────────────────────────────────────────────────────────────────┐
│                          GATEWAY                                 │
│                    (WebSocket @ :18789)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Telegram │  │ Discord  │  │  Slack   │  │ WhatsApp │        │
│  │ Adapter  │  │ Adapter  │  │ Adapter  │  │ Adapter  │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       │             │             │             │                │
│       └─────────────┴──────┬──────┴─────────────┘                │
│                            │                                     │
│                     ┌──────▼──────┐                              │
│                     │   Router    │                              │
│                     │  (Session   │                              │
│                     │  Dispatch)  │                              │
│                     └──────┬──────┘                              │
│                            │                                     │
│              ┌─────────────┼─────────────┐                       │
│              │             │             │                       │
│        ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐                │
│        │  Agent    │ │  Memory   │ │  Tools    │                │
│        │  (LLM)    │ │  System   │ │  Executor │                │
│        └───────────┘ └───────────┘ └───────────┘                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F2.1.1 | WebSocket server for real-time communication | Must |
| F2.1.2 | Channel adapter plugin interface | Must |
| F2.1.3 | Message routing by session ID | Must |
| F2.1.4 | Unified message format across channels | Must |
| F2.1.5 | Health check endpoint | Must |
| F2.1.6 | Graceful shutdown with message drain | Should |
| F2.1.7 | Horizontal scaling support | Could |

**Acceptance Criteria:**
- [ ] Messages route correctly between channels and agent
- [ ] Gateway recovers from channel adapter failures
- [ ] Latency <100ms for message routing

---

#### F2.2: Telegram Bot

**Priority:** P0
**Effort:** M

**Description:**
Telegram integration using python-telegram-bot library.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F2.2.1 | Receive and respond to direct messages | Must |
| F2.2.2 | Support group chats with @mention activation | Should |
| F2.2.3 | Handle voice notes (transcribe to text) | Should |
| F2.2.4 | Handle images (describe or process) | Should |
| F2.2.5 | Handle documents (PDF, text files) | Should |
| F2.2.6 | DM pairing for unknown users | Must |
| F2.2.7 | Inline keyboards for confirmations | Should |
| F2.2.8 | Message editing for streaming responses | Could |

**Acceptance Criteria:**
- [ ] Bot responds to DMs within 2 seconds
- [ ] Voice notes transcribed accurately
- [ ] Unknown users prompted to pair before access

---

#### F2.3: Discord Bot

**Priority:** P1
**Effort:** M

**Description:**
Discord integration using discord.py library.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F2.3.1 | Respond to DMs | Must |
| F2.3.2 | Respond to @mentions in channels | Must |
| F2.3.3 | Slash commands for common operations | Should |
| F2.3.4 | Thread support for long conversations | Should |
| F2.3.5 | Voice channel support (listen/speak) | Could |
| F2.3.6 | Role-based permissions mapping | Should |

**Acceptance Criteria:**
- [ ] Bot responds to mentions and DMs
- [ ] Slash commands work in servers
- [ ] Discord roles map to permission system

---

#### F2.4: Slack App

**Priority:** P1
**Effort:** M

**Description:**
Slack integration using Bolt SDK for enterprise users.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F2.4.1 | Respond to DMs | Must |
| F2.4.2 | Respond to @mentions in channels | Must |
| F2.4.3 | Slash commands | Should |
| F2.4.4 | Slack Connect support (external orgs) | Could |
| F2.4.5 | Thread replies | Should |
| F2.4.6 | Rich message formatting (blocks) | Should |
| F2.4.7 | Workspace-level configuration | Should |

**Acceptance Criteria:**
- [ ] App installable via Slack App Directory flow
- [ ] Works in threads and channels
- [ ] Enterprise Grid compatible

---

#### F2.5: WhatsApp Connector

**Priority:** P2
**Effort:** L

**Description:**
WhatsApp integration using Baileys library (unofficial API).

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F2.5.1 | Send and receive text messages | Must |
| F2.5.2 | Handle voice notes | Should |
| F2.5.3 | Handle images | Should |
| F2.5.4 | QR code pairing flow | Must |
| F2.5.5 | Session persistence across restarts | Must |
| F2.5.6 | Rate limit compliance (avoid bans) | Must |

**Risk:** WhatsApp unofficial API may change or result in account bans.

**Acceptance Criteria:**
- [ ] Messages send and receive reliably
- [ ] Session survives gateway restart
- [ ] No account bans after 30 days of testing

---

#### F2.6: Unified Inbox

**Priority:** P1
**Effort:** M

**Description:**
Cross-platform message management with consistent experience regardless of channel.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F2.6.1 | Normalize message format across channels | Must |
| F2.6.2 | Preserve channel-specific metadata | Must |
| F2.6.3 | Cross-channel session continuity | Should |
| F2.6.4 | Channel preference per user | Should |
| F2.6.5 | Fallback channel if primary unavailable | Could |

**Acceptance Criteria:**
- [ ] Same conversation continues across channels
- [ ] User can set preferred response channel

---

### 6.3 Phase 3: System Access

**Goal:** Enable the agent to perform actions, not just provide advice.

**Duration:** Weeks 13-16

---

#### F3.1: Sandbox Executor

**Priority:** P0
**Effort:** L

**Description:**
Docker-based execution environment for running commands safely.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F3.1.1 | Execute commands in isolated Docker container | Must |
| F3.1.2 | No access to host filesystem by default | Must |
| F3.1.3 | No network access by default | Must |
| F3.1.4 | Resource limits (CPU, memory, time) | Must |
| F3.1.5 | Command output capture (stdout, stderr) | Must |
| F3.1.6 | Timeout enforcement with graceful then forced kill | Must |
| F3.1.7 | Configurable base images per task type | Should |
| F3.1.8 | Volume mounting for approved directories only | Should |
| F3.1.9 | Network allowlist for specific hosts | Should |

**Default Resource Limits:**

| Resource | Default Limit |
|----------|---------------|
| CPU | 1 core |
| Memory | 512 MB |
| Execution time | 60 seconds |
| Disk | 1 GB |
| Network | Disabled |

**Acceptance Criteria:**
- [ ] Commands cannot access host filesystem
- [ ] Commands timeout and are killed after limit
- [ ] Resource exhaustion contained to container

---

#### F3.2: File Operations

**Priority:** P1
**Effort:** M

**Description:**
Secure file read/write with path validation and sandboxing.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F3.2.1 | Read files from approved directories | Must |
| F3.2.2 | Write files to approved directories | Must |
| F3.2.3 | Path traversal prevention (no ../) | Must |
| F3.2.4 | File type validation | Should |
| F3.2.5 | Size limits on reads and writes | Must |
| F3.2.6 | Atomic writes (temp file + rename) | Should |
| F3.2.7 | Directory listing | Should |

**Approved Directories (default):**
- `~/addulting/workspace/` (user files)
- `~/addulting/.tmp/` (scratch)
- `/tmp/addulting/` (temporary)

**Acceptance Criteria:**
- [ ] Path traversal attempts blocked and logged
- [ ] Files outside approved directories inaccessible
- [ ] Large file operations don't crash system

---

#### F3.3: Browser Automation

**Priority:** P1
**Effort:** L

**Description:**
Playwright-based browser automation in isolated container.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F3.3.1 | Navigate to URLs | Must |
| F3.3.2 | Take screenshots | Must |
| F3.3.3 | Generate PDFs | Should |
| F3.3.4 | Fill forms | Should |
| F3.3.5 | Extract text content | Must |
| F3.3.6 | Click elements | Should |
| F3.3.7 | Isolated browser profile (no host cookies) | Must |
| F3.3.8 | Block tracking/ads | Should |
| F3.3.9 | Timeout enforcement | Must |

**Acceptance Criteria:**
- [ ] Browser runs in isolated container
- [ ] No access to user's browser profile
- [ ] Screenshots and PDFs generated successfully

---

#### F3.4: Network Client

**Priority:** P2
**Effort:** M

**Description:**
HTTP client for making API requests with allowlist enforcement.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F3.4.1 | Make HTTP GET/POST requests | Must |
| F3.4.2 | Domain allowlist (configurable) | Must |
| F3.4.3 | Request/response logging | Must |
| F3.4.4 | Timeout enforcement | Must |
| F3.4.5 | Rate limiting per domain | Should |
| F3.4.6 | Response size limits | Must |
| F3.4.7 | SSL verification (no bypass) | Must |

**Acceptance Criteria:**
- [ ] Requests to non-allowlisted domains blocked
- [ ] All requests logged in audit trail
- [ ] SSL errors not bypassable

---

### 6.4 Phase 4: Proactive Automation

**Goal:** Transform from reactive chatbot to proactive agent.

**Duration:** Weeks 17-20

---

#### F4.1: Heartbeat Engine

**Priority:** P0
**Effort:** M

**Description:**
Periodic check system that runs background awareness tasks.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F4.1.1 | Read HEARTBEAT.md for check definitions | Must |
| F4.1.2 | Execute checks at configurable interval (default 30 min) | Must |
| F4.1.3 | Batch multiple checks into single LLM turn | Must |
| F4.1.4 | Share context with main session | Must |
| F4.1.5 | Skip if user is actively chatting | Should |
| F4.1.6 | Cost tracking per heartbeat | Must |
| F4.1.7 | Disable specific checks without editing file | Should |

**HEARTBEAT.md Format:**
```markdown
# Heartbeat Checks

## Morning Briefing
- Check calendar for today's events
- Summarize unread important emails
- Weather forecast for user's location

## Monitoring
- Check if backup completed successfully
- Verify API endpoints are responding
```

**Acceptance Criteria:**
- [ ] Heartbeat runs at configured interval
- [ ] Checks batched into single turn
- [ ] Cost per heartbeat tracked and reported

---

#### F4.2: Cron Scheduler

**Priority:** P1
**Effort:** M

**Description:**
Time-based job scheduler using Unix cron syntax.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F4.2.1 | Parse Unix cron expressions | Must |
| F4.2.2 | Execute jobs at scheduled times | Must |
| F4.2.3 | Isolated session per job (fresh context) | Must |
| F4.2.4 | Job success/failure tracking | Must |
| F4.2.5 | Retry with exponential backoff | Should |
| F4.2.6 | Job history and logs | Must |
| F4.2.7 | Resource limits per job | Must |
| F4.2.8 | Cost limits per job | Must |
| F4.2.9 | Enable/disable jobs | Must |

**CRON.yaml Format:**
```yaml
jobs:
  morning_briefing:
    schedule: "0 7 * * *"  # 7 AM daily
    task: "Generate morning briefing and send to Telegram"
    timeout: 120
    cost_limit: 0.50

  weekly_review:
    schedule: "0 18 * * 5"  # 6 PM every Friday
    task: "Summarize this week's completed tasks and learnings"
    timeout: 300
    cost_limit: 1.00
```

**Acceptance Criteria:**
- [ ] Jobs execute at scheduled times (±1 minute)
- [ ] Failed jobs retry with backoff
- [ ] Jobs exceeding cost limit are stopped

---

#### F4.3: Event Triggers

**Priority:** P2
**Effort:** M

**Description:**
React to external events (file changes, webhooks, etc.).

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F4.3.1 | File system watching (specific directories) | Should |
| F4.3.2 | Webhook endpoint for external triggers | Should |
| F4.3.3 | Email trigger (new email matching criteria) | Could |
| F4.3.4 | Debouncing for rapid events | Must |
| F4.3.5 | Event queue with processing order | Should |

**Acceptance Criteria:**
- [ ] File changes trigger within 5 seconds
- [ ] Webhooks processed securely (signed)
- [ ] Rapid events debounced appropriately

---

#### F4.4: Notification Dispatch

**Priority:** P1
**Effort:** S

**Description:**
Send proactive messages to users across their preferred channels.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F4.4.1 | Send notifications to user's preferred channel | Must |
| F4.4.2 | Fallback to secondary channel if primary fails | Should |
| F4.4.3 | Notification priority levels (urgent, normal, low) | Should |
| F4.4.4 | Do Not Disturb schedule | Should |
| F4.4.5 | Notification aggregation (batch similar) | Should |
| F4.4.6 | Delivery confirmation tracking | Should |

**Acceptance Criteria:**
- [ ] Notifications delivered to preferred channel
- [ ] DND schedule respected
- [ ] Delivery tracked in logs

---

### 6.5 Phase 5: Extensibility

**Goal:** Enable community-driven growth through skills ecosystem.

**Duration:** Weeks 21-24

---

#### F5.1: Skill Architecture

**Priority:** P0
**Effort:** L

**Description:**
Plugin system for loading and managing third-party skills.

**Skill Structure:**
```
skills/
└── my-skill/
    ├── manifest.yaml     # Metadata, permissions, dependencies
    ├── skill.py          # Main skill code
    ├── README.md         # Documentation
    └── tests/            # Test files
```

**manifest.yaml:**
```yaml
name: my-skill
version: 1.0.0
description: A useful skill that does X
author: developer@example.com

permissions:
  memory: read_write
  network:
    - api.example.com
  system: none

dependencies:
  - requests>=2.28.0

trust_level: 1  # 0=untrusted, 1=verified, 2=trusted, 3=core
```

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F5.1.1 | Load skills from designated directories | Must |
| F5.1.2 | Parse and validate manifest | Must |
| F5.1.3 | Enforce declared permissions | Must |
| F5.1.4 | Skill enable/disable | Must |
| F5.1.5 | Skill configuration (per-skill settings) | Should |
| F5.1.6 | Hot reload (no restart required) | Could |
| F5.1.7 | Skill dependency resolution | Should |

**Acceptance Criteria:**
- [ ] Skills load and execute correctly
- [ ] Permission violations blocked and logged
- [ ] Skills can be enabled/disabled at runtime

---

#### F5.2: Skill Sandbox

**Priority:** P0
**Effort:** M

**Description:**
Isolation environment for running untrusted skills safely.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F5.2.1 | Run skills in isolated process/container | Must |
| F5.2.2 | Enforce memory permissions per skill | Must |
| F5.2.3 | Enforce network permissions per skill | Must |
| F5.2.4 | Enforce system permissions per skill | Must |
| F5.2.5 | Resource limits per skill | Must |
| F5.2.6 | Skill crash doesn't crash platform | Must |
| F5.2.7 | Inter-skill communication (controlled) | Could |

**Acceptance Criteria:**
- [ ] Level 0 skills cannot access network
- [ ] Skill crash contained, platform continues
- [ ] Resource exhaustion limited to skill

---

#### F5.3: Skill Registry

**Priority:** P1
**Effort:** M

**Description:**
Discovery and installation system for skills.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F5.3.1 | CLI to install skills | Must |
| F5.3.2 | CLI to list available skills | Must |
| F5.3.3 | CLI to update skills | Must |
| F5.3.4 | CLI to remove skills | Must |
| F5.3.5 | Version pinning | Should |
| F5.3.6 | Dependency auto-resolution | Should |
| F5.3.7 | Local registry (file-based) | Must |
| F5.3.8 | Remote registry (HTTP) | Could |

**CLI Examples:**
```bash
addulting skills install github:user/skill-name
addulting skills list
addulting skills update skill-name
addulting skills remove skill-name
```

**Acceptance Criteria:**
- [ ] Skills installable from local and git sources
- [ ] Version conflicts detected before install
- [ ] Removal cleans up all skill files

---

#### F5.4: Skill Verification

**Priority:** P1
**Effort:** M

**Description:**
Security verification system for establishing skill trust levels.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F5.4.1 | Automated security scan (static analysis) | Must |
| F5.4.2 | Dependency vulnerability check | Must |
| F5.4.3 | Permission audit (declared vs used) | Should |
| F5.4.4 | Code signing for verified skills | Should |
| F5.4.5 | Trust level assignment workflow | Must |
| F5.4.6 | Manual audit checklist for Level 2 | Should |

**Acceptance Criteria:**
- [ ] New skills start at Level 0
- [ ] Automated scan catches obvious issues
- [ ] Signed skills verified on load

---

### 6.6 Phase 6: Advanced Features

**Goal:** Polish and expand platform capabilities.

**Duration:** Weeks 25+

---

#### F6.1: Voice Integration

**Priority:** P2
**Effort:** M

**Description:**
Speech-to-text and text-to-speech for hands-free interaction.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F6.1.1 | Transcribe voice notes from messaging channels | Should |
| F6.1.2 | Generate voice responses (optional) | Could |
| F6.1.3 | ElevenLabs integration for TTS | Could |
| F6.1.4 | Whisper integration for STT | Should |
| F6.1.5 | Voice note language detection | Could |

---

#### F6.2: Visual Workspace (Canvas)

**Priority:** P3
**Effort:** L

**Description:**
Agent-driven visual interface for rich output rendering.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F6.2.1 | Render HTML/Markdown to visual panel | Could |
| F6.2.2 | Interactive elements (buttons, forms) | Could |
| F6.2.3 | Real-time updates | Could |
| F6.2.4 | Dashboard templates | Could |

---

#### F6.3: Multi-Agent Collaboration

**Priority:** P3
**Effort:** XL

**Description:**
Multiple AI agents working together on complex tasks.

**Functional Requirements:**

| ID | Requirement | Priority |
|----|-------------|----------|
| F6.3.1 | Spawn sub-agents for parallel tasks | Could |
| F6.3.2 | Agent-to-agent communication | Could |
| F6.3.3 | Shared memory access controls | Could |
| F6.3.4 | Agent supervision and termination | Could |

---

## 7. Technical Architecture

### 7.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ADDULTING-AI ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CHANNELS                    GATEWAY                      CORE               │
│  ┌──────────┐               ┌────────────────────┐       ┌────────────────┐ │
│  │ Telegram │──┐            │                    │       │    AGENT       │ │
│  └──────────┘  │            │  ┌──────────────┐  │       │  ┌──────────┐  │ │
│  ┌──────────┐  │            │  │   Router     │  │       │  │   LLM    │  │ │
│  │ Discord  │──┼───────────▶│  │              │──┼──────▶│  │ (Claude) │  │ │
│  └──────────┘  │            │  └──────────────┘  │       │  └──────────┘  │ │
│  ┌──────────┐  │            │         │         │       │       │        │ │
│  │  Slack   │──┤            │  ┌──────▼───────┐  │       │  ┌────▼─────┐  │ │
│  └──────────┘  │            │  │   Session    │  │       │  │  Memory  │  │ │
│  ┌──────────┐  │            │  │   Manager    │  │       │  │  System  │  │ │
│  │ WhatsApp │──┘            │  └──────────────┘  │       │  └──────────┘  │ │
│  └──────────┘               │                    │       │                │ │
│                             └────────────────────┘       └────────────────┘ │
│                                      │                          │           │
│                                      │                          │           │
│  SECURITY                            │                          │           │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │ │
│  │  │  Vault   │  │ Sanitizer│  │  Rate    │  │  Audit   │  │ Permis-  │ │ │
│  │  │          │  │          │  │ Limiter  │  │  Logger  │  │  sions   │ │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                      │
│  EXECUTION                           │                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │ │
│  │  │ Sandbox  │  │  File    │  │ Browser  │  │ Network  │               │ │
│  │  │ Executor │  │   Ops    │  │   Auto   │  │  Client  │               │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                      │
│  AUTOMATION                          │                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │ │
│  │  │Heartbeat │  │   Cron   │  │  Event   │  │  Notify  │               │ │
│  │  │  Engine  │  │ Scheduler│  │ Triggers │  │ Dispatch │               │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                      │
│  DATA                                │                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │ │
│  │  │ memory.db│  │activity.db│ │ audit.db │  │config.yaml│              │ │
│  │  │(SQLite)  │  │ (SQLite) │  │ (SQLite) │  │          │               │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Runtime | Python 3.11+ | Existing codebase, ML ecosystem |
| Database | SQLite | Lightweight, no server needed |
| Vector Search | sqlite-vec | Embedded, no external dependencies |
| Message Queue | In-process | Simplicity for single-node |
| Containers | Docker | Standard, well-supported sandboxing |
| Web Framework | FastAPI | Async, WebSocket support |
| Channel SDKs | python-telegram-bot, discord.py, slack-bolt | Official or well-maintained |

### 7.3 Directory Structure

```
addulting/
├── CLAUDE.md                    # Framework specification
├── config.yaml                  # Main configuration
├── goals/                       # Process definitions
│   ├── manifest.md
│   └── *.md
├── tools/                       # Deterministic execution
│   ├── manifest.md
│   ├── memory/                  # Memory tools (existing)
│   ├── security/                # Security tools (new)
│   │   ├── vault.py
│   │   ├── audit.py
│   │   ├── sanitizer.py
│   │   └── ratelimit.py
│   ├── channels/                # Channel adapters (new)
│   │   ├── telegram.py
│   │   ├── discord.py
│   │   ├── slack.py
│   │   └── whatsapp.py
│   ├── gateway/                 # Gateway components (new)
│   │   ├── router.py
│   │   └── session.py
│   ├── execution/               # Execution layer (new)
│   │   ├── sandbox.py
│   │   ├── shell.py
│   │   ├── browser.py
│   │   └── network.py
│   ├── automation/              # Automation layer (new)
│   │   ├── heartbeat.py
│   │   ├── scheduler.py
│   │   ├── triggers.py
│   │   └── notify.py
│   └── skills/                  # Skills system (new)
│       ├── loader.py
│       ├── registry.py
│       ├── sandbox.py
│       └── verify.py
├── context/                     # Domain knowledge
├── hardprompts/                 # Instruction templates
├── args/                        # Behavior settings
├── memory/                      # Persistent memory
│   ├── MEMORY.md
│   └── logs/
├── skills/                      # Installed skills (new)
├── data/                        # Databases
│   ├── memory.db
│   ├── activity.db
│   └── audit.db                 # (new)
└── .tmp/                        # Scratch work
```

### 7.4 Data Models

#### Session Model

```python
@dataclass
class Session:
    id: str                      # UUID
    user_id: str                 # User identifier
    channel: str                 # telegram, discord, slack, etc.
    channel_id: str              # Channel-specific user ID
    created_at: datetime
    expires_at: datetime
    last_active: datetime
    token: str                   # Session token (hashed)
    permissions: List[str]       # Active permissions
    elevated: bool               # Elevated mode active
    metadata: Dict               # Channel-specific data
```

#### Message Model

```python
@dataclass
class Message:
    id: str                      # UUID
    session_id: str              # Session reference
    channel: str                 # Source channel
    direction: str               # inbound | outbound
    content: str                 # Message text
    attachments: List[Attachment]
    timestamp: datetime
    metadata: Dict               # Channel-specific
```

#### Audit Entry Model

```python
@dataclass
class AuditEntry:
    id: str                      # UUID
    timestamp: datetime
    event_type: str              # command, auth, secret, permission, error
    user_id: str
    session_id: str
    channel: str
    action: str
    input: str                   # Sanitized
    output: str                  # Truncated
    duration_ms: int
    cost_usd: float
    success: bool
    error: Optional[str]
    metadata: Dict
```

---

## 8. Release Roadmap

### 8.1 Timeline Overview

```
2026
Q1                    Q2                    Q3                    Q4
├─────────────────────┼─────────────────────┼─────────────────────┼────────
│                     │                     │                     │
│  Phase 1: Security  │  Phase 2: Channels  │  Phase 3: System    │  Phase 4+
│  (Weeks 1-4)        │  (Weeks 5-12)       │  (Weeks 13-16)      │
│                     │                     │                     │
│  • Secrets vault    │  • Gateway          │  • Sandbox          │  • Heartbeat
│  • Input sanitizer  │  • Telegram         │  • File ops         │  • Cron
│  • Rate limiter     │  • Discord          │  • Browser          │  • Skills
│  • Audit logger     │  • Slack            │  • Network          │  • Voice
│  • Sessions         │  • WhatsApp         │                     │
│  • Permissions      │  • Unified inbox    │                     │
│                     │                     │                     │
└─────────────────────┴─────────────────────┴─────────────────────┴────────
```

### 8.2 Milestones

| Milestone | Target Date | Deliverables |
|-----------|-------------|--------------|
| M1: Security Foundation | Week 4 | Vault, sanitizer, rate limiter, audit, sessions, permissions |
| M2: First Channel | Week 8 | Gateway + Telegram fully operational |
| M3: Multi-Channel | Week 12 | Discord, Slack, WhatsApp added |
| M4: System Access | Week 16 | Sandbox, file ops, browser automation |
| M5: Proactive Agent | Week 20 | Heartbeat, cron, notifications |
| M6: Skills Platform | Week 24 | Skill loading, sandbox, registry |
| M7: Public Beta | Week 28 | Documentation, installer, community launch |

### 8.3 Release Criteria

**Alpha (Internal):**
- [ ] All Phase 1-2 features complete
- [ ] 2+ channels working reliably
- [ ] Security audit passed (internal)
- [ ] <5 critical bugs

**Beta (Limited External):**
- [ ] All Phase 1-4 features complete
- [ ] 4+ channels working reliably
- [ ] External security audit passed
- [ ] Documentation complete
- [ ] <3 critical bugs

**GA (General Availability):**
- [ ] All Phase 1-5 features complete
- [ ] Skills ecosystem with 10+ verified skills
- [ ] 30-day stability (no critical incidents)
- [ ] 99.9% uptime demonstrated
- [ ] Community support active

---

## 9. Success Metrics

### 9.1 Security Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Credential exposures | 0 | Audit + external reports |
| Sandbox escapes | 0 | Security testing |
| Input validation bypass | 0 | Penetration testing |
| Audit coverage | 100% | Code analysis |
| Secret access without logging | 0 | Audit verification |

### 9.2 Performance Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Message latency (p50) | <500ms | Telemetry |
| Message latency (p95) | <2s | Telemetry |
| Gateway uptime | 99.9% | Monitoring |
| Command execution (p95) | <5s | Telemetry |
| Memory search (p95) | <1s | Telemetry |

### 9.3 User Metrics

| Metric | Target (Beta) | Target (GA) |
|--------|---------------|-------------|
| Daily Active Users | 100 | 1,000 |
| Messages per user per day | 10 | 20 |
| Channels per user | 1.5 | 2.0 |
| 7-day retention | 40% | 60% |
| NPS | 30 | 50 |

### 9.4 Business Metrics

| Metric | Target (Beta) | Target (GA) |
|--------|---------------|-------------|
| GitHub stars | 1,000 | 10,000 |
| Community contributors | 10 | 50 |
| Verified skills | 5 | 20 |
| Enterprise inquiries | — | 10/month |

---

## 10. Risks & Mitigations

### 10.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Messaging API changes break channels | High | Medium | Abstract adapter interface, monitor API changelogs |
| Docker performance overhead | Medium | Low | Benchmark early, optimize or use process isolation |
| SQLite scaling limits | Low | Medium | Design for migration to PostgreSQL |
| LLM provider outage | Medium | High | Multi-provider support, graceful degradation |

### 10.2 Security Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Sandbox escape vulnerability | Low | Critical | Regular security audits, bug bounty |
| Prompt injection in skills | Medium | High | Skill sandboxing, permission isolation |
| Credential theft | Low | Critical | Encrypted vault, access logging |
| Supply chain attack via skill | Medium | High | Skill verification, trust levels |

### 10.3 Business Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| OpenClaw achieves security parity | Medium | High | Move fast, build community, enterprise focus |
| WhatsApp blocks unofficial API | High | Medium | Prioritize official channels, warn users |
| API costs exceed user expectations | High | Medium | Clear cost tracking, budget alerts |
| Community fails to adopt | Medium | High | Seed with useful skills, active engagement |

---

## 11. Dependencies & Constraints

### 11.1 External Dependencies

| Dependency | Risk | Contingency |
|------------|------|-------------|
| Anthropic Claude API | API changes, pricing | Abstract LLM interface, support alternatives |
| OpenAI Embeddings API | Pricing changes | Local embedding models |
| Telegram Bot API | Policy changes | Alternative channels |
| Docker | Security vulnerabilities | Monitor CVEs, prompt updates |

### 11.2 Constraints

| Constraint | Impact | Approach |
|------------|--------|----------|
| Single-developer velocity | Longer timelines | Prioritize ruthlessly, MVP features only |
| Self-hosted requirement | No SaaS shortcuts | Design for local-first from start |
| Security-first requirement | Longer development | Build security early, not retrofit |
| Python runtime | Performance limits | Async where possible, optimize hot paths |

---

## 12. Out of Scope

The following are explicitly **not** included in this PRD:

| Item | Reason |
|------|--------|
| Mobile native apps | Messaging apps provide mobile access |
| Moltbook integration | Risky, unclear value |
| Cloud-hosted offering | Focus on self-hosted differentiation |
| 700+ skills at launch | Quality over quantity |
| Real-time voice calls | Complexity, defer to Phase 6+ |
| Multi-user enterprise features | Single-user focus first |
| Custom LLM fine-tuning | Use foundation models |
| Blockchain/crypto integration | Distraction from core value |

---

## 13. Open Questions

| ID | Question | Status | Owner |
|----|----------|--------|-------|
| Q1 | Should we support OAuth for enterprise SSO? | Open | Product |
| Q2 | What's the pricing model for hosted skills registry? | Open | Business |
| Q3 | Should browser automation use Playwright or Puppeteer? | Decided: Playwright | Engineering |
| Q4 | Do we need a web UI or is CLI sufficient? | Open | Product |
| Q5 | What's the minimum Python version to support? | Decided: 3.11+ | Engineering |
| Q6 | Should we implement our own embedding model? | Deferred to Phase 6+ | Engineering |

---

## 14. Appendices

### Appendix A: Glossary

| Term | Definition |
|------|------------|
| Agent | AI system that can take actions, not just provide advice |
| Channel | Messaging platform (Telegram, Discord, etc.) |
| Gateway | Central hub routing messages between channels and agent |
| Heartbeat | Periodic background check system |
| Sandbox | Isolated execution environment |
| Skill | Plugin that extends agent capabilities |
| Trust Level | Security classification for skills (0-3) |
| Vault | Encrypted storage for secrets |

### Appendix B: Related Documents

| Document | Location |
|----------|----------|
| OpenClaw Research | `context/openclaw_research.md` |
| Gap Analysis | `context/gap_analysis.md` |
| GOTCHA Framework | `CLAUDE.md` |
| ATLAS Build Workflow | `goals/build_app.md` |

### Appendix C: Competitive Analysis Summary

| Feature | addulting-ai (Target) | OpenClaw | ChatGPT | Claude |
|---------|----------------------|----------|---------|--------|
| Messaging channels | ✅ 4+ | ✅ 12+ | ❌ | ❌ |
| Persistent memory | ✅ | ✅ | ⚠️ Limited | ⚠️ Limited |
| System access | ✅ Sandboxed | ✅ Unsandboxed | ❌ | ❌ |
| Proactive automation | ✅ | ✅ | ❌ | ❌ |
| Security-first | ✅ | ❌ | ✅ | ✅ |
| Self-hosted | ✅ | ✅ | ❌ | ❌ |
| Open source | ✅ | ✅ | ❌ | ❌ |
| Skills ecosystem | ✅ Verified | ✅ Unverified | ✅ GPTs | ❌ |

---

## Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Product Owner | | | |
| Engineering Lead | | | |
| Security Lead | | | |
| Design Lead | | | |

---

*Document Version: 1.0*
*Last Updated: 2026-02-02*
*Status: Draft - Pending Approval*
