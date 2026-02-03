'use client';

/**
 * Push Notification Settings Page
 *
 * Allows users to:
 * - Enable/disable push notifications
 * - Configure quiet hours
 * - Manage notification categories
 * - Send test notifications
 * - View notification history
 *
 * ADHD-Friendly Design:
 * - Clear, organized sections
 * - No overwhelming options
 * - Easy toggle controls
 * - Supportive language throughout
 */

import { useEffect, useState, useCallback } from 'react';
import {
  Bell,
  BellOff,
  Moon,
  Zap,
  Clock,
  Settings,
  Send,
  History,
  ChevronDown,
  ChevronUp,
  Loader2,
  Check,
  AlertCircle,
  Smartphone,
  Monitor,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useToastStore } from '@/lib/store';
import PushSubscription from '@/components/push/PushSubscription';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

interface Preferences {
  enabled: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  timezone: string;
  respect_flow_state: boolean;
  flow_interrupt_threshold: number;
  batch_notifications: boolean;
  batch_window_minutes: number;
  max_notifications_per_hour: number;
  category_settings: Record<string, CategorySetting>;
}

interface CategorySetting {
  enabled: boolean;
  priority_threshold: number;
  batch?: boolean;
}

interface Category {
  id: string;
  name: string;
  description: string;
  default_priority: number;
  can_batch: boolean;
  can_suppress: boolean;
  color: string;
}

