# Dashboard Crystal Dark Redesign

> **Goal**: Implement the Design7 "Crystal Dark" layout for the DexAI dashboard, matching the design exactly with minor customizations.

**Status**: Complete
**Priority**: High
**Inspiration**: `~/work/dexai-design/src/designs/Design7.tsx`

---

## Executive Summary

Redesign the DexAI dashboard to match the Crystal Dark aesthetic from Design7, featuring:
- Horizontal navigation header (replacing vertical sidebar)
- Full-width 12-column grid layout
- Crystal glass panels on true black background
- Metrics dashboard with real-time data
- Integrated ADHD features (subtle placement)

---

## Design Decisions (User-Approved)

| Decision | Choice | Notes |
|----------|--------|-------|
| Active Skills | Claude skills from `.claude/` | Real skills, not mock data |
| WhatsApp Channel | Show as "Coming Soon" | Visually indicate unavailable |
| Navigation | Hybrid approach | Main tabs + settings/debug as icons |
| ADHD Features | Integrate subtly | Not standalone cards |
| User Avatar | Pull from settings | Generate initials from user_name |
| CurrentStep | Top of chat panel | Above chat messages |
| Skills API | Create real endpoint | Backend to scan .claude/skills |

---

## Visual Reference

### Design7 Layout Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│ HEADER                                                               │
│ [Logo] DexAI          [Overview] [Memory] [Skills] [Channels]       │
│ Control Center                               [●Online] [⚙] [JD]     │
├─────────────────────────────────────────────────────────────────────┤
│ METRICS ROW (4 columns)                                              │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│ │ Uptime   │ │ Response │ │ Tasks    │ │ Providers│                │
│ │ 99.9%    │ │ 45ms     │ │ 2,847    │ │ 3/5      │                │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘                │
├─────────────────────────────────────────────────────────────────────┤
│ MAIN CONTENT (7/5 grid split)                                        │
│ ┌───────────────────────────────┐ ┌─────────────────────┐          │
│ │ CHAT PANEL (col-span-7)       │ │ RIGHT COLUMN        │          │
│ │                               │ │ (col-span-5)        │          │
│ │ 🤖 Good morning. I've...     │ │ ┌─────────────────┐ │          │
│ │                               │ │ │ Current Focus   │ │          │
│ │ 👤 Show me the calendar...   │ │ │ [ADHD Task]     │ │          │
│ │                               │ │ │ [Done][Skip][?] │ │          │
│ │ 🤖 Resolved: 1) Moved...     │ │ └─────────────────┘ │          │
│ │                               │ │                     │          │
│ │ ─────────────────────────     │ │ ┌─────────────────┐ │          │
│ │ [Type a message...] [📎][🎤]│ │ │ Active Skills   │ │          │
│ │                         [➤] │ │ │ ● Email Manager │ │          │
│ └───────────────────────────────┘ │ │ ○ Web Research  │ │          │
│                                   │ └─────────────────┘ │          │
│                                   │                     │          │
│                                   │ ┌─────────────────┐ │          │
│                                   │ │ Memory Providers│ │          │
│                                   │ │ ★ Native  2.4GB │ │          │
│                                   │ └─────────────────┘ │          │
│                                   └─────────────────────┘          │
├─────────────────────────────────────────────────────────────────────┤
│ BOTTOM ROW (2 columns)                                               │
│ ┌────────────────────────────┐ ┌────────────────────────────┐      │
│ │ OFFICE INTEGRATION         │ │ COMMUNICATION CHANNELS     │      │
│ │ ┌──────────┐ ┌──────────┐ │ │ [💬] [✈] [📱] [#] [💬]    │      │
│ │ │Microsoft │ │Google    │ │ │ Chat Tele What Disc Slack  │      │
│ │ │365   [●] │ │Work  [●] │ │ │  ●    ●   ○    ○    ○      │      │
│ │ └──────────┘ └──────────┘ │ │ (WhatsApp = Coming Soon)    │      │
│ └────────────────────────────┘ └────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### Color Palette (Crystal Dark)

```css
/* Background */
--bg-primary: #000000;                    /* True black */
--bg-surface: rgba(255, 255, 255, 0.02);  /* Glass panels */
--bg-elevated: rgba(255, 255, 255, 0.04); /* Elevated elements */
--bg-hover: rgba(255, 255, 255, 0.06);    /* Hover states */

/* Borders */
--border-default: rgba(255, 255, 255, 0.06);
--border-subtle: rgba(255, 255, 255, 0.04);

/* Text (opacity hierarchy) */
--text-primary: rgba(255, 255, 255, 0.9);
--text-secondary: rgba(255, 255, 255, 0.6);
--text-muted: rgba(255, 255, 255, 0.4);
--text-disabled: rgba(255, 255, 255, 0.2);

/* Accent */
--status-online: #10b981;  /* Emerald green */
```

### Typography

```css
/* Headers */
font-light tracking-wide          /* DexAI title */
text-xs tracking-widest uppercase /* Subtitles like "Control Center" */

/* Metrics */
text-4xl font-extralight          /* Large metric values */
text-sm text-white/40             /* Metric labels */

/* Body */
text-[15px] leading-relaxed       /* Chat messages */
text-sm font-medium               /* Section titles */
```

---

## Implementation Tasks

### Phase 1: Backend API (Skills Endpoint)

**File**: `tools/dashboard/backend/routers/skills.py`

Create endpoint to scan and return Claude skills:

```python
@router.get("/skills")
async def get_skills():
    """List all Claude skills from .claude/ directory."""
    skills = []
    claude_dir = Path.home() / ".claude"
    skills_dir = claude_dir / "skills"

    if skills_dir.exists():
        for skill_file in skills_dir.glob("*.md"):
            # Parse skill metadata from markdown
            skills.append({
                "name": skill_file.stem,
                "display_name": format_skill_name(skill_file.stem),
                "status": "idle",  # or check if actively running
                "file_path": str(skill_file)
            })

    return {"skills": skills, "total": len(skills)}
```

**Register in**: `tools/dashboard/backend/main.py`

### Phase 2: Frontend Components

#### 2.1 Crystal Components

**File**: `components/crystal-card.tsx`
```tsx
export function CrystalCard({ children, className }: Props) {
  return (
    <div className={cn(
      "bg-white/[0.02] backdrop-blur-xl",
      "border border-white/[0.06] rounded-2xl",
      className
    )}>
      {children}
    </div>
  );
}
```

**File**: `components/crystal-message.tsx`
```tsx
export function CrystalMessage({ message, isAi, time }: Props) {
  // Match Design7 chat bubble styling
}
```

#### 2.2 Metrics Card

**File**: `components/metrics-card.tsx`
```tsx
export function MetricsCard({ icon, label, value, sub }: Props) {
  return (
    <CrystalCard className="p-6">
      <div className="flex items-start justify-between mb-4">
        <Icon className="w-5 h-5 text-white/30" />
        <span className="text-xs text-white/20 uppercase tracking-wider">{sub}</span>
      </div>
      <div className="text-4xl font-extralight mb-1">{value}</div>
      <div className="text-sm text-white/40">{label}</div>
    </CrystalCard>
  );
}
```

#### 2.3 Skills Panel

**File**: `components/skills-panel.tsx`
```tsx
export function SkillsPanel() {
  // Fetch from /api/skills
  // Display 2x2 grid with status indicators
}
```

#### 2.4 Channels Panel

**File**: `components/channels-panel.tsx`
```tsx
const channels = [
  { icon: MessageSquare, name: 'Chat', active: true },
  { icon: Send, name: 'Telegram', active: true },
  { icon: Phone, name: 'WhatsApp', active: false, comingSoon: true },
  { icon: Hash, name: 'Discord', active: false },
  { icon: MessageCircle, name: 'Slack', active: false },
];
```

#### 2.5 Office Panel

**File**: `components/office-panel.tsx`
```tsx
// Fetch from /api/oauth/status
// Display Microsoft 365 and Google Workspace cards
```

### Phase 3: Layout Restructure

#### 3.1 New Header Component

**File**: `components/crystal-header.tsx`

```tsx
export function CrystalHeader() {
  const [activeSection, setActiveSection] = useState('overview');

  return (
    <header className="relative z-10 border-b border-white/[0.06]">
      <div className="max-w-7xl mx-auto px-8 py-5">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-5">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-white/10 to-white/5
                          backdrop-blur-xl border border-white/10 flex items-center justify-center">
              <Brain className="w-6 h-6 text-white/80" />
            </div>
            <div>
              <h1 className="text-2xl font-light tracking-wide">DexAI</h1>
              <p className="text-xs text-white/30 tracking-widest uppercase">Control Center</p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1">
            {['Overview', 'Memory', 'Skills', 'Channels'].map((tab) => (
              <Link
                key={tab}
                href={tab === 'Overview' ? '/' : `/${tab.toLowerCase()}`}
                className={cn(
                  'px-5 py-2.5 rounded-xl text-sm font-medium transition-all',
                  isActive ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
                )}
              >
                {tab}
              </Link>
            ))}
          </nav>

          {/* Right Section */}
          <div className="flex items-center gap-4">
            {/* Energy Selector (ADHD - subtle) */}
            <EnergySelector compact variant="crystal" />

            {/* Flow Badge (ADHD - subtle) */}
            <FlowBadge variant="crystal" />

            {/* Online Status */}
            <div className="flex items-center gap-3 px-4 py-2 rounded-xl
                          bg-emerald-500/5 border border-emerald-500/20">
              <div className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className="text-sm text-emerald-300/80">Online</span>
            </div>

            {/* Settings Icon */}
            <Link href="/settings">
              <button className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10
                               border border-white/5 transition-all">
                <Settings className="w-5 h-5 text-white/40" />
              </button>
            </Link>

            {/* User Avatar */}
            <UserAvatar />
          </div>
        </div>
      </div>
    </header>
  );
}
```

#### 3.2 Update Layout Content

**File**: `components/layout-content.tsx`

```tsx
export function LayoutContent({ children }: Props) {
  const pathname = usePathname();
  const isSetupPage = pathname?.startsWith('/setup');

  if (isSetupPage) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Crystal refraction background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-[500px] h-[500px]
                      bg-gradient-conic from-white/5 via-transparent to-white/5
                      rounded-full blur-3xl opacity-50" />
        <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px]
                      bg-gradient-conic from-slate-500/5 via-transparent to-slate-500/5
                      rounded-full blur-3xl opacity-50" />
      </div>

      {/* Crystal grid pattern */}
      <div className="fixed inset-0 opacity-[0.02] pointer-events-none"
        style={{
          backgroundImage: 'linear-gradient(rgba(255,255,255,.1) 1px, transparent 1px),
                           linear-gradient(90deg, rgba(255,255,255,.1) 1px, transparent 1px)',
          backgroundSize: '60px 60px'
        }}
      />

      {/* Header */}
      <CrystalHeader />

      {/* Main Content */}
      <main className="relative z-10 max-w-7xl mx-auto px-8 py-10">
        {children}
      </main>
    </div>
  );
}
```

### Phase 4: Overview Page

**File**: `app/page.tsx`

```tsx
export default function HomePage() {
  // Fetch all data
  const { metrics } = useMetrics();
  const { skills } = useSkills();
  const { providers } = useMemoryProviders();
  const { channels } = useChannels();
  const { officeStatus } = useOfficeStatus();
  const { currentStep } = useCurrentStep();

  return (
    <div className="space-y-10 animate-fade-in">
      {/* Metrics Row */}
      <section className="grid grid-cols-4 gap-6">
        <MetricsCard icon={Activity} label="System Uptime" value="99.9%" sub="Last 30 days" />
        <MetricsCard icon={Zap} label="Avg Response" value="45ms" sub="Last hour" />
        <MetricsCard icon={Cpu} label="Tasks Completed" value={metrics.tasksWeek} sub="This week" />
        <MetricsCard icon={Database} label="Active Providers"
                    value={`${providers.activeCount}/${providers.total}`} sub="Memory systems" />
      </section>

      {/* Main Content */}
      <div className="grid grid-cols-12 gap-8">
        {/* Chat Panel */}
        <div className="col-span-7">
          <CrystalCard className="h-full flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-white/[0.04]">
              <div className="flex items-center gap-3">
                <MessageSquare className="w-5 h-5 text-white/40" />
                <span className="font-medium">Direct Chat</span>
              </div>
              <div className="flex items-center gap-2 text-sm text-white/30">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Active
              </div>
            </div>

            {/* Current Step (ADHD) */}
            {currentStep && (
              <CurrentStepCard step={currentStep} variant="crystal" />
            )}

            {/* Chat Messages */}
            <div className="flex-1 p-6 space-y-6 min-h-[350px]">
              <ChatHistory variant="crystal" />
            </div>

            {/* Input */}
            <ChatInput variant="crystal" />
          </CrystalCard>
        </div>

        {/* Right Column */}
        <div className="col-span-5 space-y-6">
          {/* Active Skills (MOVED ABOVE Memory) */}
          <SkillsPanel />

          {/* Memory Providers */}
          <MemoryProvidersPanel />
        </div>
      </div>

      {/* Bottom Row */}
      <section className="grid grid-cols-2 gap-6">
        <OfficePanel />
        <ChannelsPanel />
      </section>
    </div>
  );
}
```

### Phase 5: Update Other Pages

Ensure Memory, Skills, Channels pages also use the Crystal Dark styling:
- Update `app/memory/page.tsx`
- Create `app/skills/page.tsx` (dedicated skills management)
- Update `app/channels/page.tsx`

### Phase 6: API Client Updates

**File**: `lib/api.ts`

Add new endpoints:
```typescript
// Skills
async getSkills(): Promise<ApiResponse<{ skills: Skill[]; total: number }>> {
  return this.request<{ skills: Skill[]; total: number }>('/api/skills');
}

// Types
export interface Skill {
  name: string;
  display_name: string;
  status: 'running' | 'idle';
  file_path: string;
}
```

---

## Files to Create/Modify

### New Files
- `tools/dashboard/backend/routers/skills.py` - Skills API endpoint
- `tools/dashboard/frontend/components/crystal-card.tsx`
- `tools/dashboard/frontend/components/crystal-message.tsx`
- `tools/dashboard/frontend/components/crystal-header.tsx`
- `tools/dashboard/frontend/components/metrics-card.tsx`
- `tools/dashboard/frontend/components/skills-panel.tsx`
- `tools/dashboard/frontend/components/channels-panel.tsx`
- `tools/dashboard/frontend/components/office-panel.tsx`
- `tools/dashboard/frontend/components/memory-providers-panel.tsx`
- `tools/dashboard/frontend/app/skills/page.tsx`

### Modified Files
- `tools/dashboard/backend/main.py` - Register skills router
- `tools/dashboard/frontend/app/globals.css` - Add crystal utilities
- `tools/dashboard/frontend/components/layout-content.tsx` - New layout
- `tools/dashboard/frontend/app/page.tsx` - Complete rewrite
- `tools/dashboard/frontend/lib/api.ts` - Add skills endpoint
- `tools/dashboard/frontend/components/current-step-card.tsx` - Crystal variant
- `tools/dashboard/frontend/components/energy-selector.tsx` - Crystal variant
- `tools/dashboard/frontend/components/flow-indicator.tsx` - Crystal variant
- `tools/dashboard/frontend/components/quick-chat.tsx` - Crystal variant

---

## Verification Checklist

- [x] Header displays correctly with horizontal navigation
- [x] Metrics row shows real data from APIs
- [x] Chat panel includes CurrentStep at top
- [x] Skills panel fetches and displays Claude skills
- [x] Memory providers panel shows provider health
- [x] Office panel shows Google/Microsoft connection status
- [x] Channels panel shows all channels (WhatsApp as "Coming Soon")
- [x] Energy selector works in header
- [x] Flow indicator shows in header
- [x] User initials display from settings
- [x] All pages use Crystal Dark styling
- [x] Responsive design works on smaller screens (mobile menu, breakpoints)
- [x] Crystal Dark is the default theme (light mode via CSS class toggle)

---

## Dependencies

No new npm packages required. Uses existing:
- `lucide-react` for icons
- `tailwindcss` for styling
- Existing API infrastructure

---

## Notes

- The sidebar is being **removed** in favor of horizontal tabs
- Settings and Debug pages accessible via header icons
- ADHD features are **integrated** not standalone
- WhatsApp shows as "Coming Soon" until implemented
- User avatar pulls initials from `user_name` in setup preferences

---

*Created: 2026-02-08*
*Last Updated: 2026-02-08*
