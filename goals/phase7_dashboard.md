# Goal: Phase 7 Web Dashboard

## Objective

Build a web-based management interface for DexAI that provides real-time monitoring, configuration management, and debugging tools — all with a dark, modern aesthetic inspired by Modal.com.

## Rationale

ADHD users benefit from **visual feedback**. A dashboard provides:
- Immediate confirmation that Dex is working (reduces anxiety)
- Quick access to configuration without editing YAML files
- Transparency into what Dex is doing and has done
- A central place to manage all channels and settings

The dashboard should feel **calm and focused** — not overwhelming. Less is more.

## Dependencies

- Phase 1 (Channels) — Complete
- Phase 4 (Notifications) — Recommended (for notification settings UI)
- Existing security layer (auth, sessions, permissions)

---

## Design System

### Philosophy

> **Dark, calm, professional.** Like a mission control center that doesn't stress you out.

Inspired by Modal.com's aesthetic: dark backgrounds, blue accents, subtle animations, clean typography.

### Color Palette

```css
/* Core Colors */
--bg-primary:       #0a0a0f;   /* Near black - main background */
--bg-surface:       #12121a;   /* Dark surface - cards, panels */
--bg-elevated:      #1a1a2e;   /* Elevated surface - hover states */
--bg-input:         #0f0f16;   /* Input fields */

/* Accent Colors */
--accent-primary:   #3b82f6;   /* Blue-500 - primary actions */
--accent-glow:      #60a5fa;   /* Blue-400 - glows, highlights */
--accent-secondary: #06b6d4;   /* Cyan-500 - secondary accent */

/* Status Colors */
--status-success:   #10b981;   /* Emerald-500 */
--status-warning:   #f59e0b;   /* Amber-500 */
--status-error:     #ef4444;   /* Red-500 */
--status-info:      #3b82f6;   /* Blue-500 */

/* Text Colors */
--text-primary:     #f8fafc;   /* Slate-50 - headings */
--text-secondary:   #94a3b8;   /* Slate-400 - body text */
--text-muted:       #64748b;   /* Slate-500 - captions */
--text-disabled:    #475569;   /* Slate-600 */

/* Border Colors */
--border-default:   #1e293b;   /* Slate-800 */
--border-focus:     #3b82f6;   /* Blue-500 */
```

### Typography

| Usage | Font | Size | Weight |
|-------|------|------|--------|
| Page Title | Inter/Geist | 24px | 600 |
| Section Header | Inter/Geist | 18px | 600 |
| Card Title | Inter/Geist | 16px | 500 |
| Body | Inter | 14px | 400 |
| Caption | Inter | 12px | 400 |
| Code | JetBrains Mono | 13px | 400 |

### Component Patterns

**Cards:**
- Background: `--bg-surface`
- Border: 1px `--border-default`
- Border-radius: 12px
- Shadow: `0 4px 6px -1px rgba(0, 0, 0, 0.3)`
- Hover: subtle blue glow

**Buttons:**
- Primary: `--accent-primary` bg, white text
- Secondary: transparent bg, `--accent-primary` border
- Ghost: transparent, text only
- Border-radius: 8px
- Transitions: 200ms ease

**Inputs:**
- Background: `--bg-input`
- Border: 1px `--border-default`
- Focus: `--border-focus` with glow
- Border-radius: 8px

**Animations:**
- Transitions: 200ms ease
- Hover effects: subtle scale (1.02) or glow
- Loading: pulse or skeleton
- Avoid: jarring movements, rapid flashing

---

## Dex Avatar

### Concept

A visual representation of Dex's current state — the "face" of the assistant. Always visible, providing at-a-glance status.

### Visual Design

```
┌────────────────────────────────────────┐
│                                        │
│           ╭─────────────╮              │
│          ╱               ╲             │
│         │    ◉     ◉    │  ← Eyes      │
│         │       ‿       │  ← Expression│
│          ╲_____________╱               │
│               │││││                    │
│          Particle ring / Glow          │
│                                        │
└────────────────────────────────────────┘
```

- Circular avatar with soft edges
- Particle system around edge for activity
- Glow color indicates state
- Subtle breathing animation when idle

### Avatar States

