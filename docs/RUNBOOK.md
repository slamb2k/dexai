# DexAI Operational Runbook

Operational procedures for diagnosing and resolving common failure scenarios.
Each scenario includes symptoms, diagnosis steps, resolution, and prevention guidance.

**Key paths referenced throughout:**

| Resource | Path |
|----------|------|
| SQLite databases | `data/audit.db`, `data/dashboard.db`, `data/sessions.db`, `data/memory.db`, `data/vault.db` |
| Backups | `backups/` |
| Migrations | `migrations/*.sql` |
| Vault salt (legacy) | `data/.vault_salt` |
| Routing config | `args/routing.yaml` |
| Dashboard config | `args/dashboard.yaml` |
| Office config | `args/office_integration.yaml` |
| Docker Compose | `docker-compose.yml` |
| Logs | Container stdout / `docker compose logs` |

---

## Scenario 1: Vault Corruption

**Severity:** Critical
**Symptoms:**
- All API calls fail with `"Master key not set"` or `"Decryption failed"` errors
- `python tools/security/vault.py --action status` reports `ready: false`
- Audit log shows repeated `secret / get / failure` events
- Salt migration warning in logs: `"Legacy salt file detected, migrating to HKDF-derived salt"`
- Services that depend on vault-stored credentials (OAuth, channel tokens) stop working

**Diagnosis:**

```bash
# 1. Check vault status
source .venv/bin/activate
python tools/security/vault.py --action status

# 2. Verify the master key env var is set
echo "${DEXAI_MASTER_KEY:+SET}" || echo "NOT SET"

# 3. Check if the vault database exists and is readable
sqlite3 data/vault.db "PRAGMA integrity_check;"
sqlite3 data/vault.db "SELECT COUNT(*) FROM secrets;"

# 4. Check if legacy salt file is still present (indicates failed migration)
ls -la data/.vault_salt

# 5. Check recent audit events for vault failures
python tools/security/audit.py --action query --type secret --status failure --since 1h

# 6. Check if the cryptography package is installed
python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; print('OK')"
```

**Resolution:**

*Case A: Master key lost or changed*

The master key (`DEXAI_MASTER_KEY`) is the root of all encryption. If it was changed
or lost, existing secrets cannot be decrypted.

```bash
# If you have the OLD master key and want to rotate to a new one:
python tools/security/vault.py --action rotate-key \
  --old-key "old-master-password" \
  --new-key "new-master-password"

# Update .env with the new key
# DEXAI_MASTER_KEY=new-master-password
```

If the old key is truly lost, secrets must be re-entered manually:

```bash
# List what secrets existed (keys only, values are gone)
sqlite3 data/vault.db "SELECT namespace, key FROM secrets;"

# Re-set each secret with the current master key
export DEXAI_MASTER_KEY="your-current-key"
python tools/security/vault.py --action set --key ANTHROPIC_API_KEY --value "sk-ant-..."
python tools/security/vault.py --action set --key OPENROUTER_API_KEY --value "..."
```

*Case B: Vault database corrupted*

```bash
# Restore from backup
ls -lt backups/vault_*.db.gz | head -5

# Decompress and replace
gunzip -k backups/vault_20260101_120000.db.gz
cp data/vault.db data/vault.db.corrupt
cp backups/vault_20260101_120000.db data/vault.db

# Verify restored database
python tools/security/vault.py --action status
python tools/security/vault.py --action list
```

*Case C: Salt migration failure*

If `data/.vault_salt` still exists after a crash during migration:

```bash
# The vault.py _migrate_salt() function re-encrypts all secrets from
# legacy random salt to HKDF-derived salt. If it crashed mid-way,
# some secrets may use old salt and some new.

# 1. Restore vault.db from the most recent backup
cp backups/vault_LATEST.db data/vault.db

# 2. Ensure the legacy salt file is in place
ls -la data/.vault_salt

# 3. Re-run any vault operation - migration triggers automatically
python tools/security/vault.py --action list

# 4. Verify .vault_salt was removed (migration succeeded)
ls -la data/.vault_salt 2>/dev/null && echo "MIGRATION INCOMPLETE" || echo "MIGRATION OK"
```

