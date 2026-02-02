# DexAI Future Development Roadmap

> Planned phases for DexAI beyond the initial MVP. Each phase is designed with ADHD users as the primary consideration.

---

## Phase 10: Mobile Push Notifications

**Objective:** Real-time alerts on mobile devices

### Components

| Component | Description |
|-----------|-------------|
| **Firebase Cloud Messaging (FCM)** | Push notifications for Android devices |
| **Apple Push Notification Service (APNs)** | Push notifications for iOS devices |
| **Notification Preferences** | Per-user configuration for notification types, timing, and frequency |
| **Smart Batching** | Group related notifications to prevent notification fatigue |

### ADHD Considerations

- **Respect flow state:** Check flow protection status before sending non-urgent notifications
- **Gentle reminders:** Use supportive language, avoid guilt-inducing "you missed..." phrasing
- **Configurable urgency thresholds:** Let users define what's truly interrupt-worthy
- **Quiet hours:** Automatic DND during sleep/focus periods

### Technical Notes

- Requires mobile app development (React Native or Flutter)
- Server-side notification queue with priority levels
- Integration with existing `smart_notify.py` and `flow_protection.py`

---

## Phase 11: Voice Interface

**Objective:** Hands-free task capture and queries

### Components

| Component | Description |
|-----------|-------------|
| **Speech-to-Text** | Whisper API or browser Web Speech API for voice input |
| **Voice Command Parser** | NLP to extract intent and entities from spoken commands |
| **Text-to-Speech** | Response synthesis for audio feedback |
| **Wake Word Detection** | Optional "Hey Dex" trigger (privacy-conscious, on-device) |

### ADHD Considerations

- **Quick capture when hands are busy:** "Dex, remind me to call mom tomorrow"
- **Reduce friction:** Voice is faster than typing for ADHD brains in motion
- **Confirmation without interruption:** Gentle audio feedback, no screen required
- **Ambient listening opt-in only:** Respect privacy, default to push-to-talk

### Technical Notes

- Web Speech API for browser-based MVP (no cost)
- Whisper API for higher accuracy (requires API credits)
- Consider local Whisper model for privacy-sensitive users

---

## Phase 12: Calendar Integration

**Objective:** Sync with existing calendar systems

### Components

| Component | Description |
|-----------|-------------|
| **Google Calendar API** | Read/write events, sync tasks to time blocks |
| **Microsoft Graph API** | Outlook calendar integration for enterprise users |
| **Two-Way Sync** | Tasks become calendar events, calendar events inform availability |
| **Smart Scheduling** | Suggest optimal times based on energy patterns |

### ADHD Considerations

- **Visual time blocking:** See tasks in calendar context (ADHD brains need visual anchors)
- **Buffer time between events:** Auto-add transition time (ADHD time blindness mitigation)
- **Realistic scheduling:** Use historical data to prevent over-scheduling
- **Color coding by energy level:** Match task difficulty to predicted energy

### Technical Notes

- OAuth2 flows for both Google and Microsoft
- Conflict detection and resolution UI
- Respect existing calendar events as "blocked" time

---

## Phase 13: Collaborative Features

**Objective:** Accountability partnerships for external motivation

### Components

| Component | Description |
|-----------|-------------|
| **Shared Task Visibility** | Opt-in sharing of specific tasks with accountability partners |
| **Body Doubling Sessions** | Virtual co-working with presence indicators |
| **Accountability Partner Notifications** | Alert partners when tasks are completed (celebration) or stuck (support) |
| **Progress Sharing** | Weekly digest to partners (if enabled) |

### ADHD Considerations

- **External accountability without shame:** Frame as support, not surveillance
- **Celebration over criticism:** Partners see completions, not failures
- **Body doubling for hard tasks:** ADHD brains work better with others present
- **Opt-in granularity:** Share specific tasks, not everything

### Technical Notes

- Partner invitation and linking system
- Presence/status indicators (working, on break, done for day)
- Consider integration with Discord/Slack for body doubling

---

## Phase 14: Analytics & Insights

**Objective:** Help users understand their patterns without judgment

### Components

| Component | Description |
|-----------|-------------|
| **Weekly/Monthly Reports** | Summarize productivity patterns, energy trends, wins |
| **Pattern Visualization** | Charts showing time-of-day effectiveness, task completion curves |
| **Personalized Recommendations** | Actionable suggestions based on learned patterns |
| **Trend Analysis** | Long-term improvement tracking |

### ADHD Considerations

- **Celebrate wins:** Lead with accomplishments, not deficits
- **No guilt-inducing comparisons:** Compare only to self, never to others or "ideal" metrics
- **Actionable insights:** "You complete 40% more tasks before noon" not just "completion rate: 60%"
- **Opt-out of tracking:** Some users prefer not to know; respect that

### Technical Notes

- Build on existing `energy_tracker.py` and `pattern_learner.py`
- Dashboard widgets in `frontend/` for visualizations
- Export to PDF for therapy/coaching sessions

---

## Future Considerations (Post-Phase 14)

These are ideas that may be explored after the core roadmap:

| Idea | Description |
|------|-------------|
| **Wearable Integration** | Smartwatch notifications, heart rate for stress detection |
| **Medication Reminders** | Sensitive handling of ADHD medication schedules |
| **Therapist/Coach Portal** | Read-only view for healthcare providers (user-controlled) |
| **AI Coaching** | Conversational support for emotional regulation |
| **Community Features** | Anonymous ADHD community tips and wins |

---

## Implementation Priority

Recommended order based on user impact and technical dependencies:

1. **Phase 12 (Calendar)** — High user demand, foundational for scheduling
2. **Phase 10 (Mobile Push)** — Requires mobile app, but high engagement value
3. **Phase 14 (Analytics)** — Builds on existing data, low risk
4. **Phase 11 (Voice)** — Nice-to-have, good accessibility feature
5. **Phase 13 (Collaboration)** — Valuable but complex, save for later

---

*Last updated: 2026-02-02*
*This roadmap is subject to change based on user feedback and technical discoveries.*
