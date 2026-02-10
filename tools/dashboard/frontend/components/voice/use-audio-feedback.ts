'use client';

import { useRef, useCallback } from 'react';

export type ToneType = 'start' | 'stop' | 'success' | 'error';

export interface UseAudioFeedbackReturn {
  playTone: (type: ToneType) => void;
}

/**
 * Hook for synthesised audio feedback tones via Web Audio API (Phase 11c).
 *
 * Generates short tonal cues to indicate voice state changes:
 * - start: ascending two-note (C5 → E5) — "ready"
 * - stop: descending two-note (E5 → C5) — "done"
 * - success: major triad arpeggio (C5 → E5 → G5) — "great"
 * - error: minor second (C5 → Db5) — "oops"
 *
 * No audio files required — pure synthesis, zero network cost.
 */
export function useAudioFeedback(enabled: boolean = true): UseAudioFeedbackReturn {
  const audioContextRef = useRef<AudioContext | null>(null);

  const getContext = useCallback(() => {
    if (!audioContextRef.current && typeof AudioContext !== 'undefined') {
      audioContextRef.current = new AudioContext();
    }
    return audioContextRef.current;
  }, []);

  const playTone = useCallback(
    (type: ToneType) => {
      if (!enabled) return;

      const ctx = getContext();
      if (!ctx) return;

      // Resume context if suspended (browser autoplay policy)
      if (ctx.state === 'suspended') {
        ctx.resume();
      }

      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      // Keep volume subtle so it's informative, not intrusive
      gain.gain.setValueAtTime(0.15, now);
      osc.start(now);

      switch (type) {
        case 'start':
          // Ascending two-note (C5 → E5)
          osc.frequency.setValueAtTime(523, now);
          osc.frequency.setValueAtTime(659, now + 0.08);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
          osc.stop(now + 0.2);
          break;

        case 'stop':
          // Descending two-note (E5 → C5)
          osc.frequency.setValueAtTime(659, now);
          osc.frequency.setValueAtTime(523, now + 0.08);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
          osc.stop(now + 0.2);
          break;

        case 'success':
          // Major triad arpeggio (C5 → E5 → G5)
          osc.frequency.setValueAtTime(523, now);
          osc.frequency.setValueAtTime(659, now + 0.08);
          osc.frequency.setValueAtTime(784, now + 0.16);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
          osc.stop(now + 0.3);
          break;

        case 'error':
          // Minor second (C5 → Db5)
          osc.frequency.setValueAtTime(523, now);
          osc.frequency.setValueAtTime(554, now + 0.12);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
          osc.stop(now + 0.3);
          break;
      }
    },
    [enabled, getContext]
  );

  return { playTone };
}
