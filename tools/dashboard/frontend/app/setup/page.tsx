'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  api,
  SetupState,
  ChannelValidateResponse,
  SetupPreferences,
} from '@/lib/api';
import { useToastStore } from '@/lib/store';
import { cn } from '@/lib/utils';
import {
  MessageCircle,
  Settings,
  Key,
  CheckCircle2,
  ChevronRight,
  ChevronLeft,
  Loader2,
  ExternalLink,
  Eye,
  EyeOff,
} from 'lucide-react';

// Step definitions
const STEPS = [
  { id: 'welcome', label: 'Welcome', icon: MessageCircle },
  { id: 'channel', label: 'Channel', icon: MessageCircle },
  { id: 'preferences', label: 'Preferences', icon: Settings },
  { id: 'apikey', label: 'API Key', icon: Key },
  { id: 'complete', label: 'Complete', icon: CheckCircle2 },
];

// Channel options
const CHANNELS = [
  {
    id: 'telegram',
    name: 'Telegram',
    description: 'Works great, minimal setup',
    recommended: true,
  },
  {
    id: 'discord',
    name: 'Discord',
    description: 'Good for gaming/community focus',
    recommended: false,
  },
  {
    id: 'slack',
    name: 'Slack',
    description: 'Best for work integration',
    recommended: false,
  },
];