| State | Visual | Glow Color | Animation | Description |
|-------|--------|------------|-----------|-------------|
| **Idle** | Soft expression | Blue (dim) | Slow pulse, gentle breath | Waiting for input |
| **Listening** | Alert expression | Blue (medium) | Ear/sound wave icon | Processing user message |
| **Thinking** | Concentrated | Cyan | Rotating particles | LLM inference in progress |
| **Working** | Determined | Blue (bright) | Active particle motion | Executing task/tool |
| **Success** | Happy expression | Green flash | Checkmark overlay, brief | Task completed successfully |
| **Error** | Concerned | Red pulse | Warning icon overlay | Something went wrong |
| **Sleeping** | Closed eyes | Blue (very dim) | Very slow breath | Outside active hours |
| **Hyperfocus** | Shield icon | Purple | Calm shield animation | Protecting user flow |
| **Waiting** | Patient expression | Amber | Hourglass | Waiting for external response |

### Implementation Notes

```typescript
// Avatar component props
interface DexAvatarProps {
  state: AvatarState;
  size: 'sm' | 'md' | 'lg' | 'xl';
  showLabel?: boolean;
  currentTask?: string;
}

type AvatarState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'working'
  | 'success'
  | 'error'
  | 'sleeping'
  | 'hyperfocus'
  | 'waiting';
```

---

## Dashboard Pages

### 1. Home / Overview

