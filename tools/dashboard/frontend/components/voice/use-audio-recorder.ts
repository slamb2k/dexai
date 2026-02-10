'use client';

import { useState, useRef, useCallback, useEffect } from 'react';

export interface UseAudioRecorderReturn {
  isSupported: boolean;
  isRecording: boolean;
  error: string | null;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<Blob | null>;
}

/**
 * Hook for recording audio via MediaRecorder API (Phase 11b).
 *
 * Captures audio as WebM/Opus for server-side Whisper transcription.
 * Returns a Blob on stop that can be uploaded to /api/voice/transcribe.
 */
export function useAudioRecorder(): UseAudioRecorderReturn {
  const [isSupported] = useState(
    () =>
      typeof window !== 'undefined' &&
      typeof navigator?.mediaDevices?.getUserMedia === 'function' &&
      typeof MediaRecorder !== 'undefined'
  );
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const resolveRef = useRef<((blob: Blob | null) => void) | null>(null);

  // Cleanup on unmount: stop recording and release media stream
  useEffect(() => {
    return () => {
      const recorder = mediaRecorderRef.current;
      if (recorder && recorder.state !== 'inactive') {
        recorder.stop();
      }
    };
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Prefer webm/opus, fall back to whatever is available
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : '';

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());

        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        });

        resolveRef.current?.(blob);
        resolveRef.current = null;
      };

      recorder.onerror = () => {
        stream.getTracks().forEach((t) => t.stop());
        setError('Recording failed. Try again?');
        setIsRecording(false);
        resolveRef.current?.(null);
        resolveRef.current = null;
      };

      mediaRecorderRef.current = recorder;
      recorder.start(100); // 100ms chunks for responsiveness
      setIsRecording(true);
    } catch (e) {
      const msg =
        e instanceof DOMException && e.name === 'NotAllowedError'
          ? 'Microphone permission denied. Please allow access.'
          : 'Could not access microphone. Check your audio settings.';
      setError(msg);
    }
  }, []);

  const stopRecording = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === 'inactive') {
        resolve(null);
        return;
      }

      resolveRef.current = resolve;
      recorder.stop();
      mediaRecorderRef.current = null;
      setIsRecording(false);
    });
  }, []);

  return {
    isSupported,
    isRecording,
    error,
    startRecording,
    stopRecording,
  };
}
