'use client';

import { useState, useEffect } from 'react';
import { Mic, Volume2, Globe, Sliders, Radio, MessageSquare } from 'lucide-react';
import { api, type VoicePreferences } from '@/lib/api';
import { cn } from '@/lib/utils';

interface VoiceSettingsProps {
  userId?: string;
  className?: string;
}

export function VoiceSettings({ userId = 'default', className }: VoiceSettingsProps) {
  const [preferences, setPreferences] = useState<VoicePreferences | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    loadPreferences();
  }, [userId]);

  async function loadPreferences() {
    setIsLoading(true);
    try {
      const response = await api.getVoicePreferences(userId);
      if (response.success && response.data) {
        // Backend returns {success, data: {preferences...}}
        const raw = response.data as unknown as { data?: VoicePreferences };
        setPreferences(raw.data ?? response.data);
      }
    } catch (e) {
      console.error('Failed to load voice preferences:', e);
    }
    setIsLoading(false);
  }

  async function updatePreference(key: string, value: unknown) {
    if (!preferences) return;
    setIsSaving(true);
    setSaveMessage(null);

    const updated = { ...preferences, [key]: value };
    setPreferences(updated);

    try {
      await api.updateVoicePreferences({ [key]: value }, userId);
      setSaveMessage('Saved');
      setTimeout(() => setSaveMessage(null), 2000);
    } catch (e) {
      setSaveMessage('Failed to save');
      // Revert
      setPreferences(preferences);
    }
    setIsSaving(false);
  }

  if (isLoading) {
    return (
      <div className={cn('animate-pulse text-white/20 text-sm', className)}>
        Loading voice settings...
      </div>
    );
  }

  if (!preferences) return null;

  return (
    <div className={cn('space-y-6', className)}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-white/70 flex items-center gap-2">
          <Mic className="w-4 h-4" />
          Voice Settings
        </h3>
        {saveMessage && (
          <span className="text-xs text-emerald-400">{saveMessage}</span>
        )}
      </div>

      {/* Enable/Disable */}
      <SettingToggle
        label="Voice Input"
        description="Enable voice commands via microphone"
        checked={preferences.enabled}
        onChange={(v) => updatePreference('enabled', v)}
      />

      {/* Language */}
      <SettingSelect
        label="Language"
        icon={<Globe className="w-4 h-4" />}
        value={preferences.language}
        options={[
          { value: 'en-US', label: 'English (US)' },
          { value: 'en-GB', label: 'English (UK)' },
          { value: 'en-AU', label: 'English (AU)' },
          { value: 'es-ES', label: 'Spanish' },
          { value: 'fr-FR', label: 'French' },
          { value: 'de-DE', label: 'German' },
          { value: 'ja-JP', label: 'Japanese' },
        ]}
        onChange={(v) => updatePreference('language', v)}
      />

      {/* Transcription Source (Phase 11b) */}
      <SettingSelect
        label="Transcription Source"
        icon={<Radio className="w-4 h-4" />}
        value={preferences.preferred_source}
        options={[
          { value: 'web_speech', label: 'Browser (Web Speech)' },
          { value: 'whisper_api', label: 'Server (Whisper API)' },
        ]}
        onChange={(v) => updatePreference('preferred_source', v)}
      />

      {/* Confidence Threshold */}
      <SettingSlider
        label="Confidence Threshold"
        icon={<Sliders className="w-4 h-4" />}
        description="Higher = fewer false commands, lower = more responsive"
        value={preferences.confidence_threshold}
        min={0.3}
        max={0.95}
        step={0.05}
        formatValue={(v) => `${Math.round(v * 100)}%`}
        onChange={(v) => updatePreference('confidence_threshold', v)}
      />

      {/* Auto Execute */}
      <SettingToggle
        label="Auto-Execute High Confidence"
        description="Automatically run commands when confidence is high"
        checked={preferences.auto_execute_high_confidence}
        onChange={(v) => updatePreference('auto_execute_high_confidence', v)}
      />

      {/* Continuous Listening (Phase 11c) */}
      <SettingToggle
        label="Continuous Listening"
        description="Keep listening after each command (auto-restart)"
        checked={preferences.continuous_listening}
        onChange={(v) => updatePreference('continuous_listening', v)}
      />

      {/* Audio Feedback */}
      <SettingToggle
        label="Audio Feedback"
        description="Play tones for voice events (start, stop, success, error)"
        checked={preferences.audio_feedback_enabled}
        onChange={(v) => updatePreference('audio_feedback_enabled', v)}
      />

      {/* Visual Feedback */}
      <SettingToggle
        label="Visual Feedback"
        description="Show transcript and confidence while speaking"
        checked={preferences.visual_feedback_enabled}
        onChange={(v) => updatePreference('visual_feedback_enabled', v)}
      />

      {/* Repeat on Low Confidence */}
      <SettingToggle
        label="Ask to Repeat"
        description='Prompt "Did you mean...?" for low-confidence commands'
        checked={preferences.repeat_on_low_confidence}
        onChange={(v) => updatePreference('repeat_on_low_confidence', v)}
      />

      {/* Confirmation Verbosity */}
      <SettingSelect
        label="Confirmation Style"
        icon={<Volume2 className="w-4 h-4" />}
        value={preferences.confirmation_verbosity}
        options={[
          { value: 'silent', label: 'Silent' },
          { value: 'brief', label: 'Brief' },
          { value: 'verbose', label: 'Verbose' },
        ]}
        onChange={(v) => updatePreference('confirmation_verbosity', v)}
      />

      {/* TTS Section (Phase 11c) */}
      <div className="pt-2 border-t border-white/[0.06]">
        <h4 className="text-xs font-medium text-white/40 mb-3 flex items-center gap-1.5">
          <MessageSquare className="w-3.5 h-3.5" />
          Text-to-Speech
        </h4>

        <div className="space-y-4">
          <SettingToggle
            label="Speak Responses"
            description="Read command results aloud via TTS"
            checked={preferences.tts_enabled}
            onChange={(v) => updatePreference('tts_enabled', v)}
          />

          {preferences.tts_enabled && (
            <>
              <SettingSelect
                label="Voice"
                value={preferences.tts_voice}
                options={[
                  { value: 'alloy', label: 'Alloy (Neutral)' },
                  { value: 'echo', label: 'Echo (Warm)' },
                  { value: 'fable', label: 'Fable (Expressive)' },
                  { value: 'onyx', label: 'Onyx (Deep)' },
                  { value: 'nova', label: 'Nova (Friendly)' },
                  { value: 'shimmer', label: 'Shimmer (Soft)' },
                ]}
                onChange={(v) => updatePreference('tts_voice', v)}
              />

              <SettingSlider
                label="Speed"
                value={preferences.tts_speed}
                min={0.5}
                max={2.0}
                step={0.1}
                formatValue={(v) => `${v.toFixed(1)}x`}
                onChange={(v) => updatePreference('tts_speed', v)}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// Setting components

function SettingToggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm text-white/60">{label}</p>
        {description && (
          <p className="text-xs text-white/30 mt-0.5">{description}</p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-5 w-9 flex-shrink-0 rounded-full',
          'transition-colors duration-200 ease-in-out',
          checked ? 'bg-emerald-500/60' : 'bg-white/10'
        )}
      >
        <span
          className={cn(
            'inline-block h-4 w-4 rounded-full bg-white transition-transform duration-200 mt-0.5',
            checked ? 'translate-x-4' : 'translate-x-0.5'
          )}
        />
      </button>
    </div>
  );
}

function SettingSelect({
  label,
  icon,
  value,
  options,
  onChange,
}: {
  label: string;
  icon?: React.ReactNode;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <p className="text-sm text-white/60 flex items-center gap-1.5">
        {icon}
        {label}
      </p>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-xs text-white/70 outline-none"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function SettingSlider({
  label,
  icon,
  description,
  value,
  min,
  max,
  step,
  formatValue,
  onChange,
}: {
  label: string;
  icon?: React.ReactNode;
  description?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  formatValue: (v: number) => string;
  onChange: (value: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm text-white/60 flex items-center gap-1.5">
          {icon}
          {label}
        </p>
        <span className="text-xs text-white/40">{formatValue(value)}</span>
      </div>
      {description && (
        <p className="text-xs text-white/30 mb-1.5">{description}</p>
      )}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-emerald-500"
      />
    </div>
  );
}