**Purpose:** At-a-glance status and quick actions.

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  DexAI                                    [Settings] [User] │
├───────────┬─────────────────────────────────────────────────┤
│           │                                                 │
│  [Nav]    │     ┌───────────────────────────────┐          │
│           │     │                               │          │
│  Home ●   │     │      DEX AVATAR (large)       │          │
│  Tasks    │     │      "Idle - Ready to help"   │          │
│  Activity │     │                               │          │
│  Metrics  │     └───────────────────────────────┘          │
│  Audit    │                                                 │
│  Settings │     ┌─────────┐ ┌─────────┐ ┌─────────┐       │
│  Debug    │     │ Tasks   │ │Messages │ │ Cost    │       │
│           │     │ Today:12│ │ Today:47│ │ $0.23   │       │
│           │     └─────────┘ └─────────┘ └─────────┘       │
│           │                                                 │
│           │     Recent Activity                            │
│           │     ├─ 14:32  Responded to Telegram message    │
│           │     ├─ 14:28  Completed task: "Send reminder"  │
│           │     └─ 14:15  Context snapshot saved           │
│           │                                                 │
└───────────┴─────────────────────────────────────────────────┘
```

**Components:**
- Large Dex avatar with current state
- Quick stat cards (tasks, messages, cost)
- Recent activity feed (last 5-10 items)
- Quick action buttons (disabled for v1: "New Task", "Quick Note")

### 2. Tasks

**Purpose:** Timeline view of all task executions.

**Features:**
- Timeline/list view toggle
- Filter by: status (running, completed, failed), channel, date range
- Task detail modal showing:
  - Full request/response
  - Duration
  - Tools used
  - Cost
  - Logs
- Manual task trigger (future)

**Task Card:**
```
┌──────────────────────────────────────────────────────┐
│ ● Completed                           14:32 - 14:35  │
│ "Schedule dentist appointment for next week"         │
│                                                      │
│ Channel: Telegram    Duration: 3m 12s    Cost: $0.04 │
│                                           [Details →]│
└──────────────────────────────────────────────────────┘
```

### 3. Activity

**Purpose:** Real-time event stream of all Dex actions.

**Features:**
- Live WebSocket updates
- Category filters: messages, tasks, system, errors
- Search by keyword
- Export to JSON/CSV
- Click to expand full event details

**Activity Item:**
```
14:32:15  [MESSAGE]  Received message from @user on Telegram
14:32:16  [SYSTEM]   Input sanitization passed
14:32:17  [LLM]      Claude API request sent (1,240 tokens)
14:32:19  [LLM]      Response received (342 tokens)
14:32:20  [MESSAGE]  Sent response to Telegram
```

### 4. Metrics

**Purpose:** Usage statistics and cost tracking.

**Metrics to Display:**

| Category | Metrics |
|----------|---------|
| **Usage** | Messages/day, Tasks/day, Active channels |
| **Cost** | Daily/weekly/monthly spend, Cost by model, Cost by channel |
| **Performance** | Avg response time, LLM latency, Tool execution time |
| **Quality** | Task completion rate, Error rate, User corrections |

**Charts:**
- Line chart: Daily cost over time
- Bar chart: Messages by channel
- Donut chart: Cost breakdown by category
- Sparklines in stat cards

### 5. Audit

**Purpose:** Security and compliance event viewer.

**Features:**
- Filterable by: event type, user, status, date range
- Full event detail view
- Export for compliance
- Highlight security events (auth failures, permission denials)

**Audit Event Types:**
- Authentication (login, logout, session refresh)
- Authorization (permission checks, denials)
- Data access (memory reads, secret access)
- Configuration changes
- System events

### 6. Settings

**Purpose:** Manage all DexAI configuration through UI.

**Settings Sections:**

| Section | Settings |
|---------|----------|
| **General** | Display name, timezone, language |
| **Channels** | Connected channels, add/remove, per-channel settings |
| **Notifications** | Active hours, notification tiers, hyperfocus settings |
| **Privacy** | Data retention, what to remember, what to forget |
| **Security** | Sessions, API keys (masked), 2FA |
| **Advanced** | Model selection, cost limits, feature flags |

**Design Pattern:**
- Grouped in collapsible sections
- Changes auto-save with toast confirmation
- Reset to defaults option per section

### 7. Debug (Admin Only)

**Purpose:** Troubleshooting and development tools.

**Features:**
- Live log viewer (tail -f style)
- Database browser (read-only)
- Memory inspector (view/search persistent memory)
- Health checks (all services status)
- Performance profiler
- Raw config viewer

**Access:** Requires `admin` or `owner` role.

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Framework** | Next.js 14 (App Router) | Server components, fast, great DX |
| **Styling** | Tailwind CSS | Rapid development, design system support |
| **Components** | shadcn/ui | Accessible, customizable, fits dark theme |
| **Charts** | Recharts | Lightweight, React-native |
| **Icons** | Lucide | Consistent, comprehensive, MIT license |
| **State** | Zustand | Simple, performant, minimal boilerplate |
| **Forms** | React Hook Form + Zod | Validation, type safety |
| **API Client** | tRPC or fetch | Type-safe API calls |
| **Real-time** | Socket.IO | WebSocket with fallback |
| **Auth** | Existing session system | Integrate with `tools/security/session.py` |

### Directory Structure

```
tools/dashboard/
├── frontend/                    # Next.js app
│   ├── app/
│   │   ├── layout.tsx          # Root layout with nav
│   │   ├── page.tsx            # Home/Overview
│   │   ├── tasks/
│   │   ├── activity/
│   │   ├── metrics/
│   │   ├── audit/
│   │   ├── settings/
│   │   └── debug/
│   ├── components/
│   │   ├── ui/                 # shadcn components
│   │   ├── dex-avatar.tsx
│   │   ├── stat-card.tsx
│   │   ├── activity-feed.tsx
│   │   ├── task-card.tsx
│   │   └── ...
│   ├── lib/
│   │   ├── api.ts              # API client
│   │   ├── socket.ts           # WebSocket client
│   │   └── utils.ts
│   └── styles/
│       └── globals.css         # Tailwind + custom vars
│
├── backend/                     # FastAPI endpoints
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── routes/
│   │   ├── tasks.py
│   │   ├── activity.py
│   │   ├── metrics.py
│   │   ├── audit.py
│   │   └── settings.py
│   ├── websocket.py            # Real-time events
│   └── models.py               # Pydantic models
│
└── shared/
    └── types.ts                # Shared TypeScript types
```

---

## Database Schema Additions

### Dashboard Events Table

```sql
CREATE TABLE dashboard_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,           -- 'message', 'task', 'system', 'error'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    channel TEXT,
    user_id TEXT,
    summary TEXT NOT NULL,              -- Short description
    details TEXT,                       -- JSON blob with full event data
    severity TEXT DEFAULT 'info'        -- 'info', 'warning', 'error'
);

CREATE INDEX idx_dashboard_events_timestamp ON dashboard_events(timestamp DESC);
CREATE INDEX idx_dashboard_events_type ON dashboard_events(event_type);
```

### Dashboard Metrics Table

```sql
CREATE TABLE dashboard_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    labels TEXT                         -- JSON blob for dimensions
);

