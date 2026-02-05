# DexAI Installation Guide

This guide covers manual installation and configuration of DexAI.

## Quick Start

The easiest way to install DexAI is using the automated installer:

```bash
curl -fsSL https://raw.githubusercontent.com/slamb2k/dexai/main/install.sh | bash
```

The installer will guide you through dependency checks, installation, and setup.

---

## Manual Installation

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | Required |
| Git | Any | Required |
| Node.js/npm | 18+ | Required for local frontend |
| Docker | 24+ | Required for container deployment |
| Docker Compose | v2 | Included with Docker Desktop |

### Step 1: Clone the Repository

```bash
git clone https://github.com/slamb2k/dexai.git ~/dexai
cd ~/dexai
```

### Step 2: Create Virtual Environment

Using uv (recommended - fastest):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv .venv
source .venv/bin/activate
```

Using standard venv:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Python Dependencies

Core dependencies:
```bash
pip install -e .
```

With optional features:
```bash
# All messaging channels
pip install -e ".[telegram,discord,slack]"

# Office integration
pip install -e ".[office]"

# Everything
pip install -e ".[telegram,discord,slack,office,dev]"
```

### Step 4: Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Generate a secure master key
echo "DEXAI_MASTER_KEY=$(openssl rand -hex 32)" >> .env

# Edit .env to add your API keys
nano .env
```

Required environment variables:
- `DEXAI_MASTER_KEY` - Generated automatically, used for encryption
- `ANTHROPIC_API_KEY` - Your Anthropic API key for Claude

Optional (based on channels):
- `TELEGRAM_BOT_TOKEN` - From [@BotFather](https://t.me/botfather)
- `DISCORD_BOT_TOKEN` - From [Discord Developer Portal](https://discord.com/developers/applications)
- `SLACK_BOT_TOKEN` - From [Slack API](https://api.slack.com/apps)
- `SLACK_APP_TOKEN` - For Socket Mode

### Step 5: Initialize Databases

```bash
make db-init
```

Or manually:
```bash
python -c "from tools.dashboard.backend.database import init_db; init_db()"
python -c "from tools.memory.memory_db import get_connection; get_connection().close()"
python -c "from tools.security.vault import init_vault; init_vault()"
```

### Step 6: Run Setup Wizard

```bash
python -m tools.setup.tui.main
```

---

## Deployment Options

### Option A: Local Development

Best for testing and development.

1. Install frontend dependencies:
   ```bash
   cd tools/dashboard/frontend
   npm install  # or: bun install / pnpm install
   cd ../../..
   ```

2. Start all services:
   ```bash
   make dev
   ```

3. Access the dashboard:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8080

### Option B: Docker Compose

Best for production deployment.

1. Build and start containers:
   ```bash
   docker compose up -d
   ```

2. Check status:
   ```bash
   docker compose ps
   docker compose logs -f
   ```

3. Access the dashboard:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8080

4. Stop services:
   ```bash
   docker compose down
   ```

### Option C: Docker with Reverse Proxy

For production with HTTPS:

1. Configure your domain in `.env`:
   ```bash
   DEXAI_DOMAIN=dexai.yourdomain.com
   DEXAI_ADMIN_EMAIL=admin@yourdomain.com
   ```

2. Start with the proxy profile:
   ```bash
   docker compose --profile proxy up -d
   ```

Caddy will automatically obtain SSL certificates from Let's Encrypt.

### Option D: Docker with Tailscale

For secure access without exposing ports:

1. Get a Tailscale auth key from https://login.tailscale.com/admin/settings/keys

2. Configure in `.env`:
   ```bash
   TAILSCALE_AUTHKEY=tskey-auth-xxxxx
   ```

3. Start with the Tailscale profile:
   ```bash
   docker compose --profile tailscale up -d
   ```

---

## Verifying Installation

### Check Backend Health

```bash
curl http://localhost:8080/api/health
```

Expected response:
```json
{"status": "healthy", "version": "1.0.0"}
```

### Check Frontend

Open http://localhost:3000 in your browser.

### Run Tests

```bash
make test
```

---

## Troubleshooting

### Python venv fails on Debian/Ubuntu

Install the venv package:
```bash
sudo apt install python3.11-venv
```

Or use uv which doesn't require system venv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv .venv
```

### Docker permission denied

Add your user to the docker group:
```bash
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

### Port already in use

Check what's using the port:
```bash
lsof -i :8080  # Backend port
lsof -i :3000  # Frontend port
```

Kill the process or change the port in `.env`:
```bash
DEXAI_BACKEND_PORT=8081
DEXAI_FRONTEND_PORT=3001
```

### Docker build fails

Ensure Docker has enough resources:
- At least 4GB RAM allocated
- At least 20GB disk space

Clean up and rebuild:
```bash
docker compose down -v
docker system prune -f
docker compose build --no-cache
```

### Database errors

Reset databases:
```bash
rm -rf data/*.db
make db-init
```

---

## Updating

### Local Installation

```bash
cd ~/dexai
git pull
source .venv/bin/activate
pip install -e .
make db-init  # Apply any new migrations
```

### Docker Installation

```bash
cd ~/dexai
git pull
docker compose down
docker compose build
docker compose up -d
```

---

## Uninstalling

### Local Installation

```bash
rm -rf ~/dexai
rm -rf ~/.local/share/dexai  # If exists
```

### Docker Installation

```bash
cd ~/dexai
docker compose down -v --rmi local
cd ~
rm -rf ~/dexai
```

---

## Next Steps

After installation:

1. **Configure channels** - Run the setup wizard to connect Telegram, Discord, or Slack
2. **Add your API key** - Set `ANTHROPIC_API_KEY` in `.env`
3. **Customize settings** - Edit files in `args/` directory
4. **Review security** - See [HARDENING.md](./HARDENING.md) for production security

For more help:
- GitHub Issues: https://github.com/slamb2k/dexai/issues
- Documentation: https://github.com/slamb2k/dexai/tree/main/docs
