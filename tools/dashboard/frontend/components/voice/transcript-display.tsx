'use client';

import { cn } from '@/lib/utils';

interface TranscriptDisplayProps {
  transcript: string;
  interimTranscript: string;
  confidence: number;
  intent?: string;
  isListening: boolean;
  isProcessing: boolean;
  error?: string | null;
  resultMessage?: string | null;
  resultSuccess?: boolean;
  className?: string;
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.85) return 'text-emerald-400';
  if (confidence >= 0.6) return 'text-amber-400';
  return 'text-red-400';
}

function getConfidenceLabel(confidence: number): string {
  if (confidence >= 0.85) return 'High';
  if (confidence >= 0.6) return 'Medium';
  if (confidence > 0) return 'Low';
  return '';
}

function formatIntent(intent: string): string {
  return intent
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function TranscriptDisplay({
  transcript,
  interimTranscript,
  confidence,
  intent,
  isListening,
  isProcessing,
  error,
  resultMessage,
  resultSuccess,
  className,
}: TranscriptDisplayProps) {
  const hasContent = transcript || interimTranscript || error || resultMessage || isListening;
  if (!hasContent) return null;

  return (
    <div
      className={cn(
        'px-4 py-2 bg-white/[0.03] border-t border-white/[0.04]',
        'text-sm transition-all duration-200',
        className
      )}
    >
      {/* Error message */}
      {error && (
        <p className="text-red-400 text-xs">{error}</p>
      )}

      {/* Result message (after command execution) */}
      {resultMessage && !error && (
        <p className={cn(
          'text-xs',
          resultSuccess ? 'text-emerald-400' : 'text-amber-400'
        )}>
          {resultMessage}
        </p>
      )}

      {/* Transcript display */}
      {!error && !resultMessage && (
        <div className="flex items-center gap-2 flex-wrap">
          {/* Final transcript */}
          {transcript && (
            <span className="text-white/70">{transcript}</span>
          )}

          {/* Interim transcript (while speaking) */}
          {interimTranscript && (
            <span className="text-white/30 italic">{interimTranscript}</span>
          )}

          {/* Listening indicator */}
          {isListening && !transcript && !interimTranscript && (
            <span className="text-white/30 italic flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
              Listening...
            </span>
          )}

          {/* Processing indicator */}
          {isProcessing && (
            <span className="text-white/30 italic">Processing...</span>
          )}

          {/* Confidence badge */}
          {confidence > 0 && transcript && !isProcessing && (
            <span className={cn(
              'text-[10px] px-1.5 py-0.5 rounded-full border',
              getConfidenceColor(confidence),
              'border-current/20'
            )}>
              {getConfidenceLabel(confidence)} ({Math.round(confidence * 100)}%)
            </span>
          )}

          {/* Intent badge */}
          {intent && intent !== 'unknown' && !isProcessing && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-400/20">
              {formatIntent(intent)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