**Prevention:**
- Back up `data/vault.db` before any master key rotation: `python -m tools.ops.backup --db data/vault.db`
- Store the master key in a separate password manager (not in the vault itself)
- Use `python -m tools.ops.backup` on a daily cron to maintain vault backups
- Monitor for `salt_migration` audit events after upgrades

---

## Scenario 2: API Provider Outage

**Severity:** High
**Symptoms:**
- User messages receive no response or timeout errors
- Logs show HTTP 429 (rate limit), 500, 502, or 503 errors from Anthropic or OpenRouter
- Circuit breaker logs: `"Circuit breaker for 'anthropic' OPENED (5 consecutive failures)"`
- Dashboard health endpoint (`/api/health`) reports degraded status
- Prometheus metric `dexai_circuit_breaker_state` shows value `2` (open) for a service

**Diagnosis:**

```bash
# 1. Check circuit breaker states via Prometheus metrics endpoint
curl -s http://localhost:8080/api/metrics/prometheus | grep circuit_breaker

# 2. Check circuit breaker states programmatically
python -c "
from tools.ops.circuit_breaker import circuit_breaker
import json
print(json.dumps(circuit_breaker.get_all_states(), indent=2, default=str))
"

# 3. Check the model router stats
python -c "
from tools.agent.model_router.model_router import ModelRouter
router = ModelRouter.from_config()
print(f'Profile: {router.profile.value}')
print(f'OpenRouter key set: {bool(router.openrouter_api_key)}')
print(f'Fallback enabled: {router.fallback_to_direct}')
"

# 4. Test provider connectivity directly
python -c "
import httpx, os
r = httpx.get('https://openrouter.ai/api/v1/models',
              headers={'Authorization': f\"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}\"}, timeout=10)
print(f'OpenRouter status: {r.status_code}')
"

# 5. Check recent routing decisions in dashboard DB
sqlite3 data/dashboard.db "SELECT * FROM routing_decisions ORDER BY created_at DESC LIMIT 10;"

# 6. Check for rate limit audit events
python tools/security/audit.py --action query --type rate_limit --since 1h
```

**Resolution:**

*Case A: Single provider down, others available*

```bash
# The circuit breaker automatically blocks the failing provider (threshold: 5 failures,
# recovery timeout: 60s). The model router _find_fallback_model() selects an
# alternative from a different provider.

# If auto-fallback is not working, manually switch routing profile:
# Edit args/routing.yaml - change profile to use available providers
#   routing:
#     profile: multi_provider    # Uses multiple providers instead of anthropic_only

# Or temporarily force a specific model for all requests:
# In args/routing.yaml, add:
#   routing_table:
#     critical: "gemini-2.5-pro"
#     high: "gpt-4o"
#     moderate: "gpt-4o"
#     low: "gemini-2.5-flash"
#     trivial: "gemini-2.5-flash"
```

*Case B: All providers failing*

```bash
# 1. Reset all circuit breakers to allow retry
python -c "
from tools.ops.circuit_breaker import circuit_breaker
circuit_breaker.reset()
print('All circuit breakers reset')
"

# 2. Check if the issue is network-level
curl -s https://openrouter.ai/api/v1/models | head -c 200
curl -s https://api.anthropic.com/v1/messages -H "x-api-key: test" 2>&1 | head -c 200

# 3. If network is fine, check API keys
python tools/security/vault.py --action get --key OPENROUTER_API_KEY
python tools/security/vault.py --action get --key ANTHROPIC_API_KEY

# 4. As a last resort, check OpenRouter/Anthropic status pages
# https://status.anthropic.com
# https://status.openrouter.ai
```

*Case C: Circuit breaker stuck open*

```bash
# Reset a specific service circuit
python -c "
from tools.ops.circuit_breaker import circuit_breaker
circuit_breaker.reset('anthropic')
print('Anthropic circuit reset')
"

# The circuit will transition to half_open and allow one test request.
# If it succeeds, it returns to closed. If it fails, back to open.
```

