'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, Settings, ServiceStatus } from '@/lib/api';
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
  advanced: {
    defaultModel: 'claude-3-sonnet',
    costLimitDaily: 1.0,
    costLimitMonthly: 10.0,
    debugMode: false,
  },
};

const timezones = [
  { value: 'America/New_York', label: 'Eastern Time (ET)' },
  { value: 'America/Chicago', label: 'Central Time (CT)' },
  { value: 'America/Denver', label: 'Mountain Time (MT)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
  { value: 'Europe/London', label: 'London (GMT)' },
  { value: 'Europe/Paris', label: 'Paris (CET)' },
  { value: 'Asia/Tokyo', label: 'Tokyo (JST)' },
];

const languages = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
];

const models = [
  { value: 'claude-3-opus', label: 'Claude 3 Opus (Most capable)' },
  { value: 'claude-3-sonnet', label: 'Claude 3 Sonnet (Balanced)' },
  { value: 'claude-3-haiku', label: 'Claude 3 Haiku (Fastest)' },
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
interface ApiKeysConfig {
  anthropic: { key: string; validated: boolean };
}

const defaultApiKeys: ApiKeysConfig = {
  anthropic: { key: '', validated: false },
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [channelConfig, setChannelConfig] = useState<ChannelConfig>(defaultChannelConfig);
  const [apiKeys, setApiKeys] = useState<ApiKeysConfig>(defaultApiKeys);
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [isValidatingApiKey, setIsValidatingApiKey] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['general', 'notifications', 'privacy', 'advanced', 'channels', 'apikeys'])
  );
  const { addToast } = useToastStore();

  // Load settings
  useEffect(() => {
    const loadSettings = async () => {
      setIsLoading(true);
      try {
        const [settingsRes, servicesRes] = await Promise.all([
          api.getSettings(),
          api.getServices(),
        ]);
        if (settingsRes.success && settingsRes.data) {
          setSettings(settingsRes.data);
        }
        if (servicesRes.success && servicesRes.data) {
          setServices(servicesRes.data);
          // Update channel config based on service status
          const newConfig = { ...defaultChannelConfig };
          servicesRes.data.forEach((service) => {
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
      } catch {
        // Keep defaults
      }
      setIsLoading(false);
    };
    loadSettings();
  }, []);

  // Validate API key
  const handleValidateApiKey = async () => {
    if (!apiKeys.anthropic.key) {
      addToast({ type: 'error', message: 'Please enter an API key' });
      return;
    }
    setIsValidatingApiKey(true);
    try {
      const res = await api.validateApiKey(apiKeys.anthropic.key);
      if (res.success && res.data?.success) {
        setApiKeys((prev) => ({
          ...prev,
          anthropic: { ...prev.anthropic, validated: true },
        }));
        addToast({ type: 'success', message: 'API key validated successfully' });
      } else {
        setApiKeys((prev) => ({
          ...prev,
          anthropic: { ...prev.anthropic, validated: false },
        }));
        addToast({ type: 'error', message: res.data?.error || 'API key validation failed' });
      }
    } catch {
      addToast({ type: 'error', message: 'Failed to validate API key' });
    }
    setIsValidatingApiKey(false);
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
      const res = await api.updateSettings(settings);
      if (res.success) {
        addToast({ type: 'success', message: 'Settings saved successfully' });
      } else {
        addToast({ type: 'error', message: res.error || 'Failed to save settings' });
      }
    } catch {
      addToast({ type: 'error', message: 'Failed to save settings' });
    }
    setIsSaving(false);
  }, [settings, addToast]);

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
    <div className="space-y-6 animate-fade-in max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-page-title text-text-primary">Settings</h1>
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
              </div>
              <ServiceStatusBadge service={getServiceStatus('telegram')} />
            </div>
            <FormField label="Bot Token">
              <input
                type="password"
                placeholder="Enter Telegram bot token"
                value={channelConfig.telegram.token}
                onChange={(e) =>
                  setChannelConfig((prev) => ({
                    ...prev,
                    telegram: { ...prev.telegram, token: e.target.value },
                  }))
                }
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
              </div>
              <ServiceStatusBadge service={getServiceStatus('discord')} />
            </div>
            <FormField label="Bot Token">
              <input
                type="password"
                placeholder="Enter Discord bot token"
                value={channelConfig.discord.token}
                onChange={(e) =>
                  setChannelConfig((prev) => ({
                    ...prev,
                    discord: { ...prev.discord, token: e.target.value },
                  }))
                }
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
              </div>
              <ServiceStatusBadge service={getServiceStatus('slack')} />
            </div>
            <FormField label="Bot Token (xoxb-...)">
              <input
                type="password"
                placeholder="Enter Slack bot token"
                value={channelConfig.slack.botToken}
                onChange={(e) =>
                  setChannelConfig((prev) => ({
                    ...prev,
                    slack: { ...prev.slack, botToken: e.target.value },
                  }))
                }
                className="input w-full font-mono text-sm"
              />
            </FormField>
            <FormField label="App Token (xapp-...)">
              <input
                type="password"
                placeholder="Enter Slack app token"
                value={channelConfig.slack.appToken}
                onChange={(e) =>
                  setChannelConfig((prev) => ({
                    ...prev,
                    slack: { ...prev.slack, appToken: e.target.value },
                  }))
                }
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
        <div className="space-y-4">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-body text-text-primary font-medium">Anthropic API Key</span>
              {apiKeys.anthropic.validated ? (
                <span className="badge badge-success flex items-center gap-1">
                  <CheckCircle size={12} />
                  Validated
                </span>
              ) : apiKeys.anthropic.key ? (
                <span className="badge badge-warning flex items-center gap-1">
                  <AlertCircle size={12} />
                  Not Validated
                </span>
              ) : null}
            </div>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  placeholder="sk-ant-..."
                  value={apiKeys.anthropic.key}
                  onChange={(e) =>
                    setApiKeys((prev) => ({
                      ...prev,
                      anthropic: { key: e.target.value, validated: false },
                    }))
                  }
                  className="input w-full pr-10 font-mono text-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-bg-elevated rounded"
                >
                  {showApiKey ? (
                    <EyeOff size={16} className="text-text-muted" />
                  ) : (
                    <Eye size={16} className="text-text-muted" />
                  )}
                </button>
              </div>
              <button
                onClick={handleValidateApiKey}
                disabled={isValidatingApiKey || !apiKeys.anthropic.key}
                className="btn btn-secondary flex items-center gap-2"
              >
                {isValidatingApiKey ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Check size={16} />
                )}
                Validate
              </button>
            </div>
            <p className="text-caption text-text-muted">
              Get your API key from console.anthropic.com
            </p>
          </div>

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
