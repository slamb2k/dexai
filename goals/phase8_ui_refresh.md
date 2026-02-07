# Phase 8: DexAI Web Interface Redesign

**Status**: Completed
**PR**: #50 (merged 2026-02-07)

---

## Core Design Philosophy: ADHD-First UX

This redesign treats ADHD/neurodivergent needs as **the primary design constraint**, not an afterthought. Every UI decision flows from these principles:

### Fundamental ADHD Design Principles

| Principle | Implementation |
|-----------|----------------|
| **One-Thing Mode** | Show ONE current action prominently, not overwhelming lists |
| **Reduce Decision Paralysis** | Pre-select defaults, limit visible choices, progressive disclosure |
| **RSD-Safe Language** | No guilt ("you forgot"), use forward-facing language ("Sarah's waiting on docs") |
| **Flow State Protection** | Visible indicator when in hyperfocus, suppressed notification count |
| **Visual Feedback = Anxiety Reduction** | Avatar states provide constant "Dex is okay" feedback |
| **Energy Matching** | Surface tasks appropriate to current energy level |
| **Friction Pre-Solving** | Surface blockers BEFORE user hits them |
| **Brevity by Default** | Short summaries, expand on demand |
| **Context Preservation** | "You were working on X" resumption prompts |

---

## Design System: Crystal Theme

### Dark Mode (System Default: Dark)
Based on "Crystal Dark" aesthetic:
- **Background**: True black (`#000000`) with subtle crystal grid pattern
- **Surfaces**: Glass panels with `bg-white/[0.02]` to `bg-white/[0.06]`
- **Borders**: Ultra-subtle `border-white/[0.06]`
- **Text**: White with opacity hierarchy (80%, 60%, 40%, 20%)
- **Accents**: Emerald for success/active, platinum/white for primary
- **Effects**: Backdrop blur, subtle glow on hover, conic gradient backgrounds

### Light Mode (New)
Inverse crystal aesthetic:
- **Background**: Soft white (`#fafafa`) with subtle gray grid
- **Surfaces**: Glass panels with `bg-black/[0.02]` to `bg-black/[0.06]`
- **Borders**: Ultra-subtle `border-black/[0.06]`
- **Text**: Black with opacity hierarchy
- **Accents**: Emerald for success, slate for primary
- **Effects**: Same blur/glow adapted for light

### System Preference Detection
```typescript
// In layout.tsx or theme provider
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
// Apply 'dark' class to html element, use Tailwind dark: variants
```

---

## Information Architecture: What Matters When

### First Load (Dashboard Home)
**Purpose**: Instant orientation, zero cognitive load, one clear action

| Element | Priority | ADHD Rationale |
|---------|----------|----------------|
| **Dex Avatar + State** | P0 | Visual "everything is okay" signal, reduces anxiety |
| **Current Step Card** | P0 | ONE thing to do next, not a list |
| **Flow State Indicator** | P0 | Am I in hyperfocus? Should I protect it? |
| **Context Resume Prompt** | P0 | "You were working on X" if returning |
| **Commitment Count** | P1 | Small badge, not guilt-inducing, just awareness |
| **Energy Quick-Set** | P1 | 3 buttons: Low/Medium/High - affects task suggestions |
| **Quick Stats** | P2 | Minimal: tasks done today, time saved |

**NOT on first load**: Task lists, full activity feed, settings, analytics

### Deeper Activities (Progressive Disclosure)

| Page | Access | Purpose |
|------|--------|---------|
| `/tasks` | Sidebar | Full task management with decomposition |
| `/memory` | Sidebar | Search memories, view commitments |
| `/channels` | Sidebar | Multi-platform inbox |
| `/office` | Sidebar | Email/calendar integration |
| `/activity` | Sidebar | Full event log |
| `/settings` | Top bar | Configuration |

---

## Component Specifications

### 1. Dashboard Home (`/`)