**Prevention:**
- Use `multi_provider` or `balanced` routing profile for automatic cross-provider failover
- Set `fallback_to_direct: true` in `args/routing.yaml` to allow direct Anthropic calls when OpenRouter is down
- Configure budget alerts to catch cost spikes from fallback models
- Monitor `dexai_circuit_breaker_state` metric with alerts on value = 2 (open)

---

## Scenario 3: Database Migration Failure

**Severity:** High
**Symptoms:**
- Dashboard backend fails to start with `"Migration XXXX failed"` error
- SQLite errors like `"table already exists"` or `"no such column"` on startup
- `schema_migrations` table shows partial migration state
- `python -m tools.ops.migrate --pending` shows migrations that should have been applied

**Diagnosis:**

```bash
# 1. List pending migrations
python -m tools.ops.migrate --pending

# 2. Check what migrations have been applied
sqlite3 data/audit.db "SELECT * FROM schema_migrations ORDER BY version;"

# 3. Check database integrity
sqlite3 data/audit.db "PRAGMA integrity_check;"
sqlite3 data/dashboard.db "PRAGMA integrity_check;"

# 4. Preview migrations without applying
python -m tools.ops.migrate --dry-run

# 5. Check the actual schema vs expected
sqlite3 data/audit.db ".schema audit_log"

# 6. Check if hash chain columns exist (migration 0004)
sqlite3 data/audit.db "PRAGMA table_info(audit_log);" | grep -E "entry_hash|previous_hash|trace_id"
```

**Resolution:**

*Case A: Migration partially applied (crash mid-migration)*

```bash
# 1. Back up the current database first
python -m tools.ops.backup --db data/audit.db

# 2. Check which migration failed
sqlite3 data/audit.db "SELECT * FROM schema_migrations ORDER BY version DESC LIMIT 1;"

# 3. Read the failed migration file to understand what it does
cat migrations/XXXX_description.sql

# 4. Manually complete the failed migration if partially applied
# For example, if a column was added but the index was not:
sqlite3 data/audit.db "CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_log(trace_id);"

# 5. Register the migration as complete
sqlite3 data/audit.db "INSERT INTO schema_migrations (version, filename) VALUES ('XXXX', 'XXXX_description.sql');"

# 6. Re-run remaining migrations
python -m tools.ops.migrate
```

*Case B: Schema mismatch (code expects columns that do not exist)*

```bash
# The migration system is forward-only. Apply all pending migrations:
python -m tools.ops.migrate

# If a specific migration file is missing from migrations/:
# Check git history for the file
git log --all --full-history -- "migrations/XXXX_*.sql"
```

*Case C: Corrupted SQLite database*

```bash
# 1. Run integrity check
sqlite3 data/audit.db "PRAGMA integrity_check;"

# 2. If integrity check fails, restore from backup
ls -lt backups/audit_*.db.gz | head -5
gunzip -k backups/audit_YYYYMMDD_HHMMSS.db.gz
cp data/audit.db data/audit.db.corrupt
cp backups/audit_YYYYMMDD_HHMMSS.db data/audit.db

# 3. Re-apply any migrations that were applied after the backup
python -m tools.ops.migrate

# 4. If no backup exists, attempt recovery
sqlite3 data/audit.db ".dump" > /tmp/audit_dump.sql
rm data/audit.db
sqlite3 data/audit.db < /tmp/audit_dump.sql
python -m tools.ops.migrate
```

**Prevention:**
- Run `python -m tools.ops.backup` before applying migrations
- The dashboard backend runs migrations automatically at startup (see `tools/dashboard/backend/main.py` lifespan handler) -- review logs after each deployment
- Enable WAL mode on all databases: `python -m tools.ops.backup --enable-wal`
- Test migrations on a copy first: `cp data/audit.db /tmp/test.db && python -m tools.ops.migrate --db /tmp/test.db`

---

## Scenario 4: OAuth Token Expiry

**Severity:** Medium
**Symptoms:**
- Office integration commands (email, calendar) return `401 Unauthorized` errors
- Logs show `"Token refresh failed"` or `"Proactive token refresh failed for {provider}/{account_id}"`
- User reports that Google/Microsoft integrations suddenly stopped working
- `python tools/office/oauth_manager.py --provider google --action status` shows expired `token_expiry`

**Diagnosis:**

