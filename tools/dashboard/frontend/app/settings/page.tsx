'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, Settings, ServiceStatus, ChannelTokensResponse } from '@/lib/api';
import { useToastStore } from '@/lib/store';
import { cn } from '@/lib/utils';
import {
  User,
  Bell,
  Shield,
  Sliders,
  ChevronDown,
  ChevronUp,
  Save,
  RotateCcw,
  Check,
  Loader2,
  MessageSquare,
  Key,
  Eye,
  EyeOff,
  CheckCircle,
  XCircle,
  AlertCircle,
  Sparkles,
  Package,
  Settings2,
} from 'lucide-react';

// Default settings
const defaultSettings: Settings = {
  general: {
    displayName: 'User',
    timezone: 'America/New_York',
    language: 'en',
  },
  notifications: {
    activeHoursStart: '09:00',
    activeHoursEnd: '22:00',
    hyperfocusEnabled: true,
    urgentBypassHyperfocus: true,
  },
  privacy: {
    dataRetentionDays: 30,
    rememberConversations: true,
    rememberPreferences: true,
  },
  skills: {
    dependencyInstallMode: 'ask',
  },
  advanced: {
    defaultModel: 'claude-3-5-sonnet-20241022',
    costLimitDaily: 1.0,
    costLimitMonthly: 10.0,
    debugMode: false,
  },
};

const timezones = [
  // Americas
  { value: 'America/New_York', label: 'New York (ET)' },
  { value: 'America/Chicago', label: 'Chicago (CT)' },
  { value: 'America/Denver', label: 'Denver (MT)' },
  { value: 'America/Los_Angeles', label: 'Los Angeles (PT)' },
  { value: 'America/Anchorage', label: 'Anchorage (AKT)' },
  { value: 'America/Sao_Paulo', label: 'São Paulo (BRT)' },
  { value: 'America/Toronto', label: 'Toronto (ET)' },
  { value: 'America/Vancouver', label: 'Vancouver (PT)' },
  // Europe
  { value: 'Europe/London', label: 'London (GMT/BST)' },
  { value: 'Europe/Paris', label: 'Paris (CET)' },
  { value: 'Europe/Berlin', label: 'Berlin (CET)' },
  { value: 'Europe/Amsterdam', label: 'Amsterdam (CET)' },
  { value: 'Europe/Moscow', label: 'Moscow (MSK)' },
  // Asia
  { value: 'Asia/Tokyo', label: 'Tokyo (JST)' },
  { value: 'Asia/Shanghai', label: 'Shanghai (CST)' },
  { value: 'Asia/Hong_Kong', label: 'Hong Kong (HKT)' },
  { value: 'Asia/Singapore', label: 'Singapore (SGT)' },
  { value: 'Asia/Seoul', label: 'Seoul (KST)' },
  { value: 'Asia/Dubai', label: 'Dubai (GST)' },
  { value: 'Asia/Kolkata', label: 'India (IST)' },
  { value: 'Asia/Bangkok', label: 'Bangkok (ICT)' },
  { value: 'Asia/Jakarta', label: 'Jakarta (WIB)' },
  // Australia & Pacific
  { value: 'Australia/Melbourne', label: 'Melbourne (AEST/AEDT)' },
  { value: 'Australia/Sydney', label: 'Sydney (AEST/AEDT)' },
  { value: 'Australia/Brisbane', label: 'Brisbane (AEST)' },
  { value: 'Australia/Perth', label: 'Perth (AWST)' },
  { value: 'Australia/Adelaide', label: 'Adelaide (ACST/ACDT)' },
  { value: 'Pacific/Auckland', label: 'Auckland (NZST/NZDT)' },
  { value: 'Pacific/Fiji', label: 'Fiji (FJT)' },
  { value: 'Pacific/Honolulu', label: 'Honolulu (HST)' },
  // Africa & Middle East
  { value: 'Africa/Johannesburg', label: 'Johannesburg (SAST)' },
  { value: 'Africa/Cairo', label: 'Cairo (EET)' },
  { value: 'Africa/Lagos', label: 'Lagos (WAT)' },
  // UTC
  { value: 'UTC', label: 'UTC (Coordinated Universal Time)' },
];

const languages = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
];

