'use client';

import { useState, useRef, useCallback, useEffect } from 'react';

interface SpeechRecognitionEvent {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent {
  error: string;
  message?: string;
}

interface SpeechRecognitionResult {
  isFinal: boolean;
  [index: number]: SpeechRecognitionAlternative;
  length: number;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResultList {
  [index: number]: SpeechRecognitionResult;
  length: number;
}

// Browser SpeechRecognition types
interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  onspeechstart: (() => void) | null;
  onspeechend: (() => void) | null;
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionInstance;
}

// Detect browser support
function getSpeechRecognition(): SpeechRecognitionConstructor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as SpeechRecognitionConstructor | null;
}

export interface UseVoiceRecognitionOptions {
  language?: string;
  continuous?: boolean;
  interimResults?: boolean;
  maxAlternatives?: number;
  onResult?: (transcript: string, confidence: number, isFinal: boolean) => void;
  onError?: (error: string) => void;
  onEnd?: () => void;
}

export interface UseVoiceRecognitionReturn {
  isSupported: boolean;
  isListening: boolean;
  transcript: string;
  interimTranscript: string;
  confidence: number;
  error: string | null;
  alternatives: string[];
  startListening: () => void;
  stopListening: () => void;
  resetTranscript: () => void;
}

export function useVoiceRecognition(
  options: UseVoiceRecognitionOptions = {}
): UseVoiceRecognitionReturn {
  const {
    language = 'en-US',
    continuous = false,
    interimResults = true,
    maxAlternatives = 3,
    onResult,
    onError,
    onEnd,
  } = options;

  // Defer browser check to useEffect to avoid SSR hydration mismatch
  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [confidence, setConfidence] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [alternatives, setAlternatives] = useState<string[]>([]);

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const startTimeRef = useRef<number>(0);

  // Check browser support after mount (avoids SSR hydration mismatch)
  useEffect(() => {
    setIsSupported(getSpeechRecognition() !== null);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }
    };
  }, []);

  const startListening = useCallback(() => {
    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      setError('Voice input is not supported in this browser. Try Chrome, Edge, or Safari.');
      onError?.('unsupported_browser');
      return;
    }

    // Reset state
    setError(null);
    setTranscript('');
    setInterimTranscript('');
    setConfidence(0);
    setAlternatives([]);

    // Create new instance
    const recognition = new SpeechRecognition();
    recognition.continuous = continuous;
    recognition.interimResults = interimResults;
    recognition.lang = language;
    recognition.maxAlternatives = maxAlternatives;

    recognition.onstart = () => {
      setIsListening(true);
      startTimeRef.current = Date.now();
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = '';
      let currentInterim = '';
      let bestConfidence = 0;
      const alts: string[] = [];

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const firstAlt = result[0];

        if (result.isFinal) {
          finalTranscript += firstAlt.transcript;
          bestConfidence = Math.max(bestConfidence, firstAlt.confidence);

          // Collect alternatives
          for (let j = 1; j < result.length; j++) {
            alts.push(result[j].transcript);
          }
        } else {
          currentInterim += firstAlt.transcript;
        }
      }

      if (finalTranscript) {
        setTranscript(finalTranscript);
        setConfidence(bestConfidence);
        setAlternatives(alts);
        setInterimTranscript('');
        onResult?.(finalTranscript, bestConfidence, true);
      }

      if (currentInterim) {
        setInterimTranscript(currentInterim);
        onResult?.(currentInterim, 0, false);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const errorMessages: Record<string, string> = {
        'no-speech': 'No speech detected. Try again?',
        'audio-capture': 'Microphone not found. Check your audio settings.',
        'not-allowed': 'Microphone permission denied. Please allow access.',
        'network': 'Network error. Check your connection.',
        'aborted': '',  // User cancelled, not an error
      };

      const message = errorMessages[event.error] || `Recognition error: ${event.error}`;
      if (message) {
        setError(message);
        onError?.(event.error);
      }
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
      onEnd?.();
    };

    try {
      recognition.start();
      recognitionRef.current = recognition;
    } catch (e) {
      setError('Failed to start voice recognition. Try again?');
      setIsListening(false);
    }
  }, [language, continuous, interimResults, maxAlternatives, onResult, onError, onEnd]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setIsListening(false);
  }, []);

  const resetTranscript = useCallback(() => {
    setTranscript('');
    setInterimTranscript('');
    setConfidence(0);
    setAlternatives([]);
    setError(null);
  }, []);

  return {
    isSupported,
    isListening,
    transcript,
    interimTranscript,
    confidence,
    error,
    alternatives,
    startListening,
    stopListening,
    resetTranscript,
  };
}