```bash
# 1. Check account status and token expiry
python tools/office/oauth_manager.py --provider google --action status --user-id default
python tools/office/oauth_manager.py --provider microsoft --action status --user-id default

# 2. Check token expiry directly in database
sqlite3 data/office.db "SELECT id, provider, email_address, token_expiry, updated_at FROM office_accounts;"

# 3. Check if refresh token exists in vault
python tools/security/vault.py --action list --namespace office_tokens

# 4. Check recent OAuth-related audit events
python tools/security/audit.py --action query --type secret --since 24h | grep office

# 5. Check if OAuth credentials (client ID/secret) are still valid
python -c "
from tools.office.oauth_manager import get_google_credentials, get_microsoft_credentials
try:
    cid, cs = get_google_credentials()
    print(f'Google: client_id={cid[:20]}...')
except ValueError as e:
    print(f'Google: {e}')
try:
    cid, cs, t = get_microsoft_credentials()
    print(f'Microsoft: client_id={cid[:20]}..., tenant={t}')
except ValueError as e:
    print(f'Microsoft: {e}')
"
```

**Resolution:**

*Case A: Access token expired but refresh token valid*

```bash
# The system proactively refreshes tokens within 5 minutes of expiry
# (see oauth_manager.py get_valid_access_token). To force a manual refresh:
python tools/office/oauth_manager.py --provider google --action refresh --account-id <ACCOUNT_ID>
```

*Case B: Refresh token expired or revoked*

Google refresh tokens can be revoked if the user removes app access, or if the
token has not been used for 6 months. Microsoft refresh tokens expire after 90 days
of inactivity.

```bash
# Re-authorize the user from scratch
python tools/office/oauth_manager.py --provider google --action authorize --level 2

# This prints an authorization URL. The user must:
# 1. Open the URL in a browser
# 2. Grant permissions
# 3. Copy the authorization code from the callback
# 4. Exchange it:
python tools/office/oauth_manager.py --provider google --action exchange --code <AUTH_CODE>
```

*Case C: Token refresh loop (refreshes succeed but new token immediately fails)*

```bash
# This can happen when scopes have been reduced on the provider side.
# Delete the account and re-authorize with correct scopes:
python -c "
from tools.office.oauth_manager import delete_account
result = delete_account('<ACCOUNT_ID>')
print(result)
"

# Re-authorize with the desired integration level
python tools/office/oauth_manager.py --provider google --action authorize --level 3
```

**Prevention:**
- The `get_valid_access_token()` function refreshes proactively 5 minutes before expiry
- Monitor `token_expiry` column in `office_accounts` table for upcoming expirations
- Store OAuth client credentials (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) in the vault, not just environment variables
- Set up a periodic task to test token validity (e.g., make a lightweight API call to the user info endpoint)
- Document the re-authorization flow for end users

---

## Scenario 5: Audit Chain Broken

**Severity:** High
**Symptoms:**
- `verify_hash_chain` returns `valid: false` with `broken_hashes` or `chain_breaks`
- Compliance check fails -- evidence of potential log tampering
- Hash chain verification message: `"Hash chain INVALID: N bad hashes, M chain breaks"`

**Diagnosis:**

```bash
# 1. Run hash chain verification
python -c "
from tools.security.audit import verify_hash_chain
import json
result = verify_hash_chain(limit=5000)
print(json.dumps(result, indent=2))
"

# 2. Check if hash chain columns exist (migration 0004)
sqlite3 data/audit.db "PRAGMA table_info(audit_log);" | grep -E "entry_hash|previous_hash"

# 3. Check for gaps in the ID sequence (deleted entries)
sqlite3 data/audit.db "
SELECT a.id + 1 AS gap_start, MIN(b.id) - 1 AS gap_end
FROM audit_log a
JOIN audit_log b ON b.id > a.id
WHERE NOT EXISTS (SELECT 1 FROM audit_log c WHERE c.id = a.id + 1)
  AND a.id + 1 < b.id
LIMIT 20;
"

# 4. Inspect specific broken entries
# Use the IDs from verify_hash_chain output:
sqlite3 data/audit.db "
SELECT id, timestamp, event_type, action, entry_hash, previous_hash
FROM audit_log WHERE id IN (<broken_ids>);
"

# 5. Check if cleanup was run (which would break the chain)
sqlite3 data/audit.db "
SELECT MIN(id), MAX(id), COUNT(*) FROM audit_log WHERE entry_hash IS NOT NULL;
"

# 6. Get audit log statistics
python tools/security/audit.py --action stats
```