interface Subscription {
  id: string;
  device_name: string | null;
  device_type: string;
  browser: string | null;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

export default function PushSettingsPage() {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['subscription', 'timing', 'categories'])
  );
  const { addToast } = useToastStore();

  const userId = 'default'; // In production, get from auth context

  // Load data on mount
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [prefsRes, catsRes, subsRes] = await Promise.all([
        fetch(`${API_URL}/api/push/preferences?user_id=${userId}`, { credentials: 'include' }),
        fetch(`${API_URL}/api/push/categories`, { credentials: 'include' }),
        fetch(`${API_URL}/api/push/subscriptions?user_id=${userId}`, { credentials: 'include' }),
      ]);

      if (prefsRes.ok) {
        setPreferences(await prefsRes.json());
      }
      if (catsRes.ok) {
        const data = await catsRes.json();
        setCategories(data.categories || []);
      }
      if (subsRes.ok) {
        setSubscriptions(await subsRes.json());
      }
    } catch (e) {
      addToast({ type: 'error', message: 'Failed to load settings' });
    }
    setIsLoading(false);
  };

  const savePreferences = async (updates: Partial<Preferences>) => {
    setIsSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/push/preferences?user_id=${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(updates),
      });

      if (res.ok) {
        const updated = await res.json();
        setPreferences(updated);
        addToast({ type: 'success', message: 'Settings saved' });
      } else {
        throw new Error('Failed to save');
      }
    } catch (e) {
      addToast({ type: 'error', message: 'Failed to save settings' });
    }
    setIsSaving(false);
  };

  const updateCategoryPreference = async (categoryId: string, setting: CategorySetting) => {
    try {
      const res = await fetch(`${API_URL}/api/push/categories/${categoryId}?user_id=${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(setting),
      });

      if (res.ok) {
        // Update local state
        setPreferences((prev) =>
          prev
            ? {
                ...prev,
                category_settings: {
                  ...prev.category_settings,
                  [categoryId]: setting,
                },
              }
            : null
        );
      }
    } catch (e) {
      addToast({ type: 'error', message: 'Failed to update category' });
    }
  };

  const sendTestNotification = async () => {
    setIsTesting(true);
    try {
      const res = await fetch(`${API_URL}/api/push/test?user_id=${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          title: 'Test Notification',
          body: 'Great job setting up notifications! This is how they will look.',
        }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          addToast({ type: 'success', message: 'Test notification sent!' });
        } else {
          addToast({ type: 'error', message: 'No active subscriptions' });
        }
      }
    } catch (e) {
      addToast({ type: 'error', message: 'Failed to send test' });
    }
    setIsTesting(false);
  };

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-text-muted" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-page-title text-text-primary">Notification Settings</h1>
          <p className="text-caption text-text-muted mt-1">
            Configure how and when DexAI can reach you
          </p>
        </div>
      </div>

      {/* Subscription Section */}
      <Section
        id="subscription"
        title="Push Notifications"
        icon={Bell}
        expanded={expandedSections.has('subscription')}
        onToggle={() => toggleSection('subscription')}
      >
        <div className="space-y-4">
          <PushSubscription
            userId={userId}
            onSubscribed={() => loadData()}
            onUnsubscribed={() => loadData()}
          />

          {/* Active Devices */}
          {subscriptions.length > 0 && (
            <div className="mt-4">
              <p className="text-caption text-text-muted mb-2">Active devices:</p>
              <div className="space-y-2">
                {subscriptions.map((sub) => (
                  <div
                    key={sub.id}
                    className="flex items-center justify-between p-3 bg-bg-elevated rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      {sub.device_type === 'web' ? (
                        <Monitor size={18} className="text-text-muted" />
                      ) : (
                        <Smartphone size={18} className="text-text-muted" />
                      )}
                      <div>
                        <p className="text-body text-text-primary">
                          {sub.device_name || 'Unknown Device'}
                        </p>
                        <p className="text-caption text-text-muted">
                          {sub.browser} - Added{' '}
                          {new Date(sub.created_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    {sub.is_active && (
                      <span className="text-caption text-green-500 flex items-center gap-1">
                        <Check size={14} /> Active
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Test Button */}
          {subscriptions.length > 0 && (
            <button
              onClick={sendTestNotification}
              disabled={isTesting}
              className="btn btn-ghost flex items-center gap-2 mt-4"
            >
              {isTesting ? (
                <Loader2 className="animate-spin" size={16} />
              ) : (
                <Send size={16} />
              )}
              Send Test Notification
            </button>
          )}
        </div>
      </Section>

      {/* Timing Section */}
      <Section
        id="timing"
        title="Timing & Flow Protection"
        icon={Clock}
        expanded={expandedSections.has('timing')}
        onToggle={() => toggleSection('timing')}
      >
        <div className="space-y-6">
          {/* Quiet Hours */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Moon size={18} className="text-accent-primary" />
              <span className="text-body text-text-primary">Quiet Hours</span>
            </div>
            <p className="text-caption text-text-muted mb-3">
              No notifications during these hours (except urgent items)
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-caption text-text-muted">From</label>
                <input
                  type="time"
                  value={preferences?.quiet_hours_start || '22:00'}
                  onChange={(e) =>
                    savePreferences({
                      quiet_hours_start: e.target.value,
                      quiet_hours_end: preferences?.quiet_hours_end || '08:00',
                    })
                  }
                  className="input w-full mt-1"
                />
              </div>
              <div>
                <label className="text-caption text-text-muted">To</label>
                <input
                  type="time"
                  value={preferences?.quiet_hours_end || '08:00'}
                  onChange={(e) =>
                    savePreferences({
                      quiet_hours_start: preferences?.quiet_hours_start || '22:00',
                      quiet_hours_end: e.target.value,
                    })
                  }
                  className="input w-full mt-1"
                />
              </div>
            </div>
          </div>

          {/* Flow Protection */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Zap size={18} className="text-purple-500" />
              <span className="text-body text-text-primary">Flow Protection</span>
            </div>
            <ToggleField
              label="Respect flow state"
              description="Don't interrupt when you're in deep focus"
              checked={preferences?.respect_flow_state ?? true}
              onChange={(checked) => savePreferences({ respect_flow_state: checked })}
            />
          </div>

          {/* Rate Limiting */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Settings size={18} className="text-text-muted" />
              <span className="text-body text-text-primary">Rate Limiting</span>
            </div>
            <p className="text-caption text-text-muted mb-3">
              Prevents notification fatigue
            </p>
            <div className="space-y-3">
              <div>
                <label className="text-caption text-text-muted">
                  Max notifications per hour
                </label>
                <select
                  value={preferences?.max_notifications_per_hour || 6}
                  onChange={(e) =>
                    savePreferences({
                      max_notifications_per_hour: parseInt(e.target.value),
                    })
                  }
                  className="input w-32 mt-1"
                >
                  {[3, 6, 10, 15, 20].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>

              <ToggleField
                label="Batch notifications"
                description="Group related notifications to reduce interruptions"
                checked={preferences?.batch_notifications ?? true}
                onChange={(checked) =>
                  savePreferences({ batch_notifications: checked })
                }
              />
            </div>
          </div>
        </div>
      </Section>

      {/* Categories Section */}
      <Section
        id="categories"
        title="Notification Categories"
        icon={Bell}
        expanded={expandedSections.has('categories')}
        onToggle={() => toggleSection('categories')}
      >
        <div className="space-y-4">
          <p className="text-caption text-text-muted">
            Choose which types of notifications you want to receive
          </p>

          {categories.map((category) => {
            const setting = preferences?.category_settings?.[category.id] || {
              enabled: true,
              priority_threshold: 1,
            };

            return (
              <div
                key={category.id}
                className="flex items-start justify-between p-4 bg-bg-elevated rounded-lg"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: category.color }}
                    />
                    <span className="text-body text-text-primary">{category.name}</span>
                  </div>
                  <p className="text-caption text-text-muted mt-1">
                    {category.description}
                  </p>
                  {!category.can_suppress && (
                    <p className="text-caption text-amber-500 mt-1">
                      Always delivered (important)
                    </p>
                  )}
                </div>
                <button
                  role="switch"
                  aria-checked={setting.enabled}
                  onClick={() =>
                    updateCategoryPreference(category.id, {
                      ...setting,
                      enabled: !setting.enabled,
                    })
                  }
                  className={cn(
                    'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors',
                    setting.enabled ? 'bg-accent-primary' : 'bg-bg-input'
                  )}
                >
                  <span
                    className={cn(
                      'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition',
                      setting.enabled ? 'translate-x-5' : 'translate-x-0'
                    )}
                  />
                </button>
              </div>
            );
          })}
        </div>
      </Section>
    </div>
  );
}

// =============================================================================
// Helper Components
// =============================================================================

function Section({
  id,
  title,
  icon: Icon,
  expanded,
  onToggle,
  children,
}: {
  id: string;
  title: string;
  icon: typeof Bell;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="card">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-bg-elevated transition-colors"
      >
        <div className="flex items-center gap-3">
          <Icon size={20} className="text-accent-primary" />
          <span className="text-card-title text-text-primary">{title}</span>
        </div>
        {expanded ? (
          <ChevronUp size={20} className="text-text-muted" />
        ) : (
          <ChevronDown size={20} className="text-text-muted" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-border-default pt-4">
          {children}
        </div>
      )}
    </div>
  );
}

function ToggleField({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-body text-text-primary">{label}</p>
        {description && (
          <p className="text-caption text-text-muted">{description}</p>
        )}
      </div>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors',
          checked ? 'bg-accent-primary' : 'bg-bg-input'
        )}
      >
        <span
          className={cn(
            'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition',
            checked ? 'translate-x-5' : 'translate-x-0'
          )}
        />
      </button>
    </div>
  );
}
