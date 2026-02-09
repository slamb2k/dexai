'use client';

import { useState, useEffect } from 'react';
import { Focus, Sparkles, Clock, CheckCircle2, SkipForward, HelpCircle, Waves } from 'lucide-react';
import { CrystalCard, CrystalCardHeader, CrystalCardContent } from './crystal-card';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

export interface CurrentStep {
  id: string;
  title: string;
  description?: string;
  energyRequired?: 'low' | 'medium' | 'high';
  estimatedTime?: string;
  category?: string;
}

interface CurrentStepPanelProps {
  step: CurrentStep | null;
  onComplete?: () => void;
  onSkip?: () => void;
  onStuck?: () => void;
  isLoading?: boolean;
  className?: string;
  showFlowMode?: boolean;
}

export function CurrentStepPanel({
  step,
  onComplete,
  onSkip,
  onStuck,
  isLoading,
  className,
  showFlowMode = true,
}: CurrentStepPanelProps) {
  const [isFlowMode, setIsFlowMode] = useState(false);
  const [flowDuration, setFlowDuration] = useState(0);

  // Fetch flow state on mount
  useEffect(() => {
    const fetchFlowState = async () => {
      try {
        const res = await api.getFlowState();
        if (res.success && res.data) {
          setIsFlowMode(res.data.is_in_flow);
          setFlowDuration(res.data.duration_minutes);
        }
      } catch (e) {
        // Flow state API may not be available
      }
    };

    if (showFlowMode) {
      fetchFlowState();
    }
  }, [showFlowMode]);

  // Flow Mode toggle component
  const FlowModeToggle = () => (
    <button
      onClick={() => setIsFlowMode(!isFlowMode)}
      className={cn(
        'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium',
        'border transition-all duration-200',
        isFlowMode
          ? 'bg-violet-500/15 border-violet-500/30 text-violet-400 hover:bg-violet-500/20'
          : 'bg-white/[0.04] border-white/[0.06] text-white/50 hover:text-white/70 hover:bg-white/[0.06]'
      )}
    >
      <Waves className="w-3 h-3" />
      {isFlowMode ? (
        <span>Flow {flowDuration > 0 ? `${flowDuration}m` : 'On'}</span>
      ) : (
        <span>Flow Mode</span>
      )}
    </button>
  );

  // Empty state when no current step
  if (!step) {
    return (
      <CrystalCard padding="none" className={cn('overflow-hidden', className)}>
        <div className="p-4">
          <CrystalCardHeader
            icon={<Focus className="w-5 h-5" />}
            title="Current Focus"
            subtitle="ADHD-friendly task focus"
            action={showFlowMode && <FlowModeToggle />}
          />
        </div>
        <CrystalCardContent className="px-4 pb-4 pt-0">
          <div className="flex flex-col items-center justify-center py-6 text-center">
            <div className="w-12 h-12 rounded-2xl bg-white/[0.04] border border-white/[0.06] flex items-center justify-center mb-4">
              <Sparkles className="w-6 h-6 text-white/20" />
            </div>
            <p className="text-sm text-white/40">
              No active task right now
            </p>
            <p className="text-xs text-white/20 mt-1">
              Ask Dex for help to get started
            </p>
          </div>
        </CrystalCardContent>
      </CrystalCard>
    );
  }

  return (
    <CrystalCard
      padding="none"
      className={cn(
        'overflow-hidden',
        'ring-1 ring-emerald-500/20',
        'shadow-lg shadow-emerald-500/5',
        className
      )}
    >
      {/* Header with accent gradient */}
      <div className="relative">
        {/* Subtle gradient accent at top */}
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-emerald-500/50 to-transparent" />

        <div className="p-4 pb-3">
          <CrystalCardHeader
            icon={<Focus className="w-5 h-5" />}
            title="Current Focus"
            action={
              <div className="flex items-center gap-2">
                {showFlowMode && <FlowModeToggle />}
                {step.category && (
                  <span className="px-2 py-0.5 rounded-lg text-xs font-medium bg-white/[0.06] text-white/60 border border-white/[0.06]">
                    {step.category}
                  </span>
                )}
              </div>
            }
          />
        </div>
      </div>

      <CrystalCardContent className="px-4 pb-4 pt-0 space-y-3">
        {/* Main task title - Large and clear for ADHD focus */}
        <div className="space-y-2">
          <h3 className="text-lg font-medium text-white/90 leading-relaxed">
            {step.title}
          </h3>
          {step.description && (
            <p className="text-sm text-white/50 leading-relaxed">
              {step.description}
            </p>
          )}
        </div>

        {/* Metadata badges */}
        {step.estimatedTime && (
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-white/[0.04] text-white/60 border border-white/[0.06]">
              <Clock className="w-3 h-3" />
              {step.estimatedTime}
            </div>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-2 pt-1">
          {/* Complete - Primary action */}
          <button
            onClick={onComplete}
            disabled={isLoading}
            className={cn(
              'flex-1 flex items-center justify-center gap-2',
              'px-4 py-3 rounded-xl',
              'bg-emerald-500/15 hover:bg-emerald-500/25',
              'text-emerald-400 hover:text-emerald-300',
              'border border-emerald-500/30 hover:border-emerald-500/50',
              'font-medium text-sm',
              'transition-all duration-200',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <CheckCircle2 className="w-4 h-4" />
            Done
          </button>

          {/* Skip - Secondary */}
          <button
            onClick={onSkip}
            disabled={isLoading}
            className={cn(
              'flex items-center justify-center gap-2',
              'px-4 py-3 rounded-xl',
              'bg-white/[0.03] hover:bg-white/[0.06]',
              'text-white/50 hover:text-white/70',
              'border border-white/[0.06] hover:border-white/[0.10]',
              'font-medium text-sm',
              'transition-all duration-200',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <SkipForward className="w-4 h-4" />
            Skip
          </button>

          {/* Stuck - Help action */}
          <button
            onClick={onStuck}
            disabled={isLoading}
            className={cn(
              'flex items-center justify-center',
              'p-3 rounded-xl',
              'bg-white/[0.03] hover:bg-amber-500/10',
              'text-white/40 hover:text-amber-400',
              'border border-white/[0.06] hover:border-amber-500/30',
              'transition-all duration-200',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
            title="I'm stuck"
          >
            <HelpCircle className="w-4 h-4" />
          </button>
        </div>
      </CrystalCardContent>
    </CrystalCard>
  );
}
