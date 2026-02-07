'use client';

import { Target, Check, SkipForward, HelpCircle, Zap, Clock, Tag } from 'lucide-react';
import { cn } from '@/lib/utils';

export type EnergyLevel = 'low' | 'medium' | 'high';

export interface CurrentStep {
  id: string;
  title: string;
  description?: string;
  energyRequired: EnergyLevel;
  estimatedTime?: string;
  category?: string;
  source?: string;
}

interface CurrentStepCardProps {
  step: CurrentStep | null;
  onComplete?: () => void;
  onSkip?: () => void;
  onStuck?: () => void;
  isLoading?: boolean;
  className?: string;
}

const energyConfig: Record<EnergyLevel, { label: string; color: string; icon: string }> = {
  low: { label: 'Low energy ok', color: 'text-energy-low', icon: '⚡' },
  medium: { label: 'Medium energy', color: 'text-energy-medium', icon: '⚡⚡' },
  high: { label: 'High energy', color: 'text-energy-high', icon: '⚡⚡⚡' },
};

export function CurrentStepCard({
  step,
  onComplete,
  onSkip,
  onStuck,
  isLoading = false,
  className,
}: CurrentStepCardProps) {
  if (isLoading) {
    return (
      <div className={cn('crystal-card p-8', className)}>
        <div className="animate-pulse space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-bg-elevated" />
            <div className="h-6 w-32 bg-bg-elevated rounded" />
          </div>
          <div className="h-8 w-full bg-bg-elevated rounded" />
          <div className="h-4 w-48 bg-bg-elevated rounded" />
        </div>
      </div>
    );
  }

  if (!step) {
    return (
      <div className={cn('crystal-card p-8 text-center', className)}>
        <div className="flex flex-col items-center gap-4">
          <div className="w-16 h-16 rounded-full bg-accent-muted flex items-center justify-center">
            <Check className="w-8 h-8 text-accent-primary" />
          </div>
          <div>
            <h3 className="text-section-header text-text-primary mb-1">All caught up!</h3>
            <p className="text-body text-text-secondary">
              No tasks waiting for you right now. Take a break or add something new.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const energy = energyConfig[step.energyRequired];

  return (
    <div className={cn('crystal-card p-6 md:p-8', className)}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-accent-muted">
          <Target className="w-5 h-5 text-accent-primary" />
        </div>
        <span className="text-card-title text-accent-primary font-semibold uppercase tracking-wide">
          Current Step
        </span>
      </div>

      {/* Divider */}
      <div className="h-px bg-border-default mb-6" />

      {/* Main Content - The ONE Thing */}
      <h2 className="text-step-title text-text-primary mb-4 leading-relaxed">
        {step.title}
      </h2>

      {/* Description (if available) */}
      {step.description && (
        <p className="text-body-lg text-text-secondary mb-6">
          {step.description}
        </p>
      )}

      {/* Meta info row */}
      <div className="flex flex-wrap items-center gap-4 mb-8 text-caption">
        {/* Energy indicator */}
        <span className={cn('flex items-center gap-1.5', energy.color)}>
          <span>{energy.icon}</span>
          <span>{energy.label}</span>
        </span>

        {/* Estimated time */}
        {step.estimatedTime && (
          <span className="flex items-center gap-1.5 text-text-muted">
            <Clock className="w-3.5 h-3.5" />
            <span>~{step.estimatedTime}</span>
          </span>
        )}

        {/* Category/source */}
        {step.category && (
          <span className="flex items-center gap-1.5 text-text-muted">
            <Tag className="w-3.5 h-3.5" />
            <span>{step.category}</span>
          </span>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={onComplete}
          className="btn-action flex items-center gap-2"
        >
          <Check className="w-5 h-5" />
          Done
        </button>
        <button
          onClick={onSkip}
          className="btn btn-ghost flex items-center gap-2"
        >
          <SkipForward className="w-4 h-4" />
          Skip for now
        </button>
        <button
          onClick={onStuck}
          className="btn btn-ghost flex items-center gap-2"
        >
          <HelpCircle className="w-4 h-4" />
          I&apos;m stuck
        </button>
      </div>
    </div>
  );
}
