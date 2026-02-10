'use client';

import { Mic, MicOff, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

export type VoiceButtonState = 'idle' | 'listening' | 'processing' | 'unsupported';

interface VoiceButtonProps {
  state: VoiceButtonState;
  onClick: () => void;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function VoiceButton({
  state,
  onClick,
  className,
  size = 'sm',
}: VoiceButtonProps) {
  const isDisabled = state === 'processing' || state === 'unsupported';

  const sizeClasses = {
    sm: 'w-8 h-8 flex items-center justify-center',
    md: 'w-8 h-8 p-1.5',
    lg: 'w-11 h-11 p-2.5',
  };

  const iconSize = {
    sm: 'w-5 h-5',
    md: 'w-5 h-5',
    lg: 'w-6 h-6',
  };

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={isDisabled}
      className={cn(
        'relative transition-all duration-200 rounded-lg',
        'focus:outline-none focus:ring-2 focus:ring-white/20',
        // State-specific styles
        state === 'idle' && 'text-white/40 hover:text-white/70 cursor-pointer',
        state === 'listening' && 'text-emerald-400 cursor-pointer',
        state === 'processing' && 'text-white/30 cursor-wait',
        state === 'unsupported' && 'text-white/10 cursor-not-allowed',
        sizeClasses[size],
        className
      )}
      title={
        state === 'idle' ? 'Start voice input (V)' :
        state === 'listening' ? 'Stop listening' :
        state === 'processing' ? 'Processing...' :
        'Voice input not supported in this browser'
      }
      aria-label={
        state === 'listening' ? 'Stop voice input' : 'Start voice input'
      }
    >
      {/* Pulsing ring when listening */}
      {state === 'listening' && (
        <span className="absolute inset-0 rounded-lg animate-ping bg-emerald-400/20" />
      )}

      {/* Icon */}
      <span className="relative flex items-center justify-center">
        {state === 'processing' ? (
          <Loader2 className={cn(iconSize[size], 'animate-spin')} />
        ) : state === 'unsupported' ? (
          <MicOff className={iconSize[size]} />
        ) : (
          <Mic className={iconSize[size]} />
        )}
      </span>
    </button>
  );
}
