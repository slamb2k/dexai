'use client';

import { Clock, ChevronRight, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface Commitment {
  id: string;
  personName: string;
  description: string;
  createdAt: Date;
  dueDate?: Date;
}

interface CommitmentBadgeProps {
  count: number;
  onClick?: () => void;
  className?: string;
}

// RSD-safe language: "waiting on you" not "you forgot" or "overdue"
export function CommitmentBadge({ count, onClick, className }: CommitmentBadgeProps) {
  if (count === 0) return null;

  return (
    <button
      onClick={onClick}
      className={cn(
        'crystal-card px-4 py-3 flex items-center justify-between gap-4 group',
        'hover:border-accent-primary/30 transition-all duration-200',
        className
      )}
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-accent-muted flex items-center justify-center">
          <Clock className="w-5 h-5 text-accent-primary" />
        </div>
        <div className="text-left">
          {/* Forward-facing, non-judgmental language */}
          <p className="text-card-title text-text-primary">
            {count === 1 ? 'Someone waiting' : `${count} people waiting`}
          </p>
          <p className="text-caption text-text-muted">
            View details
          </p>
        </div>
      </div>
      <ChevronRight className="w-5 h-5 text-text-muted group-hover:text-accent-primary transition-colors" />
    </button>
  );
}

// Expanded list view for commitments
interface CommitmentListProps {
  commitments: Commitment[];
  onSelect?: (commitment: Commitment) => void;
  className?: string;
}

export function CommitmentList({ commitments, onSelect, className }: CommitmentListProps) {
  if (commitments.length === 0) {
    return (
      <div className={cn('crystal-card p-6 text-center', className)}>
        <div className="flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-accent-muted flex items-center justify-center">
            <Clock className="w-6 h-6 text-accent-primary" />
          </div>
          <div>
            <p className="text-card-title text-text-primary">All caught up!</p>
            <p className="text-caption text-text-muted">No one waiting on you right now.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center gap-2 px-1 mb-3">
        <Clock className="w-4 h-4 text-text-muted" />
        <span className="text-caption text-text-muted uppercase tracking-wide">
          Waiting on you
        </span>
      </div>

      {commitments.map((commitment) => (
        <CommitmentItem
          key={commitment.id}
          commitment={commitment}
          onClick={() => onSelect?.(commitment)}
        />
      ))}
    </div>
  );
}

function CommitmentItem({
  commitment,
  onClick,
}: {
  commitment: Commitment;
  onClick?: () => void;
}) {
  const daysSince = Math.floor(
    (new Date().getTime() - commitment.createdAt.getTime()) / (1000 * 60 * 60 * 24)
  );

  // RSD-safe: describe the situation, don't blame
  const timeLabel =
    daysSince === 0
      ? 'today'
      : daysSince === 1
      ? 'since yesterday'
      : `${daysSince} days`;

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full crystal-card p-4 text-left group',
        'hover:border-accent-primary/30 transition-all duration-200'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {/* Person-centric language: "Sarah's waiting" not "You promised Sarah" */}
          <p className="text-body text-text-primary truncate">
            <span className="font-medium">{commitment.personName}&apos;s</span> waiting on{' '}
            {commitment.description.toLowerCase()}
          </p>
          <p className="text-caption text-text-muted mt-1">
            {timeLabel}
          </p>
        </div>
        <ChevronRight className="w-4 h-4 text-text-muted group-hover:text-accent-primary flex-shrink-0 mt-1 transition-colors" />
      </div>
    </button>
  );
}

// Inline commitment reminder for dashboard
export function CommitmentReminder({
  commitment,
  onDismiss,
  onAction,
  className,
}: {
  commitment: Commitment;
  onDismiss?: () => void;
  onAction?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'crystal-card p-4 border-accent-primary/20',
        className
      )}
    >
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-accent-muted flex items-center justify-center flex-shrink-0">
          <AlertCircle className="w-4 h-4 text-accent-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-body text-text-primary">
            {commitment.personName}&apos;s waiting on {commitment.description.toLowerCase()}
          </p>
          <div className="flex gap-2 mt-3">
            <button
              onClick={onAction}
              className="btn btn-primary text-caption py-1.5 px-3"
            >
              Handle now
            </button>
            <button
              onClick={onDismiss}
              className="btn btn-ghost text-caption py-1.5 px-3"
            >
              Later
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
