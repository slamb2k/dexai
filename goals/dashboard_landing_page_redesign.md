# Dashboard Landing Page Redesign

> **Goal:** Create a simpler, no-scroll landing page that prioritizes immediate chat access while maintaining visual richness through expandable widgets and compact sidebar components.

---

## Design Philosophy

### Core Principles

1. **No Page Scroll** — Everything fits on a single viewport (min 900px height)
2. **Chat-Centric** — Chat panel is the primary focus with scrollable internal history
3. **Progressive Disclosure** — Metrics are collapsed by default, expandable for details
4. **Click-to-Navigate** — Sidebar widgets are compact summaries that link to detail pages
5. **Vertical Efficiency** — Every component is optimized for minimal height

### Visual Direction

Maintain the Crystal Dark aesthetic while introducing:
- **Collapsible Accordion Widgets** — shadcn `Collapsible` or custom expandable cards
- **Compact Summary Cards** — Single-line or 2-line widget previews
- **Integrated Focus Mode** — Flow indicator merged into Current Focus panel
- **Skill Categories** — Visual differentiation between built-in and user skills

---

## Layout Architecture

### Viewport Structure (No Scroll)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CRYSTAL HEADER (64px)                           │
│  [Logo]  [Nav: Home Skills Memory Channels Office...]  [Energy] [User]  │
├─────────────────────────────────────────────────────────────────────────┤
│                    EXPANDABLE METRICS ROW (~48px collapsed)             │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐         │
│  │ ▸ Uptime 99% │ ▸ Resp 45ms  │ ▸ Tasks 284  │ ▸ Providers 3│         │
│  └──────────────┴──────────────┴──────────────┴──────────────┘         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────────────────────┐  ┌─────────────────────────────┐ │
│   │                                 │  │     CURRENT FOCUS           │ │
│   │                                 │  │   + Focus Mode Toggle       │ │
│   │                                 │  │   [title, energy, time]     │ │
│   │                                 │  │   [Done] [Skip] [?]         │ │
│   │         CHAT PANEL              │  ├─────────────────────────────┤ │
│   │    (scrollable history)         │  │     ENERGY LEVEL            │ │
│   │                                 │  │   ⚡⚡⚡ High Energy          │ │
│   │                                 │  │        → Settings           │ │
│   │                                 │  ├─────────────────────────────┤ │
│   │                                 │  │     SERVICES                │ │
│   │                                 │  │   MS: ✓  Google: ✓          │ │
│   │                                 │  │        → Office page        │ │
│   │  ┌───────────────────────────┐  │  ├─────────────────────────────┤ │
│   │  │ [Message input...    📎🎤]│  │  │     SKILLS OVERVIEW         │ │
│   │  └───────────────────────────┘  │  │   Built-in: 12  User: 4     │ │
│   │                                 │  │        → Skills page        │ │
│   └─────────────────────────────────┘  └─────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Height Budget (1080px viewport)

| Section | Height | Notes |
|---------|--------|-------|
| Header | 64px | Fixed navigation |
| Metrics Row (collapsed) | 48px | Single line with expand arrow |
| Metrics Row (expanded) | ~180px | Full cards with trends |
| Content Area | ~900px | Fills remaining space |
| Padding/Gaps | 68px | 32px top + 24px gaps |

**Content Area Split:**
- Chat Panel: Full height with internal scroll
- Sidebar: 4 stacked compact widgets

---

## Component Specifications

### 1. Expandable Metrics Row

**New Component:** `ExpandableMetricsRow`

**Collapsed State (48px):**
```tsx
<div className="flex items-center gap-3 px-6 py-2.5 bg-white/[0.02] border-b border-white/[0.04]">
  <button onClick={toggle} className="flex items-center gap-2 text-white/40">
    <ChevronRight className={cn("w-4 h-4 transition-transform", expanded && "rotate-90")} />
    <span className="text-xs uppercase tracking-wider">Metrics</span>
  </button>

  {/* Inline summary pills */}
  <div className="flex items-center gap-4 ml-auto">
    <MetricPill icon={Activity} label="Uptime" value="99.9%" />
    <MetricPill icon={Zap} label="Response" value="45ms" trend="down" />
    <MetricPill icon={Cpu} label="Tasks" value="2,847" trend="up" />
    <MetricPill icon={Database} label="Providers" value="3/5" />
  </div>
</div>
```

**Expanded State (~180px):**
Uses existing `MetricsCard` components in a grid, slides down with animation.