**Resolution:**

*Case A: Chain broken by cleanup_old_events*

The `cleanup_old_events()` function deletes old entries, which removes links
from the hash chain. This is expected but breaks verification of the full chain.

```bash
# Verification should only cover entries AFTER the last cleanup.
# Find the first entry with a hash:
sqlite3 data/audit.db "
SELECT id, timestamp FROM audit_log
WHERE entry_hash IS NOT NULL
ORDER BY id ASC LIMIT 1;
"

# Verify only from that point forward -- the chain should be valid
# within the post-cleanup range.
```

*Case B: Entries genuinely tampered with*

```bash
# 1. Export the current audit log for forensic analysis
python tools/security/audit.py --action export --format json > /tmp/audit_export.json

# 2. Restore from the most recent backup to compare
python -m tools.ops.backup --db data/audit.db  # Back up current state first
gunzip -k backups/audit_YYYYMMDD_HHMMSS.db.gz
sqlite3 backups/audit_YYYYMMDD_HHMMSS.db ".dump" > /tmp/audit_backup.sql

# 3. Diff the entries around the broken chain point
# Compare entry hashes between current and backup databases

# 4. If tampering is confirmed, restore from the last known good backup
# and investigate how write access was obtained
```

*Case C: Hash chain columns not present*

```bash
# Migration 0004 adds hash chain columns. Apply it:
python -m tools.ops.migrate

# Verify columns now exist:
sqlite3 data/audit.db "PRAGMA table_info(audit_log);" | grep entry_hash

# Note: Only entries AFTER the migration will have hashes.
# Pre-migration entries will have NULL entry_hash/previous_hash.
```

**Prevention:**
- Run `python -m tools.ops.backup` before any `cleanup_old_events` call
- Export audit logs before cleanup: `python tools/security/audit.py --action export --since 90d --format json > archive.json`
- Restrict database file permissions: `chmod 600 data/audit.db`
- Consider shipping audit logs to an external append-only store for tamper evidence
- Run hash chain verification on a schedule and alert on failures

---

## Scenario 6: Memory System Degradation

**Severity:** Medium
**Symptoms:**
- Hybrid search returns empty or irrelevant results
- `"Failed to get embeddings"` errors in logs (embedding service down)
- BM25 search works but semantic search does not (or vice versa)
- Memory database queries are slow or time out
- `python tools/memory/memory_db.py --action search --query "test"` returns errors

**Diagnosis:**

```bash
# 1. Check memory database integrity
sqlite3 data/memory.db "PRAGMA integrity_check;"
sqlite3 data/memory.db "SELECT COUNT(*) FROM memory_entries;"

# 2. Check if the embedding service is reachable
python -c "
import os, httpx
key = os.environ.get('OPENAI_API_KEY', '')
if key:
    r = httpx.post('https://api.openai.com/v1/embeddings',
                    json={'model': 'text-embedding-3-small', 'input': 'test'},
                    headers={'Authorization': f'Bearer {key}'}, timeout=10)
    print(f'Embedding API status: {r.status_code}')
else:
    print('OPENAI_API_KEY not set')
"

# 3. Test memory search directly
python tools/memory/memory_db.py --action search --query "test"

# 4. Check hybrid search components
python tools/memory/hybrid_search.py --query "test"

# 5. Check database size (bloat can cause slowness)
ls -lh data/memory.db
sqlite3 data/memory.db "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();"

# 6. Check WAL file size (can grow unbounded under write pressure)
ls -lh data/memory.db-wal 2>/dev/null
```

**Resolution:**

*Case A: Embedding service down*

```bash
# Semantic search will fail but BM25 keyword search should still work.
# The hybrid search should gracefully degrade to BM25-only results.

# Check if the fallback is working:
python tools/memory/memory_db.py --action search --query "test"

# If OPENAI_API_KEY is not set, embeddings cannot be generated.
# Verify the key:
python tools/security/vault.py --action get --key OPENAI_API_KEY
```

