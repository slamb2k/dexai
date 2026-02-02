# Goal: Phase 1 Security Foundation

## Objective
Build the security infrastructure layer for DexAI, providing authentication, authorization, audit logging, and input protection.

## Context
This is the foundation for all future security features. Every other component will depend on these tools working correctly.

## Dependencies
- Memory database must be migrated (✅ complete)
- Args layer must be populated (✅ complete)

---

## Components to Build

### 1. Audit Logger (`tools/security/audit.py`)

**Purpose:** Immutable record of all security-relevant events.

**Features:**
- Append-only SQLite logging (no updates or deletes)
- Structured JSON event format
- Event types: auth, command, permission, secret, error, system
- Query interface for forensics
- Retention management (configurable in args/security.yaml)

**Database Schema:**
```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    user_id TEXT,
    session_id TEXT,
    channel TEXT,
    action TEXT NOT NULL,
    resource TEXT,
    status TEXT CHECK(status IN ('success', 'failure', 'blocked')),
    details TEXT,  -- JSON blob
    ip_address TEXT,
    user_agent TEXT
);
```

**CLI:**
```bash
python tools/security/audit.py --action log --type auth --user alice --status success
python tools/security/audit.py --action query --user alice --since "24h"
python tools/security/audit.py --action stats
```

---

### 2. Secrets Vault (`tools/security/vault.py`)

**Purpose:** Encrypted storage for API keys, tokens, and sensitive config.

**Features:**
- AES-256-GCM encryption at rest
- PBKDF2 key derivation (100k iterations per args/security.yaml)
- Namespace support (group secrets by skill/integration)
- Environment variable injection
- Access audit logging

**Database Schema:**
```sql
CREATE TABLE secrets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace TEXT DEFAULT 'default',
    key TEXT NOT NULL,
    encrypted_value BLOB NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    expires_at DATETIME,
    accessed_count INTEGER DEFAULT 0,
    last_accessed DATETIME,
    UNIQUE(namespace, key)
);
```

**CLI:**
```bash
python tools/security/vault.py --action set --key OPENAI_API_KEY --value "sk-..."
python tools/security/vault.py --action get --key OPENAI_API_KEY
python tools/security/vault.py --action list --namespace default
python tools/security/vault.py --action delete --key OLD_TOKEN
python tools/security/vault.py --action inject-env  # Load all secrets to env vars
```

**Security Notes:**
- Master key from env var ADDULTING_MASTER_KEY
- Never log decrypted values
- Fail closed — missing master key = no access

---

### 3. Input Sanitizer (`tools/security/sanitizer.py`)

**Purpose:** Clean and validate all user input before processing.

**Features:**
- HTML/script tag stripping
- Max length enforcement (10KB default)
- Unicode normalization (NFC form)
- Prompt injection pattern detection
- Configurable per-channel rules

**Patterns to Detect:**
- Instruction overrides: "ignore previous", "forget your rules"
- Role manipulation: "you are now", "pretend to be"
- Format exploits: fake system messages, delimiter injection
- Code injection: shell metacharacters, SQL keywords

**CLI:**
```bash
python tools/security/sanitizer.py --input "Hello world"  # Returns sanitized
python tools/security/sanitizer.py --input "<script>alert(1)</script>"  # Returns stripped
python tools/security/sanitizer.py --check --input "ignore instructions"  # Returns risk assessment
```

---

### 4. Rate Limiter (`tools/security/ratelimit.py`)

**Purpose:** Prevent abuse through request throttling.

**Features:**
- Token bucket algorithm with configurable refill rate
- Per-user, per-channel, and global limits
- Cost-based tracking (API spend)
- Burst allowance for legitimate spikes
- Clear error messages with retry-after

**Database Schema:**
```sql
CREATE TABLE rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT CHECK(entity_type IN ('user', 'channel', 'global')),
    entity_id TEXT NOT NULL,
    bucket_tokens REAL,
    last_refill DATETIME,
    cost_hour REAL DEFAULT 0,
    cost_day REAL DEFAULT 0,
    cost_reset_hour DATETIME,
    cost_reset_day DATETIME,
    UNIQUE(entity_type, entity_id)
);
```