**shadcn Implementation:**
```tsx
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible"

<Collapsible open={expanded} onOpenChange={setExpanded}>
  <CollapsibleTrigger asChild>
    <div className="...collapsed row...">
      {/* Summary pills visible when collapsed */}
    </div>
  </CollapsibleTrigger>
  <CollapsibleContent>
    <div className="grid grid-cols-4 gap-4 p-4">
      {/* Full MetricsCard components */}
    </div>
  </CollapsibleContent>
</Collapsible>
```

---

### 2. Chat Panel (Enhanced)

**Key Changes:**
- `min-h-0` and `flex-1` to allow proper flex shrinking
- Chat history uses `overflow-y-auto` for internal scrolling
- Remove any fixed height constraints

```tsx
<CrystalCard className="flex-1 flex flex-col min-h-0">
  <CrystalCardHeader icon={<MessageSquare />} title="Direct Chat" />

  {/* Scrollable chat history */}
  <div className="flex-1 overflow-y-auto min-h-0">
    <ChatHistory messages={messages} />
  </div>

  {/* Fixed input at bottom */}
  <div className="flex-shrink-0 border-t border-white/[0.04] p-4">
    <ChatInput />
  </div>
</CrystalCard>
```

---

### 3. Current Focus Panel (with Flow Mode)

**Integration:** Merge `FlowIndicator` into `CurrentStepPanel`

**New Layout:**
```tsx
<CrystalCard className="flex-shrink-0">
  <div className="flex items-center justify-between p-4 border-b border-white/[0.04]">
    <CrystalCardHeader icon={<Focus />} title="Current Focus" border={false} />

    {/* Flow Mode Toggle - replaces separate FlowIndicator */}
    <button
      onClick={toggleFlowMode}
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all",
        isInFlow
          ? "bg-purple-500/15 border border-purple-500/30 text-purple-400"
          : "bg-white/[0.04] border border-white/[0.06] text-white/40"
      )}
    >
      <Shield className="w-4 h-4" />
      <span className="text-xs font-medium">
        {isInFlow ? `Flow ${elapsedTime}` : "Focus Off"}
      </span>
    </button>
  </div>

  <CrystalCardContent>
    {step ? (
      <>
        <h3 className="text-base font-medium text-white/90">{step.title}</h3>
        <div className="flex items-center gap-2 mt-2">
          <EnergyBadge level={step.energyRequired} />
          <TimeBadge time={step.estimatedTime} />
        </div>
        <div className="flex gap-2 mt-4">
          <Button variant="success" size="sm" onClick={onComplete}>Done</Button>
          <Button variant="ghost" size="sm" onClick={onSkip}>Skip</Button>
          <Button variant="ghost" size="icon" onClick={onStuck}>
            <HelpCircle className="w-4 h-4" />
          </Button>
        </div>
      </>
    ) : (
      <EmptyState message="No active task" />
    )}
  </CrystalCardContent>
</CrystalCard>
```

---

### 4. Compact Energy Widget

**New Component:** `EnergyWidgetCompact`

**Design:** Single row, clickable to navigate to settings

```tsx
<Link href="/settings#energy">
  <div className={cn(
    "group flex items-center justify-between p-4 rounded-xl",
    "bg-white/[0.02] border border-white/[0.04]",
    "hover:bg-white/[0.04] hover:border-white/[0.08] transition-all cursor-pointer"
  )}>
    <div className="flex items-center gap-3">
      <div className="p-2 rounded-lg bg-white/[0.04]">
        <Zap className="w-4 h-4 text-white/40" />
      </div>
      <div>
        <div className="text-sm font-medium text-white/80">Energy Level</div>
        <div className="text-xs text-white/40">Affects task matching</div>
      </div>
    </div>

    <div className="flex items-center gap-2">
      <EnergyIndicator level={currentEnergy} showLabel={false} />
      <span className={cn("text-sm font-medium", energyConfig[currentEnergy].color)}>
        {energyConfig[currentEnergy].fullLabel}
      </span>
      <ChevronRight className="w-4 h-4 text-white/20 group-hover:text-white/40 transition-colors" />
    </div>
  </div>
</Link>
```

**Height:** ~64px

---

### 5. Compact Office Widget

**New Component:** `ServicesWidgetCompact`

**Design:** Two provider icons with status, click to navigate