*Case B: Memory database corrupted*

```bash
# 1. Back up the current (corrupted) database
cp data/memory.db data/memory.db.corrupt

# 2. Restore from backup
ls -lt backups/memory_*.db.gz | head -5
gunzip -k backups/memory_YYYYMMDD_HHMMSS.db.gz
cp backups/memory_YYYYMMDD_HHMMSS.db data/memory.db

# 3. If no backup, attempt recovery
sqlite3 data/memory.db.corrupt ".dump" > /tmp/memory_dump.sql
rm data/memory.db
sqlite3 data/memory.db < /tmp/memory_dump.sql

# 4. Re-index if search results are poor
python tools/memory/memory_db.py --action reindex
```

*Case C: Database too large / slow queries*

```bash
# 1. Enable WAL mode for concurrent reads
python -m tools.ops.backup --enable-wal

# 2. Vacuum to reclaim space
sqlite3 data/memory.db "VACUUM;"

# 3. Check for missing indexes
sqlite3 data/memory.db ".indexes"

# 4. Consider archiving old entries
sqlite3 data/memory.db "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM memory_entries;"
```

**Prevention:**
- Run `python -m tools.ops.backup` daily to maintain memory database backups
- Enable WAL mode: `python -m tools.ops.backup --enable-wal`
- Monitor memory database size and set alerts at thresholds (e.g., > 500MB)
- Keep `OPENAI_API_KEY` valid and monitor embedding API usage/quota
- Periodically vacuum the database: `sqlite3 data/memory.db "VACUUM;"`

---

## Scenario 7: Channel Disconnection

**Severity:** Medium
**Symptoms:**
- Bot stops responding in Telegram, Discord, or Slack
- Dashboard health check (`/api/health`) shows `channels: unhealthy` or `channels: degraded`
- Logs show `"Failed to register Telegram adapter"` or adapter connection errors
- Webhook delivery failures (HTTP 401, 403, or timeout) in channel provider dashboards

**Diagnosis:**

```bash
# 1. Check overall health including channels
curl -s http://localhost:8080/api/health | python -m json.tool

# 2. Check which adapters are registered
python -c "
try:
    from tools.channels.router import get_router
    import asyncio
    router = get_router()
    status = asyncio.run(router.get_status_async()) if hasattr(router, 'get_status_async') else router.get_status()
    import json
    print(json.dumps(status, indent=2, default=str))
except Exception as e:
    print(f'Error: {e}')
"

# 3. Check if bot tokens are set in environment
echo "TELEGRAM: ${TELEGRAM_BOT_TOKEN:+SET}"
echo "DISCORD: ${DISCORD_BOT_TOKEN:+SET}"
echo "SLACK: ${SLACK_BOT_TOKEN:+SET}"

# 4. Test Telegram bot token validity
python -c "
import os, httpx
token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
if token:
    r = httpx.get(f'https://api.telegram.org/bot{token}/getMe', timeout=10)
    print(f'Telegram bot status: {r.status_code} - {r.json()}')
else:
    print('TELEGRAM_BOT_TOKEN not set')
"

# 5. Check backend logs for adapter errors
docker compose logs backend --since 30m 2>/dev/null | grep -i -E "adapter|telegram|discord|slack|channel"
```

**Resolution:**

*Case A: Bot token expired or revoked*

```bash
# Telegram: Create a new token via @BotFather
# Discord: Regenerate token in Discord Developer Portal
# Slack: Regenerate token in Slack App settings

# Update the token in .env:
# TELEGRAM_BOT_TOKEN=new-token-here

# Restart the backend to pick up the new token
docker compose restart backend
```

*Case B: Webhook failures / rate limiting*

```bash
# Telegram rate limits: 30 messages/second to different chats, 1 message/second per chat
# Discord rate limits: Vary by endpoint (headers include X-RateLimit-*)

# Check if rate limiting audit events exist
python tools/security/audit.py --action query --type rate_limit --since 1h

# Restart the adapter to re-establish the connection
docker compose restart backend
```