**CLI:**
```bash
python tools/security/ratelimit.py --check --user alice --cost 0.01
python tools/security/ratelimit.py --consume --user alice --tokens 5 --cost 0.05
python tools/security/ratelimit.py --status --user alice
python tools/security/ratelimit.py --reset --user alice
```

---

### 5. Session Manager (`tools/security/session.py`)

**Purpose:** Track authenticated sessions with security controls.

**Features:**
- 256-bit random session tokens (secrets.token_bytes(32))
- Configurable TTL (default 24h, max 7d)
- Channel/device binding
- Activity tracking with idle timeout
- Force logout capability

**Database Schema:**
```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    channel TEXT,
    device_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    last_activity DATETIME,
    is_active INTEGER DEFAULT 1,
    metadata TEXT  -- JSON blob
);
```

**CLI:**
```bash
python tools/security/session.py --action create --user alice --channel discord
python tools/security/session.py --action validate --token "abc123..."
python tools/security/session.py --action refresh --token "abc123..."
python tools/security/session.py --action revoke --token "abc123..."
python tools/security/session.py --action revoke-all --user alice
```

**Security Notes:**
- Store only token hash (SHA-256), never raw token
- Return raw token only on creation
- Validate both token and expiry on every check

---

### 6. Permission System (`tools/security/permissions.py`)

**Purpose:** Role-based access control for all operations.

**Features:**
- 5 default roles: guest, user, power_user, admin, owner
- Permission check before every action
- Elevation prompts for sensitive ops
- Custom role creation

**Database Schema:**
```sql
CREATE TABLE roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    permissions TEXT,  -- JSON array of permission strings
    priority INTEGER DEFAULT 0
);

CREATE TABLE user_roles (
    user_id TEXT NOT NULL,
    role_name TEXT NOT NULL,
    granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    granted_by TEXT,
    expires_at DATETIME,
    PRIMARY KEY(user_id, role_name)
);
```

**Permission Format:**
```
resource:action
memory:read
memory:write
secrets:access
admin:users
admin:config
*:*  (owner only)
```

**CLI:**
```bash
python tools/security/permissions.py --check --user alice --permission "memory:write"
python tools/security/permissions.py --grant --user bob --role power_user
python tools/security/permissions.py --revoke --user bob --role power_user
python tools/security/permissions.py --list-roles
python tools/security/permissions.py --create-role --name "beta_tester" --permissions '["memory:read", "experimental:*"]'
```

---

## Implementation Order

1. **Audit Logger** — Needed by all other components for logging
2. **Secrets Vault** — Needed for secure API key storage
3. **Input Sanitizer** — Independent, but should be early
4. **Rate Limiter** — Depends on audit for logging
5. **Session Manager** — Depends on audit for logging
6. **Permission System** — Depends on sessions for user context

---

## Verification Checklist

- [ ] `audit.py --action log` creates entries
- [ ] `audit.py --action query` returns filtered results
- [ ] `vault.py --action set/get` round-trips correctly
- [ ] `vault.py` fails safely without master key
- [ ] `sanitizer.py` strips HTML tags
- [ ] `sanitizer.py` detects "ignore previous instructions"
- [ ] `ratelimit.py` blocks after limit exceeded
- [ ] `ratelimit.py` refills tokens over time
- [ ] `session.py` creates and validates sessions
- [ ] `session.py` expires sessions correctly
- [ ] `permissions.py` blocks unauthorized access
- [ ] `permissions.py` allows authorized access
- [ ] All tools have `--help` documentation
- [ ] All tools return JSON output

---

## Configuration References

- `args/security.yaml` — Session TTL, auth settings, audit retention
- `args/rate_limits.yaml` — Token limits, cost tracking, exemptions
- `hardprompts/security/validate_input.md` — Injection detection prompt

---

## Output

When complete, update `tools/manifest.md` with the new security tools section.