```tsx
<Link href="/office">
  <div className={cn(
    "group flex items-center justify-between p-4 rounded-xl",
    "bg-white/[0.02] border border-white/[0.04]",
    "hover:bg-white/[0.04] hover:border-white/[0.08] transition-all cursor-pointer"
  )}>
    <div className="flex items-center gap-3">
      <div className="p-2 rounded-lg bg-white/[0.04]">
        <Building2 className="w-4 h-4 text-white/40" />
      </div>
      <div>
        <div className="text-sm font-medium text-white/80">Services</div>
        <div className="text-xs text-white/40">{connectedCount}/2 connected</div>
      </div>
    </div>

    <div className="flex items-center gap-3">
      {/* Provider status icons */}
      <div className="flex items-center gap-2">
        <ProviderIcon provider="microsoft" connected={msConnected} />
        <ProviderIcon provider="google" connected={googleConnected} />
      </div>
      <ChevronRight className="w-4 h-4 text-white/20 group-hover:text-white/40 transition-colors" />
    </div>
  </div>
</Link>
```

**Height:** ~64px

---

### 6. Skills Overview Widget (with Categories)

**New Component:** `SkillsWidgetCompact`

**Key Feature:** Categorize skills as "Built-in" or "User"

**Data Model Update:**
```typescript
interface Skill {
  name: string;
  display_name: string;
  description?: string;
  status: 'idle' | 'running';
  has_instructions: boolean;
  category: 'built-in' | 'user';  // NEW FIELD
  source_path: string;
}
```

**Category Detection Logic (Backend):**
```python
def categorize_skill(skill_path: str) -> str:
    """
    Determine if a skill is built-in or user-created.

    Built-in skills:
    - Located in ~/.claude/plugins/ (installed via plugin system)
    - Have 'anthropic' or 'claude' in the path
    - Part of the default installation

    User skills:
    - Located in ~/.claude/skills/ (user-created)
    - Custom installations
    """
    if '/plugins/' in skill_path:
        return 'built-in'
    if 'anthropic' in skill_path.lower() or 'claude' in skill_path.lower():
        return 'built-in'
    return 'user'
```

**Widget Design:**
```tsx
<Link href="/skills">
  <div className={cn(
    "group flex items-center justify-between p-4 rounded-xl",
    "bg-white/[0.02] border border-white/[0.04]",
    "hover:bg-white/[0.04] hover:border-white/[0.08] transition-all cursor-pointer"
  )}>
    <div className="flex items-center gap-3">
      <div className="p-2 rounded-lg bg-white/[0.04]">
        <Sparkles className="w-4 h-4 text-white/40" />
      </div>
      <div>
        <div className="text-sm font-medium text-white/80">Skills</div>
        <div className="text-xs text-white/40">{activeCount} active</div>
      </div>
    </div>

    <div className="flex items-center gap-3">
      {/* Category counts */}
      <div className="flex items-center gap-2">
        <CategoryBadge type="built-in" count={builtInCount} />
        <CategoryBadge type="user" count={userCount} />
      </div>
      <ChevronRight className="w-4 h-4 text-white/20 group-hover:text-white/40 transition-colors" />
    </div>
  </div>
</Link>

function CategoryBadge({ type, count }: { type: 'built-in' | 'user'; count: number }) {
  return (
    <div className={cn(
      "flex items-center gap-1.5 px-2 py-1 rounded-md text-xs",
      type === 'built-in'
        ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
        : "bg-purple-500/10 text-purple-400 border border-purple-500/20"
    )}>
      {type === 'built-in' ? <Box className="w-3 h-3" /> : <User className="w-3 h-3" />}
      <span>{count}</span>
    </div>
  );
}
```

**Height:** ~64px

---

## Skills Page Updates

### Category Filter Tabs

Add filter tabs to the skills page:

```tsx
<div className="flex items-center gap-2 mb-6">
  <FilterTab
    active={filter === 'all'}
    onClick={() => setFilter('all')}
    count={skills.length}
  >
    All
  </FilterTab>
  <FilterTab
    active={filter === 'built-in'}
    onClick={() => setFilter('built-in')}
    count={builtInSkills.length}
    icon={<Box className="w-3.5 h-3.5" />}
  >
    Built-in
  </FilterTab>
  <FilterTab
    active={filter === 'user'}
    onClick={() => setFilter('user')}
    count={userSkills.length}
    icon={<User className="w-3.5 h-3.5" />}
  >
    User
  </FilterTab>
</div>
```

### Skill Card Category Badge