*Case C: Adapter crashed but backend is running*

```bash
# The adapters are initialized during the FastAPI lifespan (tools/dashboard/backend/main.py).
# A full backend restart re-initializes all adapters:
docker compose restart backend

# Check logs to confirm adapters reconnected
docker compose logs backend --since 5m | grep -i "adapter"
```

**Prevention:**
- Monitor the `/api/health` endpoint for `channels: unhealthy` status
- Set up alerting on channel health degradation
- Store bot tokens in the vault rather than only in `.env` for rotation safety
- Implement webhook retry logic with exponential backoff
- Document the token regeneration process for each channel provider

---

## Scenario 8: Disk Space Exhaustion

**Severity:** High
**Symptoms:**
- SQLite writes fail with `"database or disk is full"` errors
- Backup operations fail silently or with write errors
- Log messages stop appearing
- Docker containers become unresponsive
- `df -h` shows filesystem at or near 100%

**Diagnosis:**

```bash
# 1. Check overall disk usage
df -h /

# 2. Check DexAI data directory sizes
du -sh data/
du -sh data/*.db data/*.db-wal data/*.db-shm 2>/dev/null
du -sh backups/
du -sh memory/logs/

# 3. Check SQLite WAL file sizes (can grow very large under write pressure)
ls -lh data/*.db-wal 2>/dev/null

# 4. Check backup accumulation
ls -lt backups/ | head -20
du -sh backups/

# 5. Check Docker volumes
docker system df 2>/dev/null

# 6. Check container-specific disk usage
docker compose exec backend du -sh /app/data/ 2>/dev/null

# 7. Check log size inside containers
docker compose logs --no-log-prefix backend 2>/dev/null | wc -l
```

**Resolution:**

*Step 1: Immediate space recovery*

```bash
# 1. Clean up old backups (keeps 7 daily + 4 weekly per database)
python -c "
from tools.ops.backup import enforce_retention
removed = enforce_retention(daily=3, weekly=2)
print(f'Removed {removed} old backup files')
"

# 2. Checkpoint and truncate WAL files
sqlite3 data/audit.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 data/dashboard.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 data/memory.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 data/sessions.db "PRAGMA wal_checkpoint(TRUNCATE);"

# 3. Clean up old daily log files
find memory/logs/ -name "*.md" -mtime +30 -delete

# 4. Vacuum databases to reclaim space
sqlite3 data/audit.db "VACUUM;"
sqlite3 data/dashboard.db "VACUUM;"
sqlite3 data/memory.db "VACUUM;"

# 5. Clean up Docker resources
docker system prune -f 2>/dev/null
```

*Step 2: Identify the root cause*

```bash
# Check which databases are growing fastest
for db in data/*.db; do
    echo "$db: $(du -sh "$db" | cut -f1) ($(sqlite3 "$db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';") tables)"
done

# Check audit log size and age
sqlite3 data/audit.db "
SELECT COUNT(*) as total,
       MIN(timestamp) as oldest,
       MAX(timestamp) as newest
FROM audit_log;
"

# Clean up old audit events (default: 90 day retention)
python tools/security/audit.py --action cleanup --retention-days 90 --dry-run
python tools/security/audit.py --action cleanup --retention-days 90
```

**Prevention:**
- Run `python -m tools.ops.backup` daily (includes retention enforcement: 7 daily + 4 weekly)
- Schedule periodic `PRAGMA wal_checkpoint(TRUNCATE)` on all databases
- Set up disk usage monitoring with alerts at 80% and 95%
- Configure audit log retention: `python tools/security/audit.py --action cleanup --retention-days 90`
- Add `--log-opt max-size=100m --log-opt max-file=3` to Docker container configuration for log rotation
- Enable WAL mode to reduce WAL file growth: `python -m tools.ops.backup --enable-wal`

---

## Scenario 9: Container Isolation Failure

**Severity:** High
**Symptoms:**
- `docker compose ps` shows containers in `Exit`, `Restarting`, or `OOMKilled` state
- Dashboard and/or API completely unreachable
- Backend health check fails: container returns non-zero exit code
- Errors like `"Cannot connect to the Docker daemon"` or `"permission denied while trying to connect to the Docker daemon socket"`
- Frontend shows blank page or connection refused

