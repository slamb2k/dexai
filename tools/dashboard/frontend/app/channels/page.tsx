'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, ServiceStatus, ServiceAction } from '@/lib/api';
import { cn, formatDuration } from '@/lib/utils';
import { CrystalCard, CrystalCardHeader, CrystalCardContent } from '@/components/crystal';
import {
  Server,
  Radio,
  RefreshCw,
  Play,
  Square,
  RotateCcw,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  Settings,
  MessageSquare,
  AlertCircle,
  Loader2,
} from 'lucide-react';

// Channel icons mapping
const channelIcons: Record<string, typeof MessageSquare> = {
  telegram: MessageSquare,
  discord: MessageSquare,
  slack: MessageSquare,
};

// Channel colors
const channelColors: Record<string, string> = {
  telegram: '#0088cc',
  discord: '#5865F2',
  slack: '#4A154B',
};

export default function ChannelsPage() {
  const [channels, setChannels] = useState<ServiceStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<ServiceAction | null>(null);

  // Load channels
  const loadChannels = useCallback(async () => {
    try {
      const res = await api.getServices();
      if (res.success && res.data) {
        setChannels(res.data);
        setError(null);
      } else if (res.error) {
        setError(res.error);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load channels');
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      await loadChannels();
      setIsLoading(false);
    };
    load();

    // Auto-refresh every 30 seconds
    const interval = setInterval(loadChannels, 30000);
    return () => clearInterval(interval);
  }, [loadChannels]);

  // Channel actions
  const handleStart = async (name: string) => {
    setActionInProgress(name);
    setActionResult(null);
    try {
      const res = await api.startService(name);
      if (res.data) {
        setActionResult(res.data);
        await loadChannels();
      }
    } catch (e) {
      setActionResult({
        success: false,
        service: name,
        action: 'start',
        message: null,
        error: e instanceof Error ? e.message : 'Failed to start channel',
      });
    }
    setActionInProgress(null);
  };

  const handleStop = async (name: string) => {
    setActionInProgress(name);
    setActionResult(null);
    try {
      const res = await api.stopService(name);
      if (res.data) {
        setActionResult(res.data);
        await loadChannels();
      }
    } catch (e) {
      setActionResult({
        success: false,
        service: name,
        action: 'stop',
        message: null,
        error: e instanceof Error ? e.message : 'Failed to stop channel',
      });
    }
    setActionInProgress(null);
  };

  const handleRestart = async (name: string) => {
    setActionInProgress(name);
    setActionResult(null);
    try {
      const res = await api.restartService(name);
      if (res.data) {
        setActionResult(res.data);
        await loadChannels();
      }
    } catch (e) {
      setActionResult({
        success: false,
        service: name,
        action: 'restart',
        message: null,
        error: e instanceof Error ? e.message : 'Failed to restart channel',
      });
    }
    setActionInProgress(null);
  };

  // Get status indicator
  function getStatusIndicator(status: string) {
    switch (status) {
      case 'running':
        return <CheckCircle size={16} className="text-emerald-400" />;
      case 'stopped':
        return <Square size={16} className="text-white/40" />;
      case 'error':
        return <XCircle size={16} className="text-red-400" />;
      default:
        return <AlertTriangle size={16} className="text-amber-400" />;
    }
  }

  // Get config status badge
  function getConfigBadge(configStatus: string) {
    switch (configStatus) {
      case 'configured':
        return (
          <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            Configured
          </span>
        );
      case 'partial':
        return (
          <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30">
            Partial Config
          </span>
        );
      case 'unconfigured':
        return (
          <span className="px-2 py-0.5 text-xs rounded-full bg-white/[0.04] text-white/40 border border-white/[0.06]">
            Not Configured
          </span>
        );
      default:
        return null;
    }
  }

  return (
    <div className="space-y-8 pt-4 animate-fade-in">
      {/* Error banner */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-2xl px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Action result banner */}
      {actionResult && (
        <div
          className={cn(
            'border rounded-2xl px-4 py-3 flex items-center gap-3',
            actionResult.success
              ? 'bg-emerald-500/10 border-emerald-500/20'
              : 'bg-red-500/10 border-red-500/20'
          )}
        >
          {actionResult.success ? (
            <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0" />
          ) : (
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          )}
          <p
            className={cn(
              'text-sm',
              actionResult.success ? 'text-emerald-400' : 'text-red-400'
            )}
          >
            {actionResult.message || actionResult.error}
          </p>
          <button
            onClick={() => setActionResult(null)}
            className="ml-auto p-1 hover:bg-white/[0.04] rounded-lg transition-colors"
          >
            <XCircle size={16} className="text-white/40" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <Radio className="w-6 h-6 text-white/40" />
            <h1 className="text-2xl font-light tracking-wide text-white/90">Channels</h1>
          </div>
          <p className="text-xs text-white/40 mt-1 tracking-wide">Manage messaging platform connections</p>
        </div>
        <button
          onClick={loadChannels}
          disabled={isLoading}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-xl text-sm transition-all duration-200',
            'bg-white/[0.04] border border-white/[0.06]',
            'hover:bg-white/[0.08] hover:text-white/80',
            'text-white/60',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        >
          <RefreshCw size={16} className={cn(isLoading && 'animate-spin')} />
          Refresh
        </button>
      </div>

      {/* Channels grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-white/40" />
        </div>
      ) : channels.length === 0 ? (
        <CrystalCard className="p-8 text-center">
          <Server size={48} className="mx-auto mb-4 text-white/20" />
          <p className="text-sm text-white/60">No channels available</p>
          <p className="text-xs text-white/40 mt-1">
            Configure channel adapters in your environment to see them here
          </p>
        </CrystalCard>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {channels.map((channel) => {
            const Icon = channelIcons[channel.name] || Server;
            const color = channelColors[channel.name] || '#6366f1';
            const isActioning = actionInProgress === channel.name;

            return (
              <CrystalCard key={channel.name} padding="none" className="flex flex-col">
                <div className="p-6">
                  {/* Header */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-10 h-10 rounded-xl flex items-center justify-center"
                        style={{ backgroundColor: `${color}20` }}
                      >
                        <Icon size={20} style={{ color }} />
                      </div>
                      <div>
                        <h3 className="font-medium text-white/90">
                          {channel.display_name}
                        </h3>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          {getStatusIndicator(channel.status)}
                          <span
                            className={cn(
                              'text-xs capitalize',
                              channel.status === 'running' && 'text-emerald-400',
                              channel.status === 'stopped' && 'text-white/40',
                              channel.status === 'error' && 'text-red-400'
                            )}
                          >
                            {channel.status}
                          </span>
                        </div>
                      </div>
                    </div>
                    {getConfigBadge(channel.config_status)}
                  </div>

                  {/* Details */}
                  <div className="space-y-2 mb-4 flex-1">
                    {channel.uptime_seconds !== null && channel.status === 'running' && (
                      <div className="flex items-center gap-2 text-xs text-white/40">
                        <Clock size={14} />
                        <span>Uptime: {formatDuration(channel.uptime_seconds)}</span>
                      </div>
                    )}
                    {channel.last_activity && (
                      <div className="flex items-center gap-2 text-xs text-white/40">
                        <MessageSquare size={14} />
                        <span>
                          Last activity:{' '}
                          {new Date(channel.last_activity).toLocaleString()}
                        </span>
                      </div>
                    )}
                    {channel.error && (
                      <div className="flex items-start gap-2 text-xs text-red-400">
                        <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                        <span>{channel.error}</span>
                      </div>
                    )}
                    {channel.config_status === 'unconfigured' && (
                      <div className="flex items-center gap-2 text-xs text-white/40">
                        <Settings size={14} />
                        <span>Configure in Settings to enable</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 px-6 pb-6 pt-4 border-t border-white/[0.06]">
                  {channel.status === 'running' ? (
                    <>
                      <button
                        onClick={() => handleStop(channel.name)}
                        disabled={isActioning || channel.config_status === 'unconfigured'}
                        className={cn(
                          'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm transition-all duration-200',
                          'bg-white/[0.04] border border-white/[0.06]',
                          'hover:bg-white/[0.08] hover:text-white/80',
                          'text-white/60',
                          'disabled:opacity-50 disabled:cursor-not-allowed'
                        )}
                      >
                        {isActioning ? (
                          <Loader2 size={16} className="animate-spin" />
                        ) : (
                          <Square size={16} />
                        )}
                        Stop
                      </button>
                      <button
                        onClick={() => handleRestart(channel.name)}
                        disabled={isActioning || channel.config_status === 'unconfigured'}
                        className={cn(
                          'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm transition-all duration-200',
                          'bg-white/[0.04] border border-white/[0.06]',
                          'hover:bg-white/[0.08] hover:text-white/80',
                          'text-white/60',
                          'disabled:opacity-50 disabled:cursor-not-allowed'
                        )}
                      >
                        {isActioning ? (
                          <Loader2 size={16} className="animate-spin" />
                        ) : (
                          <RotateCcw size={16} />
                        )}
                        Restart
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => handleStart(channel.name)}
                      disabled={isActioning || channel.config_status === 'unconfigured'}
                      className={cn(
                        'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm transition-all duration-200',
                        'bg-emerald-500/80 hover:bg-emerald-500 text-white',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                      )}
                    >
                      {isActioning ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Play size={16} />
                      )}
                      Start
                    </button>
                  )}
                </div>
              </CrystalCard>
            );
          })}
        </div>
      )}

      {/* Help text */}
      <CrystalCard variant="subtle" padding="md">
        <h3 className="text-xs text-white/40 uppercase tracking-wider mb-2">
          About Channels
        </h3>
        <p className="text-sm text-white/60">
          Channels connect DexAI to messaging platforms like Telegram, Discord, and Slack.
          Each channel needs to be configured with API tokens before it can be started.
          Configure channels in the <strong className="text-white/80">Settings</strong> page.
        </p>
      </CrystalCard>
    </div>
  );
}
