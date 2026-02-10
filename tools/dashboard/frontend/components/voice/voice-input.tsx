'use client';

import { useState, useEffect, useRef } from 'react';
import { api, type VoiceCommandResponse, type VoicePreferences } from '@/lib/api';
import { useVoiceRecognition } from './use-voice-recognition';
import { useAudioRecorder } from './use-audio-recorder';
import { useTTS } from './use-tts';
import { useAudioFeedback } from './use-audio-feedback';
import { VoiceButton, type VoiceButtonState } from './voice-button';
import { TranscriptDisplay } from './transcript-display';

interface VoiceInputProps {
  onTranscript?: (text: string) => void;
  onCommandResult?: (result: VoiceCommandResponse) => void;
  className?: string;
  userId?: string;
  /** If true, insert text into chat instead of executing commands */
  chatMode?: boolean;
}

export function VoiceInput({
  onTranscript,
  onCommandResult,
  className,
  userId = 'default',
  chatMode = false,
}: VoiceInputProps) {
  // -- Preferences (loaded on mount) --
  const [prefs, setPrefs] = useState({
    source: 'web_speech',
    ttsEnabled: false,
    ttsVoice: 'alloy',
    ttsSpeed: 1.0,
    audioFeedback: true,
    continuousListening: false,
  });

  const [isProcessingCommand, setIsProcessingCommand] = useState(false);
  const [commandResult, setCommandResult] = useState<VoiceCommandResponse | null>(null);
  const [detectedIntent, setDetectedIntent] = useState<string | undefined>();

  // Whisper mode stores transcript/confidence from API response
  const [whisperTranscript, setWhisperTranscript] = useState('');
  const [whisperConfidence, setWhisperConfidence] = useState(0);

  const resultTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const autoRestartTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const shouldContinueRef = useRef(false);
  // Ref to always access latest handlers from the keyboard shortcut effect
  const handlersRef = useRef({ start: () => {}, stop: () => {} });

  // -- Load preferences --
  useEffect(() => {
    api
      .getVoicePreferences(userId)
      .then((res) => {
        if (res.success && res.data) {
          const raw = res.data as unknown as { data?: VoicePreferences };
          const p = raw.data ?? res.data;
          setPrefs({
            source: p.preferred_source || 'web_speech',
            ttsEnabled: p.tts_enabled || false,
            ttsVoice: p.tts_voice || 'alloy',
            ttsSpeed: p.tts_speed || 1.0,
            audioFeedback: p.audio_feedback_enabled ?? true,
            continuousListening: p.continuous_listening || false,
          });
        }
      })
      .catch(() => {});
  }, [userId]);

  // -- Hooks --
  const recognition = useVoiceRecognition({
    continuous: prefs.continuousListening,
    onResult: handleWebSpeechResult,
    onEnd: handleRecognitionEnd,
  });

  const recorder = useAudioRecorder();

  const tts = useTTS({
    preferCloud: prefs.ttsEnabled,
    voice: prefs.ttsVoice,
    speed: prefs.ttsSpeed,
    userId,
  });

  const { playTone } = useAudioFeedback(prefs.audioFeedback);

  const isWhisper = prefs.source === 'whisper_api';
  const isActive = isWhisper ? recorder.isRecording : recognition.isListening;

  // -- Result auto-clear --
  useEffect(() => {
    if (commandResult) {
      resultTimeoutRef.current = setTimeout(() => {
        setCommandResult(null);
        setDetectedIntent(undefined);
      }, 4000);

      return () => {
        if (resultTimeoutRef.current) clearTimeout(resultTimeoutRef.current);
      };
    }
  }, [commandResult]);

  // -- Cleanup on unmount --
  useEffect(() => {
    return () => {
      shouldContinueRef.current = false;
      if (resultTimeoutRef.current) clearTimeout(resultTimeoutRef.current);
      if (autoRestartTimeoutRef.current) clearTimeout(autoRestartTimeoutRef.current);
    };
  }, []);

  // -- V key shortcut (uses ref to always access latest handlers) --
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (
        e.key === 'v' &&
        !e.metaKey &&
        !e.ctrlKey &&
        !e.altKey &&
        !['INPUT', 'TEXTAREA', 'SELECT'].includes(
          (e.target as HTMLElement)?.tagName
        )
      ) {
        e.preventDefault();
        if (isActive) {
          handlersRef.current.stop();
        } else {
          handlersRef.current.start();
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isActive]);

  // -- Handlers --

  function handleWebSpeechResult(text: string, conf: number, isFinal: boolean) {
    if (!isFinal) return;

    if (chatMode) {
      onTranscript?.(text);
      playTone('success');
      return;
    }

    executeCommand(text, conf, 'web_speech');
  }

  function handleRecognitionEnd() {
    if (shouldContinueRef.current && prefs.continuousListening && !isWhisper) {
      // Auto-restart for continuous mode
      setTimeout(() => {
        if (shouldContinueRef.current) {
          recognition.startListening();
        }
      }, 300);
    }
  }

  async function executeCommand(text: string, conf: number, src: string) {
    setIsProcessingCommand(true);
    setCommandResult(null);

    try {
      const response = await api.sendVoiceCommand(
        {
          transcript: text,
          confidence: conf,
          source: src,
          alternatives: !isWhisper ? recognition.alternatives : [],
        },
        userId
      );

      if (response.success && response.data) {
        const result = response.data;
        setCommandResult(result);
        setDetectedIntent(result.parsed?.intent);
        onCommandResult?.(result);

        playTone(result.success ? 'success' : 'error');

        // Speak result via TTS if enabled
        if (prefs.ttsEnabled && result.message) {
          tts.speak(result.message);
        }

        // Keep confirmation visible longer
        if (result.data?.requires_confirmation) {
          if (resultTimeoutRef.current) clearTimeout(resultTimeoutRef.current);
        }
      } else {
        setCommandResult({
          success: false,
          message: response.error || 'Failed to process command',
          intent: 'unknown',
          data: {},
          undo_available: false,
          parsed: {
            intent: 'unknown',
            confidence: 0,
            entities: [],
            requires_confirmation: false,
          },
        });
        playTone('error');
      }
    } catch {
      setCommandResult({
        success: false,
        message: 'Connection error. Try again?',
        intent: 'unknown',
        data: {},
        undo_available: false,
        parsed: {
          intent: 'unknown',
          confidence: 0,
          entities: [],
          requires_confirmation: false,
        },
      });
      playTone('error');
    }

    setIsProcessingCommand(false);

    // Continuous mode auto-restart for whisper
    if (shouldContinueRef.current && prefs.continuousListening && isWhisper) {
      autoRestartTimeoutRef.current = setTimeout(() => {
        if (shouldContinueRef.current) {
          recorder.startRecording();
          playTone('start');
        }
      }, 500);
    }
  }

  async function handleWhisperStop() {
    playTone('stop');
    const blob = await recorder.stopRecording();
    if (!blob) return;

    setIsProcessingCommand(true);

    try {
      const res = await api.transcribeAudio(blob, 'whisper_api', undefined, userId);
      if (res.success && res.data) {
        const { transcript: t, confidence: c } = res.data;
        setWhisperTranscript(t);
        setWhisperConfidence(c);

        if (chatMode) {
          onTranscript?.(t);
          playTone('success');
          setIsProcessingCommand(false);
          return;
        }

        if (t) {
          await executeCommand(t, c, 'whisper_api');
          return;
        }
      }
    } catch {
      // Fall through to error handling
    }

    setIsProcessingCommand(false);
    playTone('error');
  }

  function handleStart() {
    setCommandResult(null);
    setDetectedIntent(undefined);
    setWhisperTranscript('');
    setWhisperConfidence(0);
    shouldContinueRef.current = true;

    // Cancel any pending auto-restart
    if (autoRestartTimeoutRef.current) clearTimeout(autoRestartTimeoutRef.current);

    playTone('start');

    if (isWhisper) {
      recorder.startRecording();
    } else {
      recognition.resetTranscript();
      recognition.startListening();
    }
  }

  function handleStop() {
    shouldContinueRef.current = false;

    // Cancel any pending auto-restart
    if (autoRestartTimeoutRef.current) clearTimeout(autoRestartTimeoutRef.current);

    if (isWhisper) {
      handleWhisperStop();
    } else {
      recognition.stopListening();
      playTone('stop');
    }
  }

  // Keep ref in sync so keyboard shortcut always uses latest handlers
  handlersRef.current.start = handleStart;
  handlersRef.current.stop = handleStop;

  function handleClick() {
    if (isProcessingCommand) return;
    if (isActive) {
      handleStop();
    } else {
      handleStart();
    }
  }

  // -- Render --
  const buttonState: VoiceButtonState =
    !(recognition.isSupported || recorder.isSupported)
      ? 'unsupported'
      : isProcessingCommand
        ? 'processing'
        : isActive
          ? 'listening'
          : 'idle';

  const displayTranscript = isWhisper ? whisperTranscript : recognition.transcript;
  const displayInterim = isWhisper ? '' : recognition.interimTranscript;
  const displayConfidence = isWhisper ? whisperConfidence : recognition.confidence;
  const displayError = isWhisper ? recorder.error : recognition.error;

  return (
    <div className={className}>
      <VoiceButton state={buttonState} onClick={handleClick} />

      <TranscriptDisplay
        transcript={displayTranscript}
        interimTranscript={displayInterim}
        confidence={displayConfidence}
        intent={detectedIntent}
        isListening={isActive}
        isProcessing={isProcessingCommand}
        error={displayError}
        resultMessage={commandResult?.message}
        resultSuccess={commandResult?.success}
      />
    </div>
  );
}