**Diagnosis:**

```bash
# 1. Check container status
docker compose ps

# 2. Check for OOM kills
docker inspect dexai-backend --format '{{.State.OOMKilled}}' 2>/dev/null
docker inspect dexai-frontend --format '{{.State.OOMKilled}}' 2>/dev/null

# 3. Check container resource usage
docker stats --no-stream 2>/dev/null

# 4. Check container logs for crash reasons
docker compose logs backend --tail 50
docker compose logs frontend --tail 50

# 5. Check Docker daemon status
systemctl status docker 2>/dev/null || service docker status

# 6. Check Docker socket permissions
ls -la /var/run/docker.sock

# 7. Check available system memory
free -h

# 8. Check if ports are already in use
ss -tlnp | grep -E ":(8080|3000)\s"
```

**Resolution:**

*Case A: Docker daemon down*

```bash
# Restart Docker daemon
sudo systemctl restart docker
# or: sudo service docker restart

# Wait for daemon to be ready
docker info >/dev/null 2>&1 && echo "Docker is running" || echo "Docker still starting..."

# Restart DexAI services
docker compose up -d
```

*Case B: Container OOM killed*

```bash
# The backend is limited to 4GB and frontend to 8GB (docker-compose.yml).

# 1. Check current memory limits
docker inspect dexai-backend --format '{{.HostConfig.Memory}}' 2>/dev/null
docker inspect dexai-frontend --format '{{.HostConfig.Memory}}' 2>/dev/null

# 2. If OOM is recurring, increase memory limits in docker-compose.yml:
#    backend:
#      mem_limit: 6g    # was 4g
#    frontend:
#      mem_limit: 8g
#      environment:
#        - NODE_OPTIONS=--max-old-space-size=6144  # was 4096

# 3. Restart with new limits
docker compose up -d

# 4. For WSL2 environments, check WSL memory limit
cat /proc/meminfo | grep MemTotal
# If too low, edit ~/.wslconfig on the Windows host:
# [wsl2]
# memory=8GB
```

*Case C: Port conflicts*

```bash
# Check what is using the ports
ss -tlnp | grep -E ":(8080|3000)\s"

# Kill the conflicting process or change ports in .env:
# DEXAI_BACKEND_PORT=8081
# DEXAI_FRONTEND_PORT=3001

# Restart
docker compose down && docker compose up -d
```

*Case D: Docker socket permission denied*

```bash
# Add current user to the docker group
sudo usermod -aG docker $USER

# OR: Fix socket permissions
sudo chmod 666 /var/run/docker.sock

# Note: Container isolation (V-10/S-4) requires mounting the Docker socket.
# This is disabled by default in docker-compose.yml. Only enable if needed:
#   volumes:
#     - /var/run/docker.sock:/var/run/docker.sock
```

*Case E: Container restart loop*

```bash
# 1. Check exit code and reason
docker inspect dexai-backend --format '{{.State.ExitCode}} {{.State.Error}}' 2>/dev/null

# 2. Common causes:
#    - Missing .env file: cp .env.example .env and fill in required values
#    - Database lock: Stop containers, check for zombie processes
#    - Import errors: Check Python dependencies

# 3. Run backend outside Docker to debug
source .venv/bin/activate
python -m tools.dashboard.backend.main

# 4. If the issue is a locked database
docker compose down
# Wait for all processes to exit
sqlite3 data/dashboard.db "PRAGMA integrity_check;"
docker compose up -d
```

**Prevention:**
- Set appropriate memory limits in `docker-compose.yml` based on available host resources
- Monitor container health: `docker compose ps` and the `/api/health` endpoint
- Use Docker's built-in restart policy (`restart: unless-stopped` is already set)
- For WSL2: Configure adequate memory in `~/.wslconfig`
- Set up container log rotation to prevent log-driven disk exhaustion
- Run `docker system prune` periodically to clean up unused images/volumes
- Back up Docker volumes before upgrades: `docker compose down && tar czf dexai-data-backup.tar.gz /var/lib/docker/volumes/dexai_dexai-data/`
