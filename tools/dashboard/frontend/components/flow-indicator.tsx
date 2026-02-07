'use client';

import { Shield, Clock, Pause } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useEffect, useState } from 'react';

interface FlowIndicatorProps {
  isInFlow: boolean;
  flowStartTime?: Date;
  onPauseFlow?: () => void;
  className?: string;
  compact?: boolean;
}

export function FlowIndicator({
  isInFlow,
  flowStartTime,
  onPauseFlow,
  className,
  compact = false,
}: FlowIndicatorProps) {
  const [elapsedTime, setElapsedTime] = useState<string>('');

  // Update elapsed time every minute
  useEffect(() => {
    if (!isInFlow || !flowStartTime) {
      setElapsedTime('');
      return;
    }

    const updateTime = () => {
      const now = new Date();
      const diff = Math.floor((now.getTime() - flowStartTime.getTime()) / 1000 / 60);

      if (diff < 60) {
        setElapsedTime(`${diff}min`);
      } else {
        const hours = Math.floor(diff / 60);
        const mins = diff % 60;
        setElapsedTime(`${hours}h ${mins}m`);
      }
    };

    updateTime();
    const interval = setInterval(updateTime, 60000); // Update every minute

    return () => clearInterval(interval);
  }, [isInFlow, flowStartTime]);

  if (!isInFlow) {
    return (
      <div className={cn('crystal-card p-4', className)}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-bg-surface border border-border-default flex items-center justify-center">
            <Shield className="w-5 h-5 text-text-muted" />
          </div>
          <div>
            <p className="text-card-title text-text-secondary">Flow State</p>
            <p className="text-caption text-text-muted">Not in focus mode</p>
          </div>
        </div>
      </div>
    );
  }

  if (compact) {
    return (
      <div
        className={cn(
          'flow-badge active cursor-pointer',
          className
        )}
        onClick={onPauseFlow}
        title="Click to pause flow state"
      >
        <Shield className="w-4 h-4" />
        <span className="font-medium">Flow</span>
        {elapsedTime && (
          <>
            <span className="text-text-muted">|</span>
            <span>{elapsedTime}</span>
          </>
        )}
      </div>
    );
  }

  return (
    <div className={cn('crystal-card p-4 border-status-hyperfocus/30', className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-status-hyperfocus/20 flex items-center justify-center animate-glow-pulse">
            <Shield className="w-5 h-5 text-status-hyperfocus" />
          </div>
          <div>
            <p className="text-card-title text-status-hyperfocus font-medium">
              Flow State Active
            </p>
            <div className="flex items-center gap-2 text-caption text-text-muted">
              <Clock className="w-3.5 h-3.5" />
              <span>{elapsedTime || '0min'} deep focus</span>
            </div>
          </div>
        </div>

        {onPauseFlow && (
          <button
            onClick={onPauseFlow}
            className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors"
            title="Pause flow state"
          >
            <Pause className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Protecting focus message */}
      <div className="mt-3 p-3 rounded-lg bg-status-hyperfocus/10 border border-status-hyperfocus/20">
        <p className="text-caption text-status-hyperfocus">
          Notifications are being held to protect your focus.
        </p>
      </div>
    </div>
  );
}

// Minimal version for top bar
export function FlowBadge({
  isInFlow,
  elapsedMinutes,
  className,
}: {
  isInFlow: boolean;
  elapsedMinutes?: number;
  className?: string;
}) {
  if (!isInFlow) return null;

  const timeLabel = elapsedMinutes
    ? elapsedMinutes >= 60
      ? `${Math.floor(elapsedMinutes / 60)}h ${elapsedMinutes % 60}m`
      : `${elapsedMinutes}min`
    : '';

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium',
        'bg-status-hyperfocus/15 text-status-hyperfocus border border-status-hyperfocus/30',
        'animate-glow-pulse',
        className
      )}
    >
      <Shield className="w-3.5 h-3.5" />
      <span>Flow</span>
      {timeLabel && <span className="opacity-70">{timeLabel}</span>}
    </div>
  );
}
