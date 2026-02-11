---
name: setup
description: DexAI onboarding and configuration
triggers:
  - "run setup"
  - "setup again"
  - "redo setup"
  - "reconfigure"
  - "update preferences"
  - "update my preferences"
  - "bootstrap dex"
  - "initialise dex"
  - "initialize dex"
  - "configure channels"
  - "change my timezone"
  - "change my name"
  - "update active hours"
  - "personalise"
  - "personalize"
args:
  - all
  - core
  - channels
  - preferences
  - adhd
---

# Setup Skill

Deterministic onboarding and configuration flow for DexAI.

This skill is **not LLM-driven** — it runs as a field-by-field deterministic flow
through `tools/dashboard/backend/services/setup_flow.py`. The chat service detects
trigger phrases (listed above) and routes them to the setup flow service.

## Execution Model

1. Trigger detection via regex in `chat_service.py`
2. `SetupFlowService` intercept (existing pattern)
3. Deterministic field-by-field flow with skip support
4. Yields chunk/control/done to frontend via WebSocket

## Scopes

| Scope | Fields |
|-------|--------|
| `all` | All required + optional fields |
| `core` | API key, name, timezone |
| `channels` | Primary channel + tokens |
| `preferences` | Schedule, notification, brevity |
| `adhd` | Work focus, energy, challenges, encouragement |

## Re-entry

Users can say "run setup again", "update my preferences", "configure channels",
etc. to re-enter the flow scoped to specific field groups.
