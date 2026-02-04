'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, ServiceStatus, ServiceAction } from '@/lib/api';
import { cn, formatDuration } from '@/lib/utils';
import {
  Server,
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

// Service icons mapping
const serviceIcons: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  telegram: MessageSquare,
  discord: MessageSquare,
  slack: MessageSquare,
};

// Service colors
const serviceColors: Record<string, string> = {
  telegram: '#0088cc',
  discord: '#5865F2',
  slack: '#4A154B',
};

export default function ServicesPage() {
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<ServiceAction | null>(null);

  // Load services
  const loadServices = useCallback(async () => {
    try {
      const res = await api.getServices();
      if (res.success && res.data) {
        setServices(res.data);
        setError(null);
      } else if (res.error) {
        setError(res.error);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load services');
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      await loadServices();
      setIsLoading(false);
    };
    load();

    // Auto-refresh every 30 seconds
    const interval = setInterval(loadServices, 30000);
    return () => clearInterval(interval);
  }, [loadServices]);

  // Service actions
  const handleStart = async (name: string) => {
    setActionInProgress(name);
    setActionResult(null);
    try {
      const res = await api.startService(name);
      if (res.data) {
        setActionResult(res.data);
        await loadServices();
      }
    } catch (e) {
      setActionResult({
        success: false,
        service: name,
        action: 'start',
        message: null,
        error: e instanceof Error ? e.message : 'Failed to start service',
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
        await loadServices();
      }
    } catch (e) {
      setActionResult({
        success: false,
        service: name,
        action: 'stop',
        message: null,
        error: e instanceof Error ? e.message : 'Failed to stop service',
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
        await loadServices();
      }
    } catch (e) {
      setActionResult({
        success: false,
        service: name,
        action: 'restart',
        message: null,
        error: e instanceof Error ? e.message : 'Failed to restart service',
      });
    }
    setActionInProgress(null);
  };

  // Get status indicator
  const getStatusIndicator = (status: string) => {
    switch (status) {
      case 'running':
        return <CheckCircle size={16} className="text-status-success" />;
      case 'stopped':
        return <Square size={16} className="text-text-muted" />;
      case 'error':
        return <XCircle size={16} className="text-status-error" />;
      default:
        return <AlertTriangle size={16} className="text-status-warning" />;
    }
  };

  // Get config status badge
  const getConfigBadge = (configStatus: string) => {
    switch (configStatus) {
      case 'configured':
        return (
          <span className="badge badge-success">Configured</span>
        );
      case 'partial':
        return (
          <span className="badge badge-warning">Partial Config</span>
        );
      case 'unconfigured':
        return (
          <span className="badge bg-text-muted/20 text-text-muted">Not Configured</span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Error banner */}
      {error && (
        <div className="bg-status-error/10 border border-status-error/30 rounded-card px-4 py-3 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-status-error flex-shrink-0" />
          <p className="text-body text-status-error">{error}</p>
        </div>
      )}

      {/* Action result banner */}
      {actionResult && (
        <div
          className={cn(
            'border rounded-card px-4 py-3 flex items-center gap-3',
            actionResult.success
              ? 'bg-status-success/10 border-status-success/30'
              : 'bg-status-error/10 border-status-error/30'
          )}
        >
          {actionResult.success ? (
            <CheckCircle className="w-5 h-5 text-status-success flex-shrink-0" />
          ) : (
            <XCircle className="w-5 h-5 text-status-error flex-shrink-0" />
          )}
          <p
            className={cn(
              'text-body',
              actionResult.success ? 'text-status-success' : 'text-status-error'
            )}
          >
            {actionResult.message || actionResult.error}
          </p>
          <button
            onClick={() => setActionResult(null)}
            className="ml-auto p-1 hover:bg-bg-elevated rounded"
          >
            <XCircle size={16} className="text-text-muted" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Server className="text-accent-primary" size={24} />
          <h1 className="text-page-title text-text-primary">Services</h1>
        </div>
        <button
          onClick={loadServices}
          disabled={isLoading}
          className="btn btn-secondary flex items-center gap-2"
        >
          <RefreshCw size={16} className={cn(isLoading && 'animate-spin')} />
          Refresh
        </button>
      </div>

      {/* Services grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-text-muted" />
        </div>
      ) : services.length === 0 ? (
        <div className="card p-8 text-center">
          <Server size={48} className="mx-auto mb-4 text-text-muted opacity-50" />
          <p className="text-body text-text-muted">No services available</p>
          <p className="text-caption text-text-muted mt-1">
            Configure channel adapters in your environment to see them here
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {services.map((service) => {
            const Icon = serviceIcons[service.name] || Server;
            const color = serviceColors[service.name] || '#6366f1';
            const isActioning = actionInProgress === service.name;

            return (
              <div
                key={service.name}
                className="card p-6 flex flex-col"
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center"
                      style={{ backgroundColor: `${color}20` }}
                    >
                      <Icon size={20} style={{ color }} />
                    </div>
                    <div>
                      <h3 className="text-card-title text-text-primary">
                        {service.display_name}
                      </h3>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {getStatusIndicator(service.status)}
                        <span
                          className={cn(
                            'text-caption capitalize',
                            service.status === 'running' && 'text-status-success',
                            service.status === 'stopped' && 'text-text-muted',
                            service.status === 'error' && 'text-status-error'
                          )}
                        >
                          {service.status}
                        </span>
                      </div>
                    </div>
                  </div>
                  {getConfigBadge(service.config_status)}
                </div>

                {/* Details */}
                <div className="space-y-2 mb-4 flex-1">
                  {service.uptime_seconds !== null && service.status === 'running' && (
                    <div className="flex items-center gap-2 text-caption text-text-muted">
                      <Clock size={14} />
                      <span>Uptime: {formatDuration(service.uptime_seconds)}</span>
                    </div>
                  )}
                  {service.last_activity && (
                    <div className="flex items-center gap-2 text-caption text-text-muted">
                      <MessageSquare size={14} />
                      <span>
                        Last activity:{' '}
                        {new Date(service.last_activity).toLocaleString()}
                      </span>
                    </div>
                  )}
                  {service.error && (
                    <div className="flex items-start gap-2 text-caption text-status-error">
                      <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                      <span>{service.error}</span>
                    </div>
                  )}
                  {service.config_status === 'unconfigured' && (
                    <div className="flex items-center gap-2 text-caption text-text-muted">
                      <Settings size={14} />
                      <span>Configure in Settings to enable</span>
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 pt-4 border-t border-border-default">
                  {service.status === 'running' ? (
                    <>
                      <button
                        onClick={() => handleStop(service.name)}
                        disabled={isActioning || service.config_status === 'unconfigured'}
                        className="btn btn-secondary flex-1 flex items-center justify-center gap-2"
                      >
                        {isActioning ? (
                          <Loader2 size={16} className="animate-spin" />
                        ) : (
                          <Square size={16} />
                        )}
                        Stop
                      </button>
                      <button
                        onClick={() => handleRestart(service.name)}
                        disabled={isActioning || service.config_status === 'unconfigured'}
                        className="btn btn-secondary flex-1 flex items-center justify-center gap-2"
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
                      onClick={() => handleStart(service.name)}
                      disabled={isActioning || service.config_status === 'unconfigured'}
                      className="btn btn-primary flex-1 flex items-center justify-center gap-2"
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
              </div>
            );
          })}
        </div>
      )}

      {/* Help text */}
      <div className="card p-4 bg-bg-elevated/50">
        <h3 className="text-caption text-text-muted uppercase tracking-wider mb-2">
          About Services
        </h3>
        <p className="text-body text-text-secondary">
          Services are the channel adapters that connect DexAI to messaging platforms.
          Each service needs to be configured with API tokens before it can be started.
          Configure services in the <strong>Settings</strong> page.
        </p>
      </div>
    </div>
  );
}
