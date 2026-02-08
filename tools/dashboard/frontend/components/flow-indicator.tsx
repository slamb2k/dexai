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
        setElapsedTime(`${diff}m`);
      } else {
        const hours = Math.floor(diff / 60);
        const mins = diff % 60;
        setElapsedTime(`${hours}h ${mins}m`);
      }
    };

    updateTime();
    const interval = setInterval(updateTime, 60000);

    return () => clearInterval(interval);
  }, [isInFlow, flowStartTime]);

  if (compact) {
    // Compact header version - matches EnergySelector styling
    return (
      <button
        onClick={onPauseFlow}
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-xl',
          'transition-all duration-200',
          isInFlow
            ? 'bg-purple-500/10 border border-purple-500/30 hover:bg-purple-500/15'
            : 'bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06]',
          className
        )}
        title={isInFlow ? 'Click to pause flow state' : 'Flow state inactive'}
      >
        <Shield
          className={cn(
            'w-4 h-4',
            isInFlow ? 'text-purple-400' : 'text-white/30'
          )}
        />
        <span
          className={cn(
            'text-xs font-medium',
            isInFlow ? 'text-purple-400' : 'text-white/40'
          )}
        >
          {isInFlow ? 'Flow' : 'Focus'}
        </span>
        {isInFlow && elapsedTime && (
          <>
            <span className="text-purple-400/50">·</span>
            <span className="text-xs text-purple-400/70">{elapsedTime}</span>
          </>
        )}
      </button>
    );
  }

  // Full version for dashboard/settings
  if (!isInFlow) {
    return (
      <div
        className={cn(
          'p-4 rounded-2xl',
          'bg-white/[0.02] border border-white/[0.06]',
          className
        )}
      >
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'w-10 h-10 rounded-xl flex items-center justify-center',
              'bg-white/[0.04] border border-white/[0.08]'
            )}
          >
            <Shield className="w-5 h-5 text-white/30" />
          </div>
          <div>
            <p className="text-sm font-medium text-white/50">Flow State</p>
            <p className="text-xs text-white/30">Not in focus mode</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'p-4 rounded-2xl',
        'bg-purple-500/5 border border-purple-500/20',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'w-10 h-10 rounded-xl flex items-center justify-center',
              'bg-purple-500/20 border border-purple-500/30',
              'animate-pulse'
            )}
          >
            <Shield className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <p className="text-sm font-medium text-purple-300">Flow State Active</p>
            <div className="flex items-center gap-1.5 text-xs text-purple-400/60">
              <Clock className="w-3 h-3" />
              <span>{elapsedTime || '0m'} deep focus</span>
            </div>
          </div>
        </div>

        {onPauseFlow && (
          <button
            onClick={onPauseFlow}
            className={cn(
              'p-2 rounded-lg transition-colors',
              'text-purple-400/50 hover:text-purple-400 hover:bg-purple-500/10'
            )}
            title="Pause flow state"
          >
            <Pause className="w-5 h-5" />
          </button>
        )}
      </div>

      <div
        className={cn(
          'mt-3 px-3 py-2 rounded-lg',
          'bg-purple-500/10 border border-purple-500/20'
        )}
      >
        <p className="text-xs text-purple-400/80">
          Notifications are being held to protect your focus.
        </p>
      </div>
    </div>
  );
}

// Badge version for inline use
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
      : `${elapsedMinutes}m`
    : '';

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full',
        'text-xs font-medium',
        'bg-purple-500/15 text-purple-400 border border-purple-500/30',
        className
      )}
    >
      <Shield className="w-3 h-3" />
      <span>Flow</span>
      {timeLabel && <span className="text-purple-400/60">{timeLabel}</span>}
    </div>
  );
}
