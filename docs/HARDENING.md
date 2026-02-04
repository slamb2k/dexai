# DexAI Security Hardening Guide

This guide covers security best practices for deploying DexAI in production.

## Table of Contents

1. [System Hardening](#system-hardening)
2. [AI/API Hardening](#aiapi-hardening)
3. [Gateway Hardening](#gateway-hardening)
4. [Client Hardening](#client-hardening)
5. [Monitoring & Auditing](#monitoring--auditing)

---

## System Hardening

### Create Dedicated User

Run DexAI as a non-root user without sudo access:

```bash
# Create system user
sudo useradd -r -s /bin/false -d /opt/dexai dexai

# Set ownership
sudo chown -R dexai:dexai /opt/dexai

# Restrict permissions
sudo chmod 700 /opt/dexai/data
sudo chmod 600 /opt/dexai/.env
```

### File Permissions

| Path | Permission | Reason |
|------|------------|--------|
| `/opt/dexai/data/` | 700 | SQLite databases contain sensitive data |
| `/opt/dexai/.env` | 600 | Contains API keys and secrets |
| `/opt/dexai/memory/` | 700 | User conversation history |
| `/opt/dexai/args/` | 644 | Configuration files (read-only ok) |

### Firewall Configuration

Using UFW (Uncomplicated Firewall):

```bash
# Enable firewall
sudo ufw enable

# Allow SSH (adjust port if changed)
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS (if using Caddy)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow Tailscale (if using)
sudo ufw allow 41641/udp

# Deny everything else
sudo ufw default deny incoming
sudo ufw default allow outgoing
```

### SSH Hardening

Edit `/etc/ssh/sshd_config`:

```
# Disable root login
PermitRootLogin no

# Disable password authentication (use keys)
PasswordAuthentication no

# Limit users who can SSH
AllowUsers your-admin-user

# Change default port (optional)
Port 2222
```

### Automatic Security Updates

For Ubuntu/Debian:

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## AI/API Hardening

### API Key Security

1. **Use environment variables, not files**:
   ```bash
   # Good: In .env file (600 permissions)
   ANTHROPIC_API_KEY=sk-ant-...

   # Bad: Hardcoded in code
   # api_key = "sk-ant-..."
   ```

2. **Set usage limits** in Anthropic Console:
   - Monthly spending cap
   - Per-request limits

3. **Rotate keys regularly**:
   - Generate new key monthly
   - Revoke old keys after confirming new key works

### Rate Limiting

Configure in `args/security.yaml`:

```yaml
rate_limiting:
  enabled: true

  # Per-user limits
  user:
    requests_per_minute: 20
    requests_per_hour: 200
    daily_cost_limit_usd: 5.00

  # Global limits
  global:
    requests_per_minute: 100
    daily_cost_limit_usd: 50.00
```

### Cost Controls

Configure in `args/agent.yaml`:

```yaml
agent:
  model: claude-sonnet-4-20250514

  limits:
    max_tokens_per_request: 4096
    max_tool_uses_per_request: 10
    daily_cost_limit_usd: 10.00

  # Require confirmation for expensive operations
  confirm_expensive_ops:
    threshold_usd: 1.00
    message: "This operation will cost approximately ${cost}. Continue?"
```

### Prompt Injection Protection

The sanitizer is enabled by default. Configure in `args/security.yaml`:

```yaml
sanitizer:
  enabled: true

  # Block suspicious patterns
  patterns:
    - "ignore previous instructions"
    - "system prompt"
    - "jailbreak"

  # Action on detection
  action: block  # or: warn, log

  # Log all sanitization events
  log_events: true
```

---

## Gateway Hardening

### TLS Configuration

Caddy handles TLS automatically. For manual configuration:

```
# In Caddyfile
{
    # Use only TLS 1.2+
    default_sni localhost
}

example.com {
    tls {
        protocols tls1.2 tls1.3
        ciphers TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384 TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
    }
}
```

### CORS Configuration

In `args/dashboard.yaml`:

```yaml
dashboard:
  security:
    # Restrict to specific origins
    allowed_origins:
      - "https://dexai.example.com"
      - "https://admin.example.com"

    # Never use "*" in production
    # allowed_origins: ["*"]  # BAD!
```

### Session Security

Configure in `args/security.yaml`:

```yaml
sessions:
  # Session lifetime
  ttl_minutes: 60

  # Max sessions per user
  max_concurrent: 3

  # Bind session to channel
  channel_binding: true

  # Require re-auth after inactivity
  idle_timeout_minutes: 30

  # IP allowlist (optional)
  # ip_allowlist:
  #   - "192.168.1.0/24"
  #   - "10.0.0.0/8"
```

### WebSocket Security

```yaml
websocket:
  # Ping/pong for connection health
  ping_interval_seconds: 30

  # Max message size
  max_message_size_kb: 64

  # Rate limit WebSocket messages
  rate_limit:
    messages_per_second: 10
```

---

## Client Hardening

### Channel Bot Security

#### Telegram

1. Enable 2FA on your Telegram account
2. Use BotFather to set bot privacy mode
3. Restrict bot to specific chats if possible

```bash
# Rotate token
# 1. Create new token with @BotFather
# 2. Update in vault
python tools/channels/telegram_adapter.py --set-token NEW_TOKEN
# 3. Revoke old token with @BotFather
```

#### Discord

1. Enable 2FA on Discord account
2. Use minimal bot permissions
3. Review OAuth scopes

Required permissions (minimal):
- Send Messages
- Read Message History
- Use Slash Commands

```bash
# Rotate token
# 1. Regenerate in Discord Developer Portal
# 2. Update
python tools/channels/discord.py --set-token NEW_TOKEN
```

#### Slack

1. Use minimal OAuth scopes
2. Enable IP allowlist if available
3. Review app home and event subscriptions

Minimal scopes:
- `chat:write`
- `im:history`
- `im:read`
- `commands`

### Session Management

Review active sessions regularly:

```bash
# List active sessions
python tools/security/session.py --list

# Revoke suspicious sessions
python tools/security/session.py --revoke SESSION_ID
```

---

## Monitoring & Auditing

### Enable Audit Logging

Audit logging is enabled by default. Configure in `args/security.yaml`:

```yaml
audit:
  enabled: true

  # Log these events
  events:
    - authentication
    - authorization
    - command_execution
    - data_access
    - configuration_change
    - security_violation

  # Retention
  retention_days: 90

  # Export to external system (optional)
  # export:
  #   type: syslog
  #   server: logs.example.com:514
```

### Review Audit Logs

```bash
# View recent security events
python tools/security/audit.py --query --type security --limit 50

# Export for analysis
python tools/security/audit.py --export --format json --output audit.json
```

### Set Up Alerts

Configure alerts for security events in `args/smart_notifications.yaml`:

```yaml
smart_notifications:
  security_alerts:
    enabled: true

    # Alert on these events
    events:
      - failed_authentication
      - rate_limit_exceeded
      - permission_denied
      - suspicious_content

    # Send to admin channel
    channel: telegram
    admin_user_id: "123456789"
```

### Regular Security Tasks

| Task | Frequency | Command |
|------|-----------|---------|
| Review audit logs | Daily | `make logs \| grep -i security` |
| Check for updates | Weekly | `git fetch && git status` |
| Rotate API keys | Monthly | See API Key Security section |
| Rotate bot tokens | Quarterly | See Client Hardening section |
| Review permissions | Quarterly | `python tools/security/permissions.py --audit` |
| Backup databases | Daily | `make db-backup` |

---

## Incident Response

### If You Suspect a Compromise

1. **Isolate**: Stop all services
   ```bash
   docker compose down
   # or
   sudo systemctl stop dexai
   ```

2. **Rotate credentials**:
   - Generate new DEXAI_MASTER_KEY
   - Rotate all API keys
   - Rotate all bot tokens

3. **Review logs**:
   ```bash
   python tools/security/audit.py --query --since "24 hours ago"
   ```

4. **Revoke sessions**:
   ```bash
   python tools/security/session.py --revoke-all
   ```

5. **Update and restart**:
   ```bash
   git pull
   docker compose build --no-cache
   docker compose up -d
   ```

### Security Contact

For security issues, please email security@example.com or open a private security advisory on GitHub.

---

## Checklist

Use this checklist before going to production:

- [ ] Created dedicated `dexai` user
- [ ] Set correct file permissions (700/600)
- [ ] Configured firewall
- [ ] Disabled root SSH login
- [ ] Enabled automatic security updates
- [ ] Set API usage limits in Anthropic Console
- [ ] Configured rate limiting in DexAI
- [ ] Set daily cost limits
- [ ] Enabled sanitizer
- [ ] Configured CORS with specific origins
- [ ] Set session timeouts
- [ ] Enabled 2FA on all admin accounts
- [ ] Reviewed bot permissions
- [ ] Enabled audit logging
- [ ] Set up security alerts
- [ ] Scheduled regular security reviews
- [ ] Tested backup and restore
- [ ] Documented incident response plan