```
┌─────────────────────────────────────────────────────────────┐
│ [Logo]  DexAI                    [🌙] [🔔 3] [Settings] [JD]│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              DEX AVATAR (Large, Animated)            │   │
│  │                   [Current State]                    │   │
│  │                  "Ready to help"                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  🎯 CURRENT STEP                                     │   │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │   │
│  │  "Reply to Sarah's email about the Q4 report"       │   │
│  │                                                      │   │
│  │  [✓ Done]  [Skip for now]  [I'm stuck]              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Energy: ⚡⚡⚡ │  │ Flow: 🟢 ON  │  │ Waiting: 2   │      │
│  │ [Low][Med][Hi]│  │ 47min deep   │  │ (view →)     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  💬 Quick Chat                                       │   │
│  │  [Type a message to Dex...]            [📎][🎤][→]  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key ADHD Features**:
- Avatar is large and centered (calming, immediate feedback)
- ONE current step, not a task list
- "I'm stuck" button triggers friction-solving
- Energy selector is 3 simple buttons, not a slider
- Flow state shows time in focus (positive reinforcement)
- "Waiting" count uses neutral language, not "overdue"

### 2. Sidebar (Collapsible)

```
┌────────────────────┐
│ ◀ Collapse         │
├────────────────────┤
│ 🏠 Home            │
│ ✅ Tasks           │
│ 🧠 Memory          │
│ 💬 Channels        │
│ 📧 Office          │
│ 📊 Activity        │
├────────────────────┤
│ ⚙️ Settings        │
│ 🔍 Debug (admin)   │
└────────────────────┘
```

### 3. Tasks Page (`/tasks`)

**Default View**: Current step + Next 2 steps only
**Expanded View**: Full decomposed task tree (on demand)

```
┌─────────────────────────────────────────────────────────────┐
│ TASKS                                    [+ New Task]       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🎯 NOW                                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Reply to Sarah's email about Q4 report              │   │
│  │ ⚡ Low energy ok  •  📧 Office  •  ~5 min           │   │
│  │ [✓ Done]  [Skip]  [Stuck]  [Decompose]              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ⏭️ UP NEXT (2)                          [Show all →]      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ • Review budget spreadsheet (⚡⚡ Medium)            │   │
│  │ • Call Mike about project timeline (⚡⚡⚡ High)     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ⚠️ FRICTION DETECTED                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ "Call Mike" needs: Mike's phone number              │   │
│  │ [Find in contacts]  [Ask Dex to find]               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4. Memory Page (`/memory`)

```
┌─────────────────────────────────────────────────────────────┐
│ MEMORY                                                      │
├─────────────────────────────────────────────────────────────┤
│  [🔍 Search memories...]                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  👋 WAITING ON YOU (Forward-facing, not guilt)              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ • Sarah's waiting on Q4 docs (3 days)               │   │
│  │ • Mike expects callback (today)                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  📍 CONTEXT SNAPSHOTS                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Yesterday 4:32pm - "Budget review for Q4"           │   │
│  │ [Resume this context]                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  🧠 MEMORY PROVIDERS                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ● Native (Primary) - 2.4GB - 100% health            │   │
│  │ ● Mem0 (Active) - 1.2GB - 98% health                │   │
│  │ ○ Zep (Inactive)                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5. Theme Toggle Component

```typescript
// components/theme-toggle.tsx
'use client'
import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'

export function ThemeToggle() {
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>('system')

  useEffect(() => {
    const root = document.documentElement
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches

    if (theme === 'system') {
      root.classList.toggle('dark', systemDark)
    } else {
      root.classList.toggle('dark', theme === 'dark')
    }
  }, [theme])

  // Listen for system preference changes
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      if (theme === 'system') {
        document.documentElement.classList.toggle('dark', mq.matches)
      }
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [theme])

  return (
    <button onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}>
      {theme === 'dark' ? <Sun /> : <Moon />}
    </button>
  )
}
```

---

## Implementation Summary

### Files Created/Modified

| File | Changes |
|------|---------|
| `tools/dashboard/frontend/tailwind.config.js` | Crystal theme colors, dark mode config |
| `tools/dashboard/frontend/app/globals.css` | CSS variables for theming, Crystal effects |
| `tools/dashboard/frontend/app/layout.tsx` | ThemeProvider, system preference detection |
| `tools/dashboard/frontend/app/page.tsx` | ADHD-first dashboard redesign |
| `tools/dashboard/frontend/components/sidebar.tsx` | Updated nav items, styling |
| `tools/dashboard/frontend/components/top-bar.tsx` | Theme toggle, simplified |
| `tools/dashboard/frontend/components/dex-avatar.tsx` | Larger, more prominent |
| `tools/dashboard/frontend/app/tasks/page.tsx` | Current-step-first redesign |
| `tools/dashboard/frontend/app/memory/page.tsx` | **NEW** Memory search, commitments |
| `tools/dashboard/frontend/components/current-step-card.tsx` | **NEW** The ONE action |
| `tools/dashboard/frontend/components/energy-selector.tsx` | **NEW** 3-button selector |
| `tools/dashboard/frontend/components/flow-indicator.tsx` | **NEW** Flow state display |
| `tools/dashboard/frontend/components/theme-toggle.tsx` | **NEW** Dark/light switcher |
| `tools/dashboard/frontend/lib/theme-provider.tsx` | **NEW** Theme context + system pref |
| `tools/dashboard/frontend/components/commitment-badge.tsx` | **NEW** RSD-safe commitments |
| `tools/dashboard/frontend/components/quick-chat.tsx` | **NEW** Chat input |

---

## Verification Checklist

- [x] Visual: Crystal Dark aesthetic with glass panels
- [x] Theme: Toggle between dark/light, system preference detection
- [x] ADHD Principles:
  - [x] Dashboard shows ONE current step prominently
  - [x] No overwhelming lists on first load
  - [x] Energy selector is simple (3 buttons)
  - [x] Flow state indicator is visible
  - [x] Language is forward-facing, not guilt-inducing
- [x] Responsive: Mobile viewport support
- [x] Real-time: WebSocket updates work with new components
- [x] Navigation: All sidebar links work, pages load correctly
- [x] Build: TypeScript compiles, Next.js builds successfully