// Timezone options
const TIMEZONES = [
  { value: 'America/New_York', label: 'Eastern Time (ET)' },
  { value: 'America/Chicago', label: 'Central Time (CT)' },
  { value: 'America/Denver', label: 'Mountain Time (MT)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
  { value: 'Europe/London', label: 'London (GMT)' },
  { value: 'Europe/Paris', label: 'Paris (CET)' },
  { value: 'Asia/Tokyo', label: 'Tokyo (JST)' },
  { value: 'Australia/Sydney', label: 'Sydney (AEST)' },
  { value: 'UTC', label: 'UTC' },
];

export default function SetupPage() {
  const router = useRouter();
  const { addToast } = useToastStore();

  // State
  const [currentStep, setCurrentStep] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [setupState, setSetupState] = useState<SetupState | null>(null);

  // Form state
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [channelToken, setChannelToken] = useState('');
  const [slackBotToken, setSlackBotToken] = useState('');
  const [slackAppToken, setSlackAppToken] = useState('');
  const [channelValidation, setChannelValidation] =
    useState<ChannelValidateResponse | null>(null);
  const [showToken, setShowToken] = useState(false);

  const [preferences, setPreferences] = useState<SetupPreferences>({
    user_name: '',
    timezone: 'America/New_York',
    active_hours_start: '09:00',
    active_hours_end: '22:00',
  });

  const [apiKey, setApiKey] = useState('');
  const [apiKeyValid, setApiKeyValid] = useState(false);
  const [skipApiKey, setSkipApiKey] = useState(false);

  // Load initial setup state
  useEffect(() => {
    const loadState = async () => {
      try {
        const res = await api.getSetupState();
        if (res.success && res.data) {
          setSetupState(res.data);

          // If setup is complete, redirect to dashboard
          if (res.data.is_complete) {
            router.push('/');
            return;
          }

          // Set detected timezone
          setPreferences((prev) => ({
            ...prev,
            timezone: res.data?.detected_timezone || prev.timezone,
          }));
        }
      } catch {
        // Continue with defaults
      }
      setIsLoading(false);
    };
    loadState();
  }, [router]);

  // Validate channel token
  const handleValidateChannel = useCallback(async () => {
    if (!selectedChannel) return;

    setIsSubmitting(true);
    setChannelValidation(null);

    try {
      const request =
        selectedChannel === 'slack'
          ? {
              channel: selectedChannel,
              bot_token: slackBotToken,
              app_token: slackAppToken,
            }
          : { channel: selectedChannel, token: channelToken };

      const res = await api.validateChannel(request);

      if (res.success && res.data) {
        setChannelValidation(res.data);
        if (res.data.success) {
          addToast({
            type: 'success',
            message: `Connected to ${res.data.bot_username || res.data.bot_name}`,
          });
        }
      }
    } catch {
      addToast({ type: 'error', message: 'Validation failed' });
    }

    setIsSubmitting(false);
  }, [
    selectedChannel,
    channelToken,
    slackBotToken,
    slackAppToken,
    addToast,
  ]);

  // Validate API key
  const handleValidateApiKey = useCallback(async () => {
    if (!apiKey) return;

    setIsSubmitting(true);
    try {
      const res = await api.validateApiKey(apiKey);
      if (res.success && res.data?.success) {
        setApiKeyValid(true);
        addToast({ type: 'success', message: 'API key is valid' });
      } else {
        setApiKeyValid(false);
        addToast({
          type: 'error',
          message: res.data?.error || 'Invalid API key',
        });
      }
    } catch {
      addToast({ type: 'error', message: 'Validation failed' });
    }
    setIsSubmitting(false);
  }, [apiKey, addToast]);

  // Complete setup
  const handleComplete = useCallback(async (forceSkipApiKey = false) => {
    setIsSubmitting(true);

    const shouldSkipApiKey = skipApiKey || forceSkipApiKey;

    try {
      // Build channel config based on selected channel type
      let channelConfig: Record<string, string> | undefined;
      if (selectedChannel === 'slack') {
        channelConfig = { bot_token: slackBotToken, app_token: slackAppToken };
      } else if (selectedChannel) {
        channelConfig = { token: channelToken };
      }

      const res = await api.completeSetup({
        channel: selectedChannel || undefined,
        channel_config: channelConfig,
        preferences,
        api_key: apiKeyValid ? apiKey : undefined,
        skip_api_key: shouldSkipApiKey,
      });

      if (res.success && res.data?.success) {
        addToast({ type: 'success', message: 'Setup complete!' });
        setCurrentStep(4); // Move to complete step
      } else {
        addToast({
          type: 'error',
          message: res.data?.error || 'Setup failed',
        });
      }
    } catch {
      addToast({ type: 'error', message: 'Setup failed' });
    }

    setIsSubmitting(false);
  }, [
    selectedChannel,
    channelToken,
    slackBotToken,
    slackAppToken,
    preferences,
    apiKey,
    apiKeyValid,
    skipApiKey,
    addToast,
  ]);

  // Navigation
  const canProceed = useCallback(() => {
    switch (currentStep) {
      case 0: // Welcome
        return true;
      case 1: // Channel
        return (
          !selectedChannel || (channelValidation?.success ?? false)
        );
      case 2: // Preferences
        return true;
      case 3: // API Key
        return apiKeyValid || skipApiKey;
      default:
        return true;
    }
  }, [currentStep, selectedChannel, channelValidation, apiKeyValid, skipApiKey]);

  const handleNext = useCallback(() => {
    if (currentStep === 3) {
      // Complete setup before moving to final step
      handleComplete();
    } else {
      setCurrentStep((prev) => Math.min(prev + 1, STEPS.length - 1));
    }
  }, [currentStep, handleComplete]);

  const handleBack = useCallback(() => {
    setCurrentStep((prev) => Math.max(prev - 1, 0));
  }, []);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-primary">
        <Loader2 className="animate-spin text-accent-primary" size={48} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-primary flex flex-col">
      {/* Deprecation banner */}
      <div className="bg-amber-500/10 border-b border-amber-500/20 px-6 py-3">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <span className="text-amber-400 text-sm">
            Setup has moved to Direct Chat. You can configure Dex by chatting on the main dashboard.
          </span>
          <button
            onClick={() => router.push('/')}
            className="ml-auto px-4 py-1.5 rounded-lg text-sm bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 transition-colors whitespace-nowrap"
          >
            Go to Direct Chat
          </button>
        </div>
      </div>

      {/* Progress indicator */}
      <div className="bg-bg-surface border-b border-border-default">
        <div className="max-w-3xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            {STEPS.map((step, index) => {
              const Icon = step.icon;
              const isActive = index === currentStep;
              const isCompleted = index < currentStep;

              return (
                <div
                  key={step.id}
                  className={cn(
                    'flex items-center',
                    index < STEPS.length - 1 && 'flex-1'
                  )}
                >
                  <div
                    className={cn(
                      'flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors',
                      isActive && 'border-accent-primary bg-accent-primary/10',
                      isCompleted && 'border-status-success bg-status-success',
                      !isActive &&
                        !isCompleted &&
                        'border-border-default bg-bg-elevated'
                    )}
                  >
                    {isCompleted ? (
                      <CheckCircle2 size={20} className="text-white" />
                    ) : (
                      <Icon
                        size={20}
                        className={cn(
                          isActive ? 'text-accent-primary' : 'text-text-muted'
                        )}
                      />
                    )}
                  </div>
                  {index < STEPS.length - 1 && (
                    <div
                      className={cn(
                        'flex-1 h-0.5 mx-2',
                        isCompleted ? 'bg-status-success' : 'bg-border-default'
                      )}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-xl">
          {/* Step 0: Welcome */}
          {currentStep === 0 && (
            <div className="text-center space-y-6 animate-fade-in">
              <div className="text-6xl">👋</div>
              <h1 className="text-page-title text-text-primary">
                Welcome to DexAI
              </h1>
              <p className="text-body text-text-secondary max-w-md mx-auto">
                I&apos;m Dex, your AI assistant designed for how your brain
                actually works. Let&apos;s get you set up in just a few minutes.
              </p>
              <div className="bg-bg-surface rounded-lg p-4 text-left">
                <p className="text-caption text-text-muted mb-2">
                  What you&apos;ll need:
                </p>
                <ul className="text-body text-text-secondary space-y-1">
                  <li>• A messaging app (Telegram, Discord, or Slack)</li>
                  <li>• About 3-5 minutes</li>
                </ul>
              </div>
            </div>
          )}

          {/* Step 1: Channel Selection */}
          {currentStep === 1 && (
            <div className="space-y-6 animate-fade-in">
              <div className="text-center">
                <h2 className="text-section-header text-text-primary">
                  Where would you like to chat with Dex?
                </h2>
                <p className="text-body text-text-secondary mt-2">
                  Pick one to start — you can add more later.
                </p>
              </div>

              <div className="space-y-3">
                {CHANNELS.map((channel) => (
                  <button
                    key={channel.id}
                    onClick={() => {
                      setSelectedChannel(channel.id);
                      setChannelValidation(null);
                    }}
                    className={cn(
                      'w-full p-4 rounded-lg border-2 text-left transition-all',
                      selectedChannel === channel.id
                        ? 'border-accent-primary bg-accent-primary/5'
                        : 'border-border-default hover:border-border-hover bg-bg-surface'
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-card-title text-text-primary">
                            {channel.name}
                          </span>
                          {channel.recommended && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-accent-primary/20 text-accent-primary">
                              Recommended
                            </span>
                          )}
                        </div>
                        <p className="text-caption text-text-muted mt-1">
                          {channel.description}
                        </p>
                      </div>
                      <div
                        className={cn(
                          'w-5 h-5 rounded-full border-2 flex items-center justify-center',
                          selectedChannel === channel.id
                            ? 'border-accent-primary'
                            : 'border-border-default'
                        )}
                      >
                        {selectedChannel === channel.id && (
                          <div className="w-3 h-3 rounded-full bg-accent-primary" />
                        )}
                      </div>
                    </div>
                  </button>
                ))}

                <button
                  onClick={() => setSelectedChannel(null)}
                  className={cn(
                    'w-full p-4 rounded-lg border-2 text-left transition-all',
                    selectedChannel === null
                      ? 'border-accent-primary bg-accent-primary/5'
                      : 'border-border-default hover:border-border-hover bg-bg-surface'
                  )}
                >
                  <span className="text-body text-text-secondary">
                    I&apos;ll configure channels later
                  </span>
                </button>
              </div>

              {/* Token input for selected channel */}
              {selectedChannel && (
                <div className="mt-6 p-4 bg-bg-surface rounded-lg border border-border-default">
                  {selectedChannel === 'telegram' && (
                    <>
                      <p className="text-caption text-text-muted mb-3">
                        1. Open{' '}
                        <a
                          href="https://t.me/BotFather"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent-primary hover:underline inline-flex items-center gap-1"
                        >
                          @BotFather <ExternalLink size={12} />
                        </a>{' '}
                        in Telegram
                        <br />
                        2. Send /newbot and follow the prompts
                        <br />
                        3. Copy the token and paste below
                      </p>
                      <div className="relative">
                        <input
                          type={showToken ? 'text' : 'password'}
                          value={channelToken}
                          onChange={(e) => setChannelToken(e.target.value)}
                          placeholder="Paste your Telegram bot token"
                          className="input w-full pr-10"
                        />
                        <button
                          onClick={() => setShowToken(!showToken)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                        >
                          {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                    </>
                  )}

                  {selectedChannel === 'discord' && (
                    <>
                      <p className="text-caption text-text-muted mb-3">
                        1. Go to{' '}
                        <a
                          href="https://discord.com/developers/applications"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent-primary hover:underline inline-flex items-center gap-1"
                        >
                          Discord Developer Portal <ExternalLink size={12} />
                        </a>
                        <br />
                        2. Create a new application
                        <br />
                        3. Go to Bot → Add Bot → Copy Token
                      </p>
                      <div className="relative">
                        <input
                          type={showToken ? 'text' : 'password'}
                          value={channelToken}
                          onChange={(e) => setChannelToken(e.target.value)}
                          placeholder="Paste your Discord bot token"
                          className="input w-full pr-10"
                        />
                        <button
                          onClick={() => setShowToken(!showToken)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                        >
                          {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                    </>
                  )}

                  {selectedChannel === 'slack' && (
                    <>
                      <p className="text-caption text-text-muted mb-3">
                        1. Go to{' '}
                        <a
                          href="https://api.slack.com/apps"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent-primary hover:underline inline-flex items-center gap-1"
                        >
                          Slack App Directory <ExternalLink size={12} />
                        </a>
                        <br />
                        2. Create a new app and install to workspace
                        <br />
                        3. Copy both tokens below
                      </p>
                      <div className="space-y-3">
                        <input
                          type="password"
                          value={slackBotToken}
                          onChange={(e) => setSlackBotToken(e.target.value)}
                          placeholder="Bot Token (xoxb-...)"
                          className="input w-full"
                        />
                        <input
                          type="password"
                          value={slackAppToken}
                          onChange={(e) => setSlackAppToken(e.target.value)}
                          placeholder="App Token (xapp-...)"
                          className="input w-full"
                        />
                      </div>
                    </>
                  )}

                  <button
                    onClick={handleValidateChannel}
                    disabled={
                      isSubmitting ||
                      (selectedChannel === 'slack'
                        ? !slackBotToken || !slackAppToken
                        : !channelToken)
                    }
                    className="btn btn-primary w-full mt-4"
                  >
                    {isSubmitting ? (
                      <Loader2 className="animate-spin" size={16} />
                    ) : (
                      'Test Connection'
                    )}
                  </button>

                  {channelValidation && (
                    <div
                      className={cn(
                        'mt-3 p-3 rounded-lg text-caption',
                        channelValidation.success
                          ? 'bg-status-success/10 text-status-success'
                          : 'bg-status-error/10 text-status-error'
                      )}
                    >
                      {channelValidation.success
                        ? `Connected! Bot: @${channelValidation.bot_username || channelValidation.bot_name}`
                        : channelValidation.error || 'Connection failed'}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Step 2: Preferences */}
          {currentStep === 2 && (
            <div className="space-y-6 animate-fade-in">
              <div className="text-center">
                <h2 className="text-section-header text-text-primary">
                  A few quick preferences
                </h2>
                <p className="text-body text-text-secondary mt-2">
                  You can change these anytime in Settings.
                </p>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-caption text-text-muted block mb-1">
                    What&apos;s your name?
                  </label>
                  <input
                    type="text"
                    value={preferences.user_name || ''}
                    onChange={(e) =>
                      setPreferences((prev) => ({
                        ...prev,
                        user_name: e.target.value,
                      }))
                    }
                    placeholder="Your name"
                    className="input w-full"
                  />
                </div>

                <div>
                  <label className="text-caption text-text-muted block mb-1">
                    What timezone are you in?
                  </label>
                  <select
                    value={preferences.timezone}
                    onChange={(e) =>
                      setPreferences((prev) => ({
                        ...prev,
                        timezone: e.target.value,
                      }))
                    }
                    className="input w-full"
                  >
                    {TIMEZONES.map((tz) => (
                      <option key={tz.value} value={tz.value}>
                        {tz.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-caption text-text-muted block mb-1">
                      Active hours start
                    </label>
                    <input
                      type="time"
                      value={preferences.active_hours_start}
                      onChange={(e) =>
                        setPreferences((prev) => ({
                          ...prev,
                          active_hours_start: e.target.value,
                        }))
                      }
                      className="input w-full"
                    />
                  </div>
                  <div>
                    <label className="text-caption text-text-muted block mb-1">
                      Active hours end
                    </label>
                    <input
                      type="time"
                      value={preferences.active_hours_end}
                      onChange={(e) =>
                        setPreferences((prev) => ({
                          ...prev,
                          active_hours_end: e.target.value,
                        }))
                      }
                      className="input w-full"
                    />
                  </div>
                </div>

                <p className="text-caption text-text-muted">
                  Dex won&apos;t disturb you outside these hours.
                </p>
              </div>
            </div>
          )}

          {/* Step 3: API Key */}
          {currentStep === 3 && (
            <div className="space-y-6 animate-fade-in">
              <div className="text-center">
                <h2 className="text-section-header text-text-primary">
                  Dex uses Claude AI
                </h2>
                <p className="text-body text-text-secondary mt-2">
                  You need an Anthropic API key to power Dex.
                </p>
              </div>

              <div className="p-4 bg-bg-surface rounded-lg border border-border-default">
                <p className="text-caption text-text-muted mb-3">
                  Get your API key from{' '}
                  <a
                    href="https://console.anthropic.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent-primary hover:underline inline-flex items-center gap-1"
                  >
                    console.anthropic.com <ExternalLink size={12} />
                  </a>
                </p>

                <div className="relative">
                  <input
                    type={showToken ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => {
                      setApiKey(e.target.value);
                      setApiKeyValid(false);
                    }}
                    placeholder="sk-ant-..."
                    className="input w-full pr-10"
                  />
                  <button
                    onClick={() => setShowToken(!showToken)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                  >
                    {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>

                <button
                  onClick={handleValidateApiKey}
                  disabled={isSubmitting || !apiKey}
                  className="btn btn-primary w-full mt-4"
                >
                  {isSubmitting ? (
                    <Loader2 className="animate-spin" size={16} />
                  ) : apiKeyValid ? (
                    <>
                      <CheckCircle2 size={16} /> Verified
                    </>
                  ) : (
                    'Verify API Key'
                  )}
                </button>
              </div>

              <div className="text-center">
                <button
                  onClick={() => {
                    setSkipApiKey(true);
                    handleComplete(true);
                  }}
                  disabled={isSubmitting}
                  className="text-caption text-text-muted hover:text-text-secondary disabled:opacity-50"
                >
                  Skip for now — I&apos;ll add it later
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Complete */}
          {currentStep === 4 && (
            <div className="text-center space-y-6 animate-fade-in">
              <div className="text-6xl">🎉</div>
              <h1 className="text-page-title text-text-primary">
                You&apos;re all set!
              </h1>
              <p className="text-body text-text-secondary max-w-md mx-auto">
                Dex is configured and ready to help.
              </p>

              <div className="bg-bg-surface rounded-lg p-6 text-left space-y-4">
                <div className="flex items-start gap-3">
                  <span className="text-xl">💬</span>
                  <div>
                    <p className="text-card-title text-text-primary">
                      Just chat naturally
                    </p>
                    <p className="text-caption text-text-muted">
                      &quot;Remind me to call mom tomorrow&quot;
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-xl">⚡</span>
                  <div>
                    <p className="text-card-title text-text-primary">
                      Dex learns your patterns
                    </p>
                    <p className="text-caption text-text-muted">
                      The more you chat, the better Dex gets
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-xl">🔕</span>
                  <div>
                    <p className="text-card-title text-text-primary">
                      Dex respects your focus
                    </p>
                    <p className="text-caption text-text-muted">
                      Won&apos;t interrupt during hyperfocus periods
                    </p>
                  </div>
                </div>
              </div>

              <button
                onClick={() => router.push('/')}
                className="btn btn-primary"
              >
                Go to Dashboard
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Navigation */}
      {currentStep < 4 && (
        <div className="bg-bg-surface border-t border-border-default">
          <div className="max-w-xl mx-auto px-6 py-4 flex justify-between">
            <button
              onClick={handleBack}
              disabled={currentStep === 0}
              className={cn(
                'btn btn-ghost flex items-center gap-2',
                currentStep === 0 && 'invisible'
              )}
            >
              <ChevronLeft size={16} /> Back
            </button>

            <button
              onClick={handleNext}
              disabled={!canProceed() || isSubmitting}
              className="btn btn-primary flex items-center gap-2"
            >
              {isSubmitting ? (
                <Loader2 className="animate-spin" size={16} />
              ) : currentStep === 3 ? (
                'Complete Setup'
              ) : (
                <>
                  Continue <ChevronRight size={16} />
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
