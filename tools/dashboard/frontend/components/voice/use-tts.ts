'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { api } from '@/lib/api';

export interface UseTTSOptions {
  /** Use cloud TTS (OpenAI) instead of browser SpeechSynthesis. */
  preferCloud?: boolean;
  /** Cloud TTS voice (alloy, echo, fable, onyx, nova, shimmer). */
  voice?: string;
  /** Playback speed (0.25–4.0). */
  speed?: number;
  /** User ID for API calls. */
  userId?: string;
}

export interface UseTTSReturn {
  isSupported: boolean;
  isSpeaking: boolean;
  speak: (text: string) => Promise<void>;
  stop: () => void;
}

/**
 * Hook for text-to-speech playback (Phase 11c).
 *
 * Supports two modes:
 * - Browser SpeechSynthesis API (free, no cost)
 * - Cloud TTS via /api/voice/tts (higher quality, falls back to browser)
 */
export function useTTS(options: UseTTSOptions = {}): UseTTSReturn {
  const {
    preferCloud = false,
    voice = 'alloy',
    speed = 1.0,
    userId = 'default',
  } = options;

  const [isSupported] = useState(
    () =>
      typeof window !== 'undefined' &&
      (typeof speechSynthesis !== 'undefined' || preferCloud)
  );
  const [isSpeaking, setIsSpeaking] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mountedRef = useRef(true);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      mountedRef.current = false;
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      if (typeof speechSynthesis !== 'undefined') {
        speechSynthesis.cancel();
      }
    };
  }, []);

  const speakBrowser = useCallback(
    (text: string): Promise<void> => {
      return new Promise((resolve) => {
        if (typeof speechSynthesis === 'undefined') {
          resolve();
          return;
        }

        speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = speed;
        utterance.onend = () => {
          if (mountedRef.current) setIsSpeaking(false);
          resolve();
        };
        utterance.onerror = () => {
          if (mountedRef.current) setIsSpeaking(false);
          resolve();
        };

        setIsSpeaking(true);
        speechSynthesis.speak(utterance);
      });
    },
    [speed]
  );

  const speakCloud = useCallback(
    async (text: string): Promise<void> => {
      try {
        const response = await api.generateTTS(
          { text, voice, speed, format: 'mp3' },
          userId
        );

        if (!response.success || !response.data) {
          await speakBrowser(text);
          return;
        }

        const data = response.data;

        if (data.use_browser_tts) {
          await speakBrowser(text);
          return;
        }

        const audioBase64 = data.audio_base64;
        if (!audioBase64) {
          await speakBrowser(text);
          return;
        }

        // Play cloud-generated audio
        const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
        audioRef.current = audio;
        if (mountedRef.current) setIsSpeaking(true);

        audio.onended = () => {
          if (mountedRef.current) setIsSpeaking(false);
          audioRef.current = null;
        };
        audio.onerror = () => {
          if (mountedRef.current) setIsSpeaking(false);
          audioRef.current = null;
        };

        await audio.play();
      } catch {
        // Fall back to browser TTS
        await speakBrowser(text);
      }
    },
    [voice, speed, userId, speakBrowser]
  );

  const speak = useCallback(
    async (text: string) => {
      if (!text) return;

      if (preferCloud) {
        await speakCloud(text);
      } else {
        await speakBrowser(text);
      }
    },
    [preferCloud, speakCloud, speakBrowser]
  );

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (typeof speechSynthesis !== 'undefined') {
      speechSynthesis.cancel();
    }
    setIsSpeaking(false);
  }, []);

  return {
    isSupported,
    isSpeaking,
    speak,
    stop,
  };
}
