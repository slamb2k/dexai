# Goals Manifest

Index of all available goal workflows. Check here before creating new goals.

---

## Available Goals

| Goal | Description |
|------|-------------|
| `prd_dexai_v1.md` | **Active PRD** — DexAI: Personal Assistant for Neuro-Divergent Users (ADHD focus) |
| `future_roadmap.md` | **Roadmap** — Phases 10-14 future development plans (mobile, voice, office, collaboration, analytics) |
| `memory_providers_design.md` | **Design Doc** — Pluggable memory provider architecture (native, Mem0, Zep, SimpleMem, ClaudeMem) |
| `phase9_ci_testing.md` | Phase 9 tactical implementation guide — CI/CD, pytest, Vitest, GitHub Actions |
| `phase10_mobile_push.md` | Phase 10 tactical implementation guide — Mobile push notifications (Web Push, PWA, Expo) |
| `phase11_voice_interface.md` | Phase 11 tactical implementation guide — Voice interface (Web Speech, Whisper, wake word, TTS) |
| `phase12_office_integration.md` | Phase 12 tactical implementation guide — Office integration with 5 levels (Google, Microsoft) |
| `phase12b_collaborative.md` | Phase 12b tactical implementation guide — Collaborative office (drafts, meeting scheduling) |
| `phase12c_managed_proxy.md` | Phase 12c tactical implementation guide — Managed proxy (send with undo, audit trail) |
| `phase12d_autonomous.md` | Phase 12d tactical implementation guide — Autonomous (policy-based automation, emergency controls) |
| `build_app.md` | ATLAS workflow for building full-stack applications with AI assistance |
| `phase1_security.md` | Phase 1 tactical implementation guide — security tools (vault, audit, sanitizer, etc.) |
| `phase2_working_memory.md` | Phase 2 tactical implementation guide — external working memory (context capture, commitments) |
| `phase3_adhd_comms.md` | Phase 3 tactical implementation guide — ADHD-friendly communication (brevity, RSD-safe) |
| `phase4_smart_notifications.md` | Phase 4 tactical implementation guide — smart notifications (flow protection, transition time) |
| `phase5_task_engine.md` | Phase 5 tactical implementation guide — ADHD task decomposition and friction solving |
| `phase6_learning.md` | Phase 6 tactical implementation guide — energy patterns, behavior learning, task matching |
| `phase7_dashboard.md` | Phase 7 tactical implementation guide — web dashboard with Dex avatar and monitoring |
| `phase8_installation.md` | Phase 8 tactical implementation guide — guided setup wizard (web + TUI) |
| `phase8_ui_refresh.md` | Phase 8b — Crystal theme UI refresh with ADHD-first components (dark/light mode, energy selector, flow indicator) |
| `dashboard_crystal_dark_redesign.md` | **Complete** — Dashboard redesign to match Design7 Crystal Dark layout (horizontal nav, metrics row, 7/5 grid) |
| `dashboard_landing_page_redesign.md` | **Active** — Simplified no-scroll landing page with chat focus, expandable metrics, compact sidebar widgets, skill categorization |
| `task_orchestration.md` | Task execution patterns — sequential, parallel, fan-out, fan-in, pipeline |
| `sdk_alignment_review.md` | SDK integration analysis and implementation roadmap (Phase 2 complete) |
| `prd_addulting_ai_v1.md` | **Archived** — Original PRD before ADHD pivot |
| `multimodal_messaging.md` | **Design** — Multi-modal messaging across channels (images, audio, video, code, documents) |
| `phase15_multimodal_implementation.md` | **Implementation Plan** — Detailed task breakdown for Phases 15a-15d (18-23 days) |

---

## Context Documents

| Document | Description |
|----------|-------------|
| `context/adhd_design_principles.md` | **Core** — ADHD-specific design philosophy and anti-patterns |
| `context/openclaw_research.md` | Competitive analysis of OpenClaw |
| `context/gap_analysis.md` | Feature gap analysis and roadmap justification |

---

## Phase Goals (Implementation Roadmap)

| Phase | Focus | Status |
|-------|-------|--------|
| Phase 0 | Foundation (Security + Memory) | ✅ Complete |
| Phase 1 | Channels (Multi-platform messaging) | ✅ Complete |
| Phase 2 | External Working Memory (Context capture) | ✅ Complete |
| Phase 3 | ADHD Communication Mode (RSD-safe) | ✅ Complete |
| Phase 4 | Smart Notifications (Flow protection, transition time) | ✅ Complete |
| Phase 5 | Task Engine (Decomposition, friction-solving) | ✅ Complete |
| Phase 6 | Learning (Energy patterns, personalization) | ✅ Complete |
| Phase 7 | Web Dashboard (Monitoring + configuration) | ✅ Complete |
| Phase 8 | Guided Installation (Setup wizard) | ✅ Complete |
| Phase 9 | CI/CD & Testing (GitHub Actions, pytest, Vitest) | ✅ Complete |
| Phase 10a | Mobile Push: Web Push + PWA | ✅ Complete |
| Phase 10b | Mobile Push: Expo Mobile Wrapper (iOS) | ✅ Complete |
| Phase 10c | Mobile Push: Native Enhancements (widgets, watch, shortcuts) | ✅ Complete |
| Phase 11a | Voice Interface: Browser Voice (Web Speech API) | 📋 Planned |
| Phase 11b | Voice Interface: Whisper Integration (API + local) | 📋 Planned |
| Phase 11c | Voice Interface: Advanced (wake word, TTS, mobile) | 📋 Planned |
| Phase 12a | Office Integration: Foundation (OAuth, read-only) | ✅ Complete |
| Phase 12b | Office Integration: Collaborative (drafts, scheduling) | ✅ Complete |
| Phase 12c | Office Integration: Managed Proxy (send with undo) | ✅ Complete |
| Phase 12d | Office Integration: Autonomous (policy-based) | ✅ Complete |
| Phase 13 | Collaborative Features (Accountability partners) | 📋 Planned |
| Phase 14 | Analytics & Insights (Patterns, reports) | 📋 Planned |
| Phase 15a | Multi-Modal: Core (images, documents, code) | ✅ Complete |
| Phase 15b | Multi-Modal: Audio/Video (transcription, TTS) | ✅ Complete |
| Phase 15c | Multi-Modal: Platform Rendering (embeds, Block Kit) | 📋 Planned |
| Phase 15d | Multi-Modal: Advanced (location, contacts, interactive) | 📋 Planned |

---

## SDK Alignment Phases

Cross-cutting improvements to better leverage Claude Agent SDK capabilities.

| Phase | Focus | Status |
|-------|-------|--------|
| SDK Phase 1 | Quick Wins (AskUserQuestion, sandbox, session resume, Stop hook) | ✅ Complete |
| SDK Phase 2 | Core Integration (subagents, security hooks, ClaudeSDKClient) | ✅ Complete |
| SDK Phase 3 | Enhanced Features (skills, commands, streaming input) | 📋 Planned |
| SDK Phase 4 | Optimization (model tuning, hook performance, skill refinement) | 📋 Planned |

**Reference:** `sdk_alignment_review.md` — Full analysis of SDK integration opportunities

---

*Update this manifest when adding new goals.*
