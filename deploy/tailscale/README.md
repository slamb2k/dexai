# Tailscale Setup for DexAI

Tailscale provides secure, zero-config networking for DexAI. This allows you to access your DexAI instance from anywhere without exposing it to the public internet.

## Benefits

- **No port forwarding** - Works behind NAT and firewalls
- **Automatic HTTPS** - Tailscale provides certificates
- **MagicDNS** - Access via `dexai.your-tailnet.ts.net`
- **ACLs** - Fine-grained access control
- **SSO** - Use your existing identity provider

## Quick Start

### 1. Create Tailscale Account

Sign up at https://tailscale.com if you don't have an account.

### 2. Generate Auth Key

1. Go to https://login.tailscale.com/admin/settings/keys
2. Click "Generate auth key"
3. Settings:
   - Reusable: Yes (for container restarts)
   - Ephemeral: No (keep the device when container stops)
   - Pre-authorized: Yes (skip manual authorization)
4. Copy the key (starts with `tskey-auth-`)

### 3. Configure DexAI

Add the auth key to your `.env` file:

```bash
TAILSCALE_AUTHKEY=tskey-auth-your-key-here
```

### 4. Start with Tailscale

```bash
docker compose --profile tailscale up -d
```

### 5. Access DexAI

Once running, access DexAI at:
- `https://dexai.your-tailnet.ts.net` (if using Tailscale Serve)
- `http://100.x.x.x:3000` (direct IP access)

Check the Tailscale admin console to find your device's IP.

## Tailscale Serve (Optional)

Tailscale Serve provides automatic HTTPS without Caddy. Create `tailscale-serve.json`:

```json
{
  "TCP": {
    "443": {
      "HTTPS": true
    }
  },
  "Web": {
    "dexai.your-tailnet.ts.net:443": {
      "Handlers": {
        "/": {
          "Proxy": "http://frontend:3000"
        },
        "/api/": {
          "Proxy": "http://backend:8080"
        },
        "/ws": {
          "Proxy": "http://backend:8080"
        }
      }
    }
  }
}
```

## Security Recommendations

### 1. Use ACLs

Add these rules to your Tailscale ACL policy:

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["group:admins"],
      "dst": ["tag:dexai:*"]
    }
  ],
  "tagOwners": {
    "tag:dexai": ["group:admins"]
  }
}
```

### 2. Rotate Auth Keys

- Create a new auth key monthly
- Delete old keys from admin console
- Update `TAILSCALE_AUTHKEY` in `.env`

### 3. Monitor Connections

Use the Tailscale admin console to:
- Review connected devices
- Check access logs
- Revoke suspicious devices

## Troubleshooting

### Container won't start

Check if the auth key is valid:
```bash
docker logs dexai-tailscale
```

### Can't reach the service

1. Verify the container is running:
   ```bash
   docker compose ps
   ```

2. Check Tailscale status:
   ```bash
   docker exec dexai-tailscale tailscale status
   ```

3. Verify you're connected to the same tailnet

### DNS not resolving

Enable MagicDNS in Tailscale admin:
https://login.tailscale.com/admin/dns

## Alternative: Funnel (Public Access)

If you need public access (not recommended for personal use):

```bash
# Inside the container
tailscale funnel 443 on
```

This exposes your service to the public internet via Tailscale's infrastructure.