const models = [
  // Claude 4 models
  { value: 'claude-opus-4-5-20251101', label: 'Claude Opus 4.5 (Most capable)' },
  { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4 (Balanced)' },
  // Claude 3.5 models
  { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet (Fast & capable)' },
  { value: 'claude-3-5-haiku-20241022', label: 'Claude 3.5 Haiku (Fastest)' },
  // Claude 3 models (legacy)
  { value: 'claude-3-opus-20240229', label: 'Claude 3 Opus (Legacy)' },
  { value: 'claude-3-sonnet-20240229', label: 'Claude 3 Sonnet (Legacy)' },
  { value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku (Legacy)' },
];

// Channel configuration
interface ChannelConfig {
  telegram: { token: string; enabled: boolean };
  discord: { token: string; enabled: boolean };
  slack: { botToken: string; appToken: string; enabled: boolean };
}

const defaultChannelConfig: ChannelConfig = {
  telegram: { token: '', enabled: false },
  discord: { token: '', enabled: false },
  slack: { botToken: '', appToken: '', enabled: false },
};

// API Keys config
interface ApiKeyState {
  key: string;
  validated: boolean;
}

interface ApiKeysConfig {
  anthropic: ApiKeyState;
  openrouter: ApiKeyState;
  openai: ApiKeyState;
  google: ApiKeyState;
}

const defaultApiKeys: ApiKeysConfig = {
  anthropic: { key: '', validated: false },
  openrouter: { key: '', validated: false },
  openai: { key: '', validated: false },
  google: { key: '', validated: false },
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [channelConfig, setChannelConfig] = useState<ChannelConfig>(defaultChannelConfig);
  const [apiKeys, setApiKeys] = useState<ApiKeysConfig>(defaultApiKeys);
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [tokenStatus, setTokenStatus] = useState<ChannelTokensResponse | null>(null);
  const [tokensModified, setTokensModified] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [showApiKey, setShowApiKey] = useState<Record<string, boolean>>({
    anthropic: false,
    openrouter: false,
    openai: false,
    google: false,
  });
  const [isValidatingApiKey, setIsValidatingApiKey] = useState<Record<string, boolean>>({
    anthropic: false,
    openrouter: false,
    openai: false,
    google: false,
  });
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['general', 'notifications', 'privacy', 'skills', 'advanced', 'channels', 'apikeys'])
  );
  const { addToast } = useToastStore();

  // Transform API settings to frontend format
  const transformApiSettings = (apiData: Record<string, unknown>): Settings => {
    // Handle the nested 'settings' object from API
    const data = (apiData?.settings || apiData) as Record<string, unknown>;

    return {
      general: {
        displayName: (data?.display_name as string) || (data?.displayName as string) || defaultSettings.general.displayName,
        timezone: (data?.timezone as string) || defaultSettings.general.timezone,
        language: (data?.language as string) || defaultSettings.general.language,
      },
      notifications: {
        activeHoursStart: ((data?.notifications as Record<string, unknown>)?.quiet_hours_start as string) ||
          ((data?.notifications as Record<string, unknown>)?.activeHoursStart as string) ||
          defaultSettings.notifications.activeHoursStart,
        activeHoursEnd: ((data?.notifications as Record<string, unknown>)?.quiet_hours_end as string) ||
          ((data?.notifications as Record<string, unknown>)?.activeHoursEnd as string) ||
          defaultSettings.notifications.activeHoursEnd,
        hyperfocusEnabled: ((data?.notifications as Record<string, unknown>)?.hyperfocusEnabled as boolean) ??
          defaultSettings.notifications.hyperfocusEnabled,
        urgentBypassHyperfocus: ((data?.notifications as Record<string, unknown>)?.urgentBypassHyperfocus as boolean) ??
          defaultSettings.notifications.urgentBypassHyperfocus,
      },
      privacy: {
        dataRetentionDays: ((data?.privacy as Record<string, unknown>)?.data_retention_days as number) ||
          ((data?.privacy as Record<string, unknown>)?.dataRetentionDays as number) ||
          defaultSettings.privacy.dataRetentionDays,
        rememberConversations: ((data?.privacy as Record<string, unknown>)?.remember_conversations as boolean) ??
          ((data?.privacy as Record<string, unknown>)?.rememberConversations as boolean) ??
          defaultSettings.privacy.rememberConversations,
        rememberPreferences: ((data?.privacy as Record<string, unknown>)?.remember_preferences as boolean) ??
          ((data?.privacy as Record<string, unknown>)?.rememberPreferences as boolean) ??
          defaultSettings.privacy.rememberPreferences,
      },
      skills: {
        dependencyInstallMode: (((data?.skill_dependencies as Record<string, unknown>)?.install_mode as string) ||
          ((data?.skills as Record<string, unknown>)?.dependencyInstallMode as string) ||
          defaultSettings.skills.dependencyInstallMode) as 'ask' | 'always' | 'never',
      },
      advanced: {
        defaultModel: ((data?.advanced as Record<string, unknown>)?.defaultModel as string) ||
          ((data?.advanced as Record<string, unknown>)?.default_model as string) ||
          defaultSettings.advanced.defaultModel,
        costLimitDaily: ((data?.advanced as Record<string, unknown>)?.costLimitDaily as number) ??
          ((data?.advanced as Record<string, unknown>)?.cost_limit_daily as number) ??
          defaultSettings.advanced.costLimitDaily,
        costLimitMonthly: ((data?.advanced as Record<string, unknown>)?.costLimitMonthly as number) ??
          ((data?.advanced as Record<string, unknown>)?.cost_limit_monthly as number) ??
          defaultSettings.advanced.costLimitMonthly,
        debugMode: ((data?.advanced as Record<string, unknown>)?.debugMode as boolean) ??
          ((data?.advanced as Record<string, unknown>)?.debug_mode as boolean) ??
          defaultSettings.advanced.debugMode,
      },
    };
  };

  // Load settings
  useEffect(() => {
    const loadSettings = async () => {
      setIsLoading(true);
      try {
        const [settingsRes, servicesRes, tokensRes] = await Promise.all([
          api.getSettings(),
          api.getServices(),
          api.getChannelTokens(),
        ]);
        if (settingsRes.success && settingsRes.data) {
          const transformed = transformApiSettings(settingsRes.data as unknown as Record<string, unknown>);
          setSettings(transformed);
        }
        if (servicesRes.success && servicesRes.data) {
          const servicesArray = Array.isArray(servicesRes.data) ? servicesRes.data : [];
          setServices(servicesArray);
          // Update channel config based on service status
          const newConfig = { ...defaultChannelConfig };
          servicesArray.forEach((service) => {
            if (service.name === 'telegram') {
              newConfig.telegram.enabled = service.status === 'running';
            } else if (service.name === 'discord') {
              newConfig.discord.enabled = service.status === 'running';
            } else if (service.name === 'slack') {
              newConfig.slack.enabled = service.status === 'running';
            }
          });
          setChannelConfig(newConfig);
        }
        if (tokensRes.success && tokensRes.data) {
          setTokenStatus(tokensRes.data);
          // Update API key validated status based on token status
          setApiKeys((prev) => ({
            ...prev,
            anthropic: {
              ...prev.anthropic,
              validated: tokensRes.data?.anthropic?.configured ?? false,
            },
            openrouter: {
              ...prev.openrouter,
              validated: tokensRes.data?.openrouter?.configured ?? false,
            },
            openai: {
              ...prev.openai,
              validated: tokensRes.data?.openai?.configured ?? false,
            },
            google: {
              ...prev.google,
              validated: tokensRes.data?.google?.configured ?? false,
            },
          }));
        }
      } catch {
        // Keep defaults
      }
      setIsLoading(false);
    };
    loadSettings();
  }, []);

  // Validate API key for a specific provider
  const handleValidateApiKey = async (provider: keyof ApiKeysConfig) => {
    if (!apiKeys[provider].key) {
      addToast({ type: 'error', message: 'Please enter an API key' });
      return;
    }
    setIsValidatingApiKey((prev) => ({ ...prev, [provider]: true }));
    try {
      const res = await api.validateApiKey(apiKeys[provider].key, provider);
      if (res.success && res.data?.success) {
        setApiKeys((prev) => ({
          ...prev,
          [provider]: { ...prev[provider], validated: true },
        }));
        addToast({ type: 'success', message: `${provider.charAt(0).toUpperCase() + provider.slice(1)} API key validated` });
      } else {
        setApiKeys((prev) => ({
          ...prev,
          [provider]: { ...prev[provider], validated: false },
        }));
        addToast({ type: 'error', message: res.data?.error || 'API key validation failed' });
      }
    } catch {
      addToast({ type: 'error', message: 'Failed to validate API key' });
    }
    setIsValidatingApiKey((prev) => ({ ...prev, [provider]: false }));
  };

  // Get service status for a channel
  const getServiceStatus = (name: string) => {
    return services.find((s) => s.name === name);
  };

  // Toggle section
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

  // Save settings
  const handleSave = useCallback(async () => {
    setIsSaving(true);
    try {
      // Transform frontend nested structure to backend flat structure
      const backendPayload = {
        display_name: settings.general.displayName,
        timezone: settings.general.timezone,
        language: settings.general.language,
        notifications: {
          enabled: true,
          quiet_hours_start: settings.notifications.activeHoursStart,
          quiet_hours_end: settings.notifications.activeHoursEnd,
        },
        privacy: {
          remember_conversations: settings.privacy.rememberConversations,
          remember_preferences: settings.privacy.rememberPreferences,
          data_retention_days: settings.privacy.dataRetentionDays,
        },
        theme: 'dark', // TODO: Add theme to frontend settings
      };

      // Cast to unknown since we're sending backend format, not frontend Settings type
      const res = await api.updateSettings(backendPayload as unknown as Partial<Settings>);

      // Save skill dependency settings
      await api.setSkillDependencySettings(settings.skills.dependencyInstallMode);

      // Save channel tokens if they've been modified
      if (tokensModified) {
        const tokenPayload: {
          telegram_token?: string;
          discord_token?: string;
          slack_bot_token?: string;
          slack_app_token?: string;
          anthropic_key?: string;
          openrouter_key?: string;
          openai_key?: string;
          google_key?: string;
        } = {};

        // Only include tokens that have values (not empty placeholders)
        if (channelConfig.telegram.token) {
          tokenPayload.telegram_token = channelConfig.telegram.token;
        }
        if (channelConfig.discord.token) {
          tokenPayload.discord_token = channelConfig.discord.token;
        }
        if (channelConfig.slack.botToken) {
          tokenPayload.slack_bot_token = channelConfig.slack.botToken;
        }
        if (channelConfig.slack.appToken) {
          tokenPayload.slack_app_token = channelConfig.slack.appToken;
        }
        if (apiKeys.anthropic.key) {
          tokenPayload.anthropic_key = apiKeys.anthropic.key;
        }
        if (apiKeys.openrouter.key) {
          tokenPayload.openrouter_key = apiKeys.openrouter.key;
        }
        if (apiKeys.openai.key) {
          tokenPayload.openai_key = apiKeys.openai.key;
        }
        if (apiKeys.google.key) {
          tokenPayload.google_key = apiKeys.google.key;
        }

        if (Object.keys(tokenPayload).length > 0) {
          const tokenRes = await api.updateChannelTokens(tokenPayload);
          if (tokenRes.success && tokenRes.data?.success) {
            addToast({
              type: 'success',
              message: tokenRes.data.message || 'Tokens updated. Restart services to apply.'
            });
            setTokensModified(false);
            // Reload token status
            const newTokens = await api.getChannelTokens();
            if (newTokens.success && newTokens.data) {
              setTokenStatus(newTokens.data);
            }
          } else {
            addToast({
              type: 'error',
              message: tokenRes.data?.error || 'Failed to save tokens'
            });
          }
        }
      }

      if (res.success) {
        addToast({ type: 'success', message: 'Settings saved successfully' });
      } else {
        addToast({ type: 'error', message: res.error || 'Failed to save settings' });
      }
    } catch {
      addToast({ type: 'error', message: 'Failed to save settings' });
    }
    setIsSaving(false);
  }, [settings, channelConfig, apiKeys, tokensModified, addToast]);

  // Reset section to defaults
  const handleReset = (section: keyof Settings) => {
    setSettings((prev) => ({
      ...prev,
      [section]: defaultSettings[section],
    }));
    addToast({ type: 'info', message: `${section} settings reset to defaults` });
  };

  // Update a setting
  const updateSetting = <T extends keyof Settings>(
    section: T,
    key: keyof Settings[T],
    value: Settings[T][keyof Settings[T]]
  ) => {
    setSettings((prev) => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: value,
      },
    }));
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-text-muted" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-8 pt-4 animate-fade-in max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Settings2 className="w-6 h-6 text-white/40" />
          <h1 className="text-2xl font-light tracking-wide text-white/90">Settings</h1>
        </div>
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="btn btn-primary flex items-center gap-2"
        >
          {isSaving ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Save size={16} />
          )}
          Save Changes
        </button>
      </div>

      {/* General Settings */}
      <SettingsSection
        id="general"
        title="General"
        icon={User}
        expanded={expandedSections.has('general')}
        onToggle={() => toggleSection('general')}
        onReset={() => handleReset('general')}
      >
        <div className="space-y-4">
          <FormField label="Display Name">
            <input
              type="text"
              value={settings.general.displayName}
              onChange={(e) =>
                updateSetting('general', 'displayName', e.target.value)
              }
              className="input w-full"
            />
          </FormField>

          <FormField label="Timezone">
            <SelectField
              value={settings.general.timezone}
              onChange={(value) => updateSetting('general', 'timezone', value)}
              options={timezones}
            />
          </FormField>

          <FormField label="Language">
            <SelectField
              value={settings.general.language}
              onChange={(value) => updateSetting('general', 'language', value)}
              options={languages}
            />
          </FormField>
        </div>
      </SettingsSection>

      {/* Notification Settings */}
      <SettingsSection
        id="notifications"
        title="Notifications"
        icon={Bell}
        expanded={expandedSections.has('notifications')}
        onToggle={() => toggleSection('notifications')}
        onReset={() => handleReset('notifications')}
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <FormField label="Active Hours Start">
              <input
                type="time"
                value={settings.notifications.activeHoursStart}
                onChange={(e) =>
                  updateSetting('notifications', 'activeHoursStart', e.target.value)
                }
                className="input w-full"
              />
            </FormField>

            <FormField label="Active Hours End">
              <input
                type="time"
                value={settings.notifications.activeHoursEnd}
                onChange={(e) =>
                  updateSetting('notifications', 'activeHoursEnd', e.target.value)
                }
                className="input w-full"
              />
            </FormField>
          </div>

          <ToggleField
            label="Hyperfocus Mode"
            description="Enable deep work protection during focused sessions"
            checked={settings.notifications.hyperfocusEnabled}
            onChange={(checked) =>
              updateSetting('notifications', 'hyperfocusEnabled', checked)
            }
          />

          <ToggleField
            label="Urgent Bypass"
            description="Allow urgent notifications during hyperfocus mode"
            checked={settings.notifications.urgentBypassHyperfocus}
            onChange={(checked) =>
              updateSetting('notifications', 'urgentBypassHyperfocus', checked)
            }
          />
        </div>
      </SettingsSection>

      {/* Privacy Settings */}
      <SettingsSection
        id="privacy"
        title="Privacy"
        icon={Shield}
        expanded={expandedSections.has('privacy')}
        onToggle={() => toggleSection('privacy')}
        onReset={() => handleReset('privacy')}
      >
        <div className="space-y-4">
          <FormField label="Data Retention (days)">
            <input
              type="number"
              min={7}
              max={365}
              value={settings.privacy.dataRetentionDays}
              onChange={(e) =>
                updateSetting('privacy', 'dataRetentionDays', parseInt(e.target.value))
              }
              className="input w-32"
            />
          </FormField>

          <ToggleField
            label="Remember Conversations"
            description="Store conversation history for context"
            checked={settings.privacy.rememberConversations}
            onChange={(checked) =>
              updateSetting('privacy', 'rememberConversations', checked)
            }
          />

          <ToggleField
            label="Remember Preferences"
            description="Learn and remember your preferences over time"
            checked={settings.privacy.rememberPreferences}
            onChange={(checked) =>
              updateSetting('privacy', 'rememberPreferences', checked)
            }
          />
        </div>
      </SettingsSection>

      {/* Advanced Settings */}
      <SettingsSection
        id="advanced"
        title="Advanced"
        icon={Sliders}
        expanded={expandedSections.has('advanced')}
        onToggle={() => toggleSection('advanced')}
        onReset={() => handleReset('advanced')}
      >
        <div className="space-y-4">
          <FormField label="Default Model">
            <SelectField
              value={settings.advanced.defaultModel}
              onChange={(value) => updateSetting('advanced', 'defaultModel', value)}
              options={models}
            />
          </FormField>

          <div className="grid grid-cols-2 gap-4">
            <FormField label="Daily Cost Limit ($)">
              <input
                type="number"
                min={0}
                step={0.5}
                value={settings.advanced.costLimitDaily}
                onChange={(e) =>
                  updateSetting('advanced', 'costLimitDaily', parseFloat(e.target.value))
                }
                className="input w-full"
              />
            </FormField>

            <FormField label="Monthly Cost Limit ($)">
              <input
                type="number"
                min={0}
                step={1}
                value={settings.advanced.costLimitMonthly}
                onChange={(e) =>
                  updateSetting('advanced', 'costLimitMonthly', parseFloat(e.target.value))
                }
                className="input w-full"
              />
            </FormField>
          </div>

          <ToggleField
            label="Debug Mode"
            description="Enable detailed logging and debug information"
            checked={settings.advanced.debugMode}
            onChange={(checked) =>
              updateSetting('advanced', 'debugMode', checked)
            }
          />
        </div>
      </SettingsSection>

      {/* Skills Settings */}
      <SettingsSection
        id="skills"
        title="Skills"
        icon={Sparkles}
        expanded={expandedSections.has('skills')}
        onToggle={() => toggleSection('skills')}
        onReset={() => handleReset('skills')}
      >
        <div className="space-y-4">
          <FormField label="Dependency Installation">
            <SelectField
              value={settings.skills.dependencyInstallMode}
              onChange={(value) => updateSetting('skills', 'dependencyInstallMode', value as 'ask' | 'always' | 'never')}
              options={[
                { value: 'ask', label: 'Ask before installing (Recommended)' },
                { value: 'always', label: 'Always install after security check' },
                { value: 'never', label: 'Never install - suggest alternatives' },
              ]}
            />
          </FormField>

          <div className="bg-bg-elevated/50 rounded-card p-3 space-y-2">
            <p className="text-caption text-text-muted">
              When Dex creates a skill that needs external packages, this controls how dependencies are handled.
            </p>
            <div className="flex items-start gap-2">
              <Package size={14} className="text-text-muted mt-0.5" />
              <div className="text-caption text-text-muted">
                <strong className="text-text-primary">Ask:</strong> Dex will request approval before installing any packages
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Package size={14} className="text-text-muted mt-0.5" />
              <div className="text-caption text-text-muted">
                <strong className="text-text-primary">Always:</strong> Packages are auto-installed after security verification
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Package size={14} className="text-text-muted mt-0.5" />
              <div className="text-caption text-text-muted">
                <strong className="text-text-primary">Never:</strong> Dex will suggest code-only alternatives or report when a dependency is required
              </div>
            </div>
          </div>
        </div>
      </SettingsSection>

      {/* Channel Configuration */}
      <SettingsSection
        id="channels"
        title="Channel Configuration"
        icon={MessageSquare}
        expanded={expandedSections.has('channels')}
        onToggle={() => toggleSection('channels')}
        onReset={() => setChannelConfig(defaultChannelConfig)}
      >
        <div className="space-y-6">
          {/* Telegram */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div
                  className="w-8 h-8 rounded flex items-center justify-center"
                  style={{ backgroundColor: '#0088cc20' }}
                >
                  <MessageSquare size={16} style={{ color: '#0088cc' }} />
                </div>
                <span className="text-body text-text-primary font-medium">Telegram</span>
                {tokenStatus?.telegram?.configured && (
                  <span className="badge badge-success text-xs">Configured</span>
                )}
              </div>
              <ServiceStatusBadge service={getServiceStatus('telegram')} />
            </div>
            <FormField label="Bot Token">
              <input
                type="password"
                placeholder={tokenStatus?.telegram?.configured
                  ? tokenStatus.telegram.masked_token || 'Token configured'
                  : 'Enter Telegram bot token'}
                value={channelConfig.telegram.token}
                onChange={(e) => {
                  setChannelConfig((prev) => ({
                    ...prev,
                    telegram: { ...prev.telegram, token: e.target.value },
                  }));
                  setTokensModified(true);
                }}
                className="input w-full font-mono text-sm"
              />
            </FormField>
            <p className="text-caption text-text-muted">
              Get your bot token from @BotFather on Telegram
            </p>
          </div>

          {/* Discord */}
          <div className="space-y-3 pt-4 border-t border-border-default">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div
                  className="w-8 h-8 rounded flex items-center justify-center"
                  style={{ backgroundColor: '#5865F220' }}
                >
                  <MessageSquare size={16} style={{ color: '#5865F2' }} />
                </div>
                <span className="text-body text-text-primary font-medium">Discord</span>
                {tokenStatus?.discord?.configured && (
                  <span className="badge badge-success text-xs">Configured</span>
                )}
              </div>
              <ServiceStatusBadge service={getServiceStatus('discord')} />
            </div>
            <FormField label="Bot Token">
              <input
                type="password"
                placeholder={tokenStatus?.discord?.configured
                  ? tokenStatus.discord.masked_token || 'Token configured'
                  : 'Enter Discord bot token'}
                value={channelConfig.discord.token}
                onChange={(e) => {
                  setChannelConfig((prev) => ({
                    ...prev,
                    discord: { ...prev.discord, token: e.target.value },
                  }));
                  setTokensModified(true);
                }}
                className="input w-full font-mono text-sm"
              />
            </FormField>
            <p className="text-caption text-text-muted">
              Create a bot at discord.com/developers/applications
            </p>
          </div>

          {/* Slack */}
          <div className="space-y-3 pt-4 border-t border-border-default">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div
                  className="w-8 h-8 rounded flex items-center justify-center"
                  style={{ backgroundColor: '#4A154B20' }}
                >
                  <MessageSquare size={16} style={{ color: '#4A154B' }} />
                </div>
                <span className="text-body text-text-primary font-medium">Slack</span>
                {tokenStatus?.slack?.configured && (
                  <span className="badge badge-success text-xs">Configured</span>
                )}
              </div>
              <ServiceStatusBadge service={getServiceStatus('slack')} />
            </div>
            <FormField label="Bot Token (xoxb-...)">
              <input
                type="password"
                placeholder={tokenStatus?.slack?.configured
                  ? tokenStatus.slack.masked_bot_token || 'Token configured'
                  : 'Enter Slack bot token'}
                value={channelConfig.slack.botToken}
                onChange={(e) => {
                  setChannelConfig((prev) => ({
                    ...prev,
                    slack: { ...prev.slack, botToken: e.target.value },
                  }));
                  setTokensModified(true);
                }}
                className="input w-full font-mono text-sm"
              />
            </FormField>
            <FormField label="App Token (xapp-...)">
              <input
                type="password"
                placeholder={tokenStatus?.slack?.configured
                  ? tokenStatus.slack.masked_app_token || 'Token configured'
                  : 'Enter Slack app token'}
                value={channelConfig.slack.appToken}
                onChange={(e) => {
                  setChannelConfig((prev) => ({
                    ...prev,
                    slack: { ...prev.slack, appToken: e.target.value },
                  }));
                  setTokensModified(true);
                }}
                className="input w-full font-mono text-sm"
              />
            </FormField>
            <p className="text-caption text-text-muted">
              Configure your Slack app at api.slack.com/apps
            </p>
          </div>

          <div className="bg-bg-elevated/50 rounded-card p-3 text-caption text-text-muted">
            <AlertCircle size={14} className="inline mr-2" />
            Channel tokens are stored securely in environment variables.
            Changes require a server restart to take effect.
          </div>
        </div>
      </SettingsSection>

      {/* API Keys */}
      <SettingsSection
        id="apikeys"
        title="API Keys"
        icon={Key}
        expanded={expandedSections.has('apikeys')}
        onToggle={() => toggleSection('apikeys')}
        onReset={() => setApiKeys(defaultApiKeys)}
      >
        <div className="space-y-6">
          {/* Anthropic API Key (Required) */}
          <ApiKeyInput
            provider="anthropic"
            label="Anthropic API Key"
            placeholder="sk-ant-..."
            helpText="Required for AI task processing."
            helpLink="https://console.anthropic.com/"
            helpLinkText="Get your key"
            configured={tokenStatus?.anthropic?.configured ?? false}
            maskedKey={tokenStatus?.anthropic?.masked_key}
            value={apiKeys.anthropic.key}
            validated={apiKeys.anthropic.validated}
            showKey={showApiKey.anthropic}
            isValidating={isValidatingApiKey.anthropic}
            onValueChange={(value) => {
              setApiKeys((prev) => ({
                ...prev,
                anthropic: { key: value, validated: false },
              }));
              setTokensModified(true);
            }}
            onToggleShow={() => setShowApiKey((prev) => ({ ...prev, anthropic: !prev.anthropic }))}
            onValidate={() => handleValidateApiKey('anthropic')}
          />

          {/* Optional Multi-Model Access divider */}
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border-default" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-bg-card px-3 text-text-muted uppercase tracking-wide">
                Optional: Multi-Model Access
              </span>
            </div>
          </div>

          {/* OpenRouter API Key */}
          <ApiKeyInput
            provider="openrouter"
            label="OpenRouter API Key"
            placeholder="sk-or-v1-..."
            helpText="Enables access to 100+ models (GPT-4, Gemini, etc.)."
            helpLink="https://openrouter.ai/keys"
            helpLinkText="Get your key"
            configured={tokenStatus?.openrouter?.configured ?? false}
            maskedKey={tokenStatus?.openrouter?.masked_key}
            value={apiKeys.openrouter.key}
            validated={apiKeys.openrouter.validated}
            showKey={showApiKey.openrouter}
            isValidating={isValidatingApiKey.openrouter}
            onValueChange={(value) => {
              setApiKeys((prev) => ({
                ...prev,
                openrouter: { key: value, validated: false },
              }));
              setTokensModified(true);
            }}
            onToggleShow={() => setShowApiKey((prev) => ({ ...prev, openrouter: !prev.openrouter }))}
            onValidate={() => handleValidateApiKey('openrouter')}
          />

          {/* OpenAI API Key */}
          <ApiKeyInput
            provider="openai"
            label="OpenAI API Key"
            placeholder="sk-..."
            helpText="Used for memory embeddings and semantic search."
            helpLink="https://platform.openai.com/api-keys"
            helpLinkText="Get your key"
            configured={tokenStatus?.openai?.configured ?? false}
            maskedKey={tokenStatus?.openai?.masked_key}
            value={apiKeys.openai.key}
            validated={apiKeys.openai.validated}
            showKey={showApiKey.openai}
            isValidating={isValidatingApiKey.openai}
            onValueChange={(value) => {
              setApiKeys((prev) => ({
                ...prev,
                openai: { key: value, validated: false },
              }));
              setTokensModified(true);
            }}
            onToggleShow={() => setShowApiKey((prev) => ({ ...prev, openai: !prev.openai }))}
            onValidate={() => handleValidateApiKey('openai')}
          />

          {/* Google API Key */}
          <ApiKeyInput
            provider="google"
            label="Google API Key"
            placeholder="AIza..."
            helpText="For direct access to Gemini models."
            helpLink="https://aistudio.google.com/app/apikey"
            helpLinkText="Get your key"
            configured={tokenStatus?.google?.configured ?? false}
            maskedKey={tokenStatus?.google?.masked_key}
            value={apiKeys.google.key}
            validated={apiKeys.google.validated}
            showKey={showApiKey.google}
            isValidating={isValidatingApiKey.google}
            onValueChange={(value) => {
              setApiKeys((prev) => ({
                ...prev,
                google: { key: value, validated: false },
              }));
              setTokensModified(true);
            }}
            onToggleShow={() => setShowApiKey((prev) => ({ ...prev, google: !prev.google }))}
            onValidate={() => handleValidateApiKey('google')}
          />

          <div className="bg-bg-elevated/50 rounded-card p-3 text-caption text-text-muted">
            <Shield size={14} className="inline mr-2" />
            API keys are encrypted and stored securely. Never share your API keys.
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}

