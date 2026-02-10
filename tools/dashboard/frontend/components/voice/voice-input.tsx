'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { api, type VoiceCommandResponse } from '@/lib/api';
import { useVoiceRecognition } from './use-voice-recognition';
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
  const [isProcessingCommand, setIsProcessingCommand] = useState(false);
  const [commandResult, setCommandResult] = useState<VoiceCommandResponse | null>(null);
  const [detectedIntent, setDetectedIntent] = useState<string | undefined>();
  const resultTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const {
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
  } = useVoiceRecognition({
    onResult: handleRecognitionResult,
    onEnd: handleRecognitionEnd,
  });

  // Clear result message after delay
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

  // V key shortcut
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Only trigger on bare 'v' key, not in input fields
      if (
        e.key === 'v' &&
        !e.metaKey && !e.ctrlKey && !e.altKey &&
        !['INPUT', 'TEXTAREA', 'SELECT'].includes(
          (e.target as HTMLElement)?.tagName
        )
      ) {
        e.preventDefault();
        if (isListening) {
          stopListening();
        } else {
          handleStart();
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isListening, stopListening]);

  function handleRecognitionResult(text: string, conf: number, isFinal: boolean) {
    if (!isFinal) return;

    if (chatMode) {
      // In chat mode, just pass text to parent
      onTranscript?.(text);
      return;
    }

    // In command mode, send to voice API
    executeCommand(text, conf);
  }

  function handleRecognitionEnd() {
    // If we have a final transcript in command mode, it's already been sent
    // In chat mode, we're done
  }

  async function executeCommand(text: string, conf: number) {
    setIsProcessingCommand(true);
    setCommandResult(null);

    try {
      const response = await api.sendVoiceCommand(
        {
          transcript: text,
          confidence: conf,
          source: 'web_speech',
          alternatives,
        },
        userId
      );

      if (response.success && response.data) {
        const result = response.data;
        setCommandResult(result);
        setDetectedIntent(result.parsed?.intent);
        onCommandResult?.(result);

        // If the command needs confirmation, don't auto-clear
        if (result.data?.requires_confirmation) {
          // Keep the result visible longer
          if (resultTimeoutRef.current) clearTimeout(resultTimeoutRef.current);
        }
      } else {
        setCommandResult({
          success: false,
          message: response.error || 'Failed to process command',
          intent: 'unknown',
          data: {},
          undo_available: false,
          parsed: { intent: 'unknown', confidence: 0, entities: [], requires_confirmation: false },
        });
      }
    } catch (e) {
      setCommandResult({
        success: false,
        message: 'Connection error. Try again?',
        intent: 'unknown',
        data: {},
        undo_available: false,
        parsed: { intent: 'unknown', confidence: 0, entities: [], requires_confirmation: false },
      });
    }

    setIsProcessingCommand(false);
  }

  function handleStart() {
    setCommandResult(null);
    setDetectedIntent(undefined);
    resetTranscript();
    startListening();
  }

  function handleClick() {
    if (isListening) {
      stopListening();
    } else {
      handleStart();
    }
  }

  const buttonState: VoiceButtonState = !isSupported
    ? 'unsupported'
    : isProcessingCommand
    ? 'processing'
    : isListening
    ? 'listening'
    : 'idle';

  return (
    <div className={className}>
      <VoiceButton state={buttonState} onClick={handleClick} />

      <TranscriptDisplay
        transcript={transcript}
        interimTranscript={interimTranscript}
        confidence={confidence}
        intent={detectedIntent}
        isListening={isListening}
        isProcessing={isProcessingCommand}
        error={error}
        resultMessage={commandResult?.message}
        resultSuccess={commandResult?.success}
      />
    </div>
  );
}