Update `SkillCard` to show category:

```tsx
<div className="flex items-center gap-2">
  <h3 className="text-base font-medium text-white/90">{skill.display_name}</h3>
  <span className={cn(
    "px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider",
    skill.category === 'built-in'
      ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
      : "bg-purple-500/10 text-purple-400 border border-purple-500/20"
  )}>
    {skill.category}
  </span>
</div>
```

---

## Removed from Landing Page

The following components are **removed** from the landing page (available via navigation):

| Component | New Location | Reason |
|-----------|--------------|--------|
| `SkillsPanel` (full) | `/skills` | Compact widget replaces it |
| `MemoryProvidersPanel` | `/memory` | Available in Memory page |
| `ChannelsPanel` | `/channels` | Available in Channels page |
| `OfficePanel` (full) | `/office` | Compact widget replaces it |

---

## Implementation Phases

### Phase 1: Core Layout Restructure
1. Create `ExpandableMetricsRow` component with collapsed/expanded states
2. Update `page.tsx` to use flexbox with `min-h-0` for no-scroll
3. Restructure chat panel for internal scrolling

### Phase 2: Compact Sidebar Widgets
1. Create `EnergyWidgetCompact` with navigation
2. Create `ServicesWidgetCompact` with provider status
3. Create `SkillsWidgetCompact` with category counts
4. Integrate Flow Mode toggle into `CurrentStepPanel`

### Phase 3: Skills Categorization
1. Update backend `/api/skills` to include `category` field
2. Update `Skill` TypeScript interface
3. Add filter tabs to Skills page
4. Update `SkillCard` to show category badge
5. Update `SkillsWidgetCompact` to show category counts

### Phase 4: Polish & Refinement
1. Animation tuning (expand/collapse, hover states)
2. Keyboard navigation (arrow keys for metrics row)
3. Responsive adjustments for smaller viewports
4. Accessibility audit (ARIA labels, focus management)

---

## Component Dependencies

### New shadcn Components Required

```bash
npx shadcn@latest add collapsible
```

### Existing Components to Modify

| Component | Modification |
|-----------|--------------|
| `page.tsx` | Complete restructure |
| `CurrentStepPanel` | Add Flow Mode toggle |
| `skills-panel.tsx` | Replace with compact widget |
| `office-panel.tsx` | Replace with compact widget |
| `energy-selector.tsx` | Add compact clickable variant |
| `skills/page.tsx` | Add category filter tabs |

### New Components to Create

| Component | Location |
|-----------|----------|
| `ExpandableMetricsRow` | `components/crystal/` |
| `MetricPill` | `components/crystal/` |
| `EnergyWidgetCompact` | `components/crystal/` |
| `ServicesWidgetCompact` | `components/crystal/` |
| `SkillsWidgetCompact` | `components/crystal/` |
| `CategoryBadge` | `components/crystal/` |
| `FilterTab` | `components/ui/` |

---

## API Changes

### GET /api/skills

**Updated Response:**
```json
{
  "skills": [
    {
      "name": "shadcn-ui",
      "display_name": "shadcn/ui",
      "description": "Component patterns guide",
      "status": "idle",
      "has_instructions": true,
      "category": "built-in",
      "source_path": "~/.claude/plugins/..."
    },
    {
      "name": "prime",
      "display_name": "Prime",
      "description": "Load project context",
      "status": "idle",
      "has_instructions": true,
      "category": "user",
      "source_path": "~/.claude/skills/prime"
    }
  ],
  "skills_dir": "~/.claude/skills",
  "counts": {
    "total": 16,
    "active": 3,
    "built_in": 12,
    "user": 4
  }
}
```

---

## Acceptance Criteria

- [ ] Landing page fits entirely within viewport without scrolling (min 900px height)
- [ ] Metrics row is collapsed by default with single-line summary
- [ ] Metrics row expands to show full cards on click
- [ ] Chat history scrolls within the chat panel
- [ ] Current Focus panel includes Flow Mode toggle
- [ ] Energy widget is compact and navigates to settings on click
- [ ] Office widget shows provider status and navigates to office page
- [ ] Skills widget shows category counts and navigates to skills page
- [ ] Skills page has filter tabs for All/Built-in/User
- [ ] Skills cards display category badges
- [ ] All compact widgets have hover states and are keyboard accessible
- [ ] Animations are smooth (200-300ms duration)

---

*Created: 2026-02-09*
*Status: Design Complete - Ready for Implementation*