// Settings section component
function SettingsSection({
  id,
  title,
  icon: Icon,
  expanded,
  onToggle,
  onReset,
  children,
}: {
  id: string;
  title: string;
  icon: typeof User;
  expanded: boolean;
  onToggle: () => void;
  onReset: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="card">
      {/* Header */}
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

      {/* Content */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-border-default pt-4">
          {children}

          {/* Reset button */}
          <div className="mt-6 pt-4 border-t border-border-default">
            <button
              onClick={onReset}
              className="btn btn-ghost text-caption flex items-center gap-2"
            >
              <RotateCcw size={14} />
              Reset to defaults
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// Form field wrapper
function FormField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-caption text-text-muted">{label}</label>
      {children}
    </div>
  );
}

// Select field component
function SelectField({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input w-full pr-8 appearance-none cursor-pointer"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={16}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
      />
    </div>
  );
}

// Toggle field component
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

// Service status badge component
function ServiceStatusBadge({ service }: { service?: ServiceStatus }) {
  if (!service) {
    return (
      <span className="badge bg-text-muted/20 text-text-muted">
        Unknown
      </span>
    );
  }

  switch (service.status) {
    case 'running':
      return (
        <span className="badge badge-success flex items-center gap-1">
          <CheckCircle size={12} />
          Running
        </span>
      );
    case 'stopped':
      return (
        <span className="badge bg-text-muted/20 text-text-muted flex items-center gap-1">
          Stopped
        </span>
      );
    case 'error':
      return (
        <span className="badge badge-error flex items-center gap-1">
          <XCircle size={12} />
          Error
        </span>
      );
    default:
      return (
        <span className="badge badge-warning flex items-center gap-1">
          <AlertCircle size={12} />
          {service.status}
        </span>
      );
  }
}

// API Key input component
function ApiKeyInput({
  provider,
  label,
  placeholder,
  helpText,
  helpLink,
  helpLinkText,
  configured,
  maskedKey,
  value,
  validated,
  showKey,
  isValidating,
  onValueChange,
  onToggleShow,
  onValidate,
}: {
  provider: string;
  label: string;
  placeholder: string;
  helpText: string;
  helpLink: string;
  helpLinkText: string;
  configured: boolean;
  maskedKey?: string;
  value: string;
  validated: boolean;
  showKey: boolean;
  isValidating: boolean;
  onValueChange: (value: string) => void;
  onToggleShow: () => void;
  onValidate: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-body text-text-primary font-medium">{label}</span>
          {configured && !value && (
            <span className="badge badge-success text-xs">Configured</span>
          )}
        </div>
        {validated ? (
          <span className="badge badge-success flex items-center gap-1">
            <CheckCircle size={12} />
            Validated
          </span>
        ) : value ? (
          <span className="badge badge-warning flex items-center gap-1">
            <AlertCircle size={12} />
            Not Validated
          </span>
        ) : null}
      </div>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            type={showKey ? 'text' : 'password'}
            placeholder={configured ? maskedKey || 'API key configured' : placeholder}
            value={value}
            onChange={(e) => onValueChange(e.target.value)}
            className="input w-full pr-10 font-mono text-sm"
          />
          <button
            type="button"
            onClick={onToggleShow}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-bg-elevated rounded"
          >
            {showKey ? (
              <EyeOff size={16} className="text-text-muted" />
            ) : (
              <Eye size={16} className="text-text-muted" />
            )}
          </button>
        </div>
        <button
          onClick={onValidate}
          disabled={isValidating || !value}
          className="btn btn-secondary flex items-center gap-2"
        >
          {isValidating ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Check size={16} />
          )}
          Validate
        </button>
      </div>
      <p className="text-caption text-text-muted">
        {helpText}{' '}
        <a
          href={helpLink}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent-primary hover:underline"
        >
          {helpLinkText}
        </a>
      </p>
    </div>
  );
}