CREATE INDEX idx_dashboard_metrics_name_time ON dashboard_metrics(metric_name, timestamp DESC);
```

### User Preferences Table (Dashboard-specific)

```sql
CREATE TABLE dashboard_preferences (
    user_id TEXT PRIMARY KEY,
    theme TEXT DEFAULT 'dark',
    sidebar_collapsed INTEGER DEFAULT 0,
    default_page TEXT DEFAULT 'home',
    activity_filters TEXT,              -- JSON blob
    metrics_timeframe TEXT DEFAULT '7d',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Endpoints

### REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Current Dex state (for avatar) |
| GET | `/api/tasks` | List tasks with filters |
| GET | `/api/tasks/:id` | Task detail |
| GET | `/api/activity` | Activity feed with pagination |
| GET | `/api/metrics/summary` | Quick stats (today's counts) |
| GET | `/api/metrics/timeseries` | Time-series data for charts |
| GET | `/api/audit` | Audit log with filters |
| GET | `/api/settings` | Current settings |
| PATCH | `/api/settings` | Update settings |
| GET | `/api/health` | Health check (all services) |

### WebSocket Events

| Event | Direction | Payload |
|-------|-----------|---------|
| `dex:state` | Server → Client | `{ state: AvatarState, task?: string }` |
| `activity:new` | Server → Client | `{ event: ActivityEvent }` |
| `task:update` | Server → Client | `{ task: Task }` |
| `metrics:update` | Server → Client | `{ metrics: MetricsSummary }` |

---

## Implementation Order

1. **Backend API** — FastAPI routes for data endpoints
2. **WebSocket Server** — Real-time event streaming
3. **Frontend Shell** — Layout, navigation, auth integration
4. **Dex Avatar** — Core visual component
5. **Home Page** — Overview with stats and activity
6. **Tasks Page** — Task list and detail views
7. **Activity Page** — Real-time event stream
8. **Metrics Page** — Charts and analytics
9. **Settings Page** — Configuration UI
10. **Audit Page** — Security log viewer
11. **Debug Page** — Admin tools (stretch)

---

## Verification Checklist

### Backend
- [ ] `/api/status` returns current Dex state
- [ ] `/api/tasks` returns paginated task list
- [ ] `/api/activity` returns activity feed
- [ ] `/api/metrics/summary` returns today's stats
- [ ] `/api/settings` GET/PATCH works correctly
- [ ] WebSocket connects and streams events
- [ ] Authentication integrates with existing sessions

### Frontend
- [ ] Dark theme renders correctly
- [ ] Dex avatar displays all states
- [ ] Navigation works on all pages
- [ ] Home page shows stats and activity
- [ ] Tasks page filters and displays tasks
- [ ] Activity page shows real-time updates
- [ ] Metrics page renders charts
- [ ] Settings page saves changes
- [ ] Responsive on mobile (stretch)

### Integration
- [ ] WebSocket reconnects on disconnect
- [ ] Auth redirects to login when session expired
- [ ] RBAC restricts Debug page to admins
- [ ] Activity feed updates in real-time
- [ ] Settings changes reflect immediately

---

## Configuration

### New Args File: `args/dashboard.yaml`

```yaml
dashboard:
  enabled: true
  port: 3000
  api_port: 8080

  # Feature flags
  features:
    debug_page: false       # Enable debug tools
    metrics_export: false   # Enable metrics export
    audit_export: true      # Enable audit log export

  # UI preferences (defaults)
  defaults:
    theme: dark
    sidebar_collapsed: false
    activity_limit: 100
    metrics_timeframe: 7d

  # Security
  security:
    require_auth: true
    session_cookie_name: dexai_session
    allowed_origins:
      - http://localhost:3000
```

---

## Future Enhancements (Out of Scope for v1)

- [ ] Mobile responsive design
- [ ] Light theme option
- [ ] Custom dashboard layouts
- [ ] Webhook integrations
- [ ] Plugin system for custom widgets
- [ ] Multi-user support (team dashboards)
- [ ] Notification center in dashboard
- [ ] Voice control integration

---

## References

- [Modal.com](https://modal.com) — Design inspiration
- [shadcn/ui](https://ui.shadcn.com) — Component library
- [Recharts](https://recharts.org) — Charting library
- `tools/security/session.py` — Auth integration
- `tools/channels/gateway.py` — WebSocket patterns

---

*This phase brings visual feedback to DexAI — helping ADHD users see that their assistant is working, reducing anxiety about "did it get my message?"*
