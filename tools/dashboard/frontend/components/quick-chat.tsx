'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { ArrowUp, Paperclip, Loader2, X, Maximize2, Minimize2, MessageSquare, Eye, EyeOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import { api, streamChatMessage, type ChatStreamChunk } from '@/lib/api';
import { ChatHistory, ChatMessage, ChatControl } from './chat-history';
import { VoiceInput } from './voice/voice-input';
import { TranscriptDisplay } from './voice/transcript-display';

interface QuickChatProps {
  onSendMessage?: (message: string) => void;
  onStateChange?: (state: 'idle' | 'thinking' | 'working') => void;
  isProcessing?: boolean;
  placeholder?: string;
  className?: string;
  showHistory?: boolean;
  conversationId?: string | null;
  onConversationChange?: (id: string) => void;
  userInitials?: string;
  isConnected?: boolean;
}

export function QuickChat({
  onSendMessage,
  onStateChange,
  isProcessing: externalIsProcessing = false,
  placeholder = 'Type a message...',
  className,
  showHistory = false,
  conversationId: externalConversationId = null,
  onConversationChange,
  userInitials = 'U',
  isConnected = false,
}: QuickChatProps) {
  const [message, setMessage] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(externalConversationId);
  const [isTyping, setIsTyping] = useState(false);
  const [typingContent, setTypingContent] = useState('');
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandPhase, setExpandPhase] = useState<'collapsed' | 'expanding' | 'expanded' | 'collapsing'>('collapsed');
  const [originRect, setOriginRect] = useState<DOMRect | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isMultiline, setIsMultiline] = useState(false);
  const [voiceResult, setVoiceResult] = useState<{ message: string; success: boolean } | null>(null);
  const [activeControl, setActiveControl] = useState<ChatControl | null>(null);
  const [controlInputValue, setControlInputValue] = useState('');
  const [showControlPassword, setShowControlPassword] = useState(false);
  const controlInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const voiceResultTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const toggleExpand = useCallback(() => {
    if (expandPhase === 'collapsed') {
      // Capture current position and start expanding
      const rect = containerRef.current?.getBoundingClientRect();
      if (rect) setOriginRect(rect);
      setIsExpanded(true);
      setExpandPhase('expanding');
      // Animate to full screen on next frame
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setExpandPhase('expanded');
        });
      });
    } else if (expandPhase === 'expanded') {
      // Capture origin rect again in case layout changed
      setExpandPhase('collapsing');
      // Wait for animation to finish, then unmount portal
      setTimeout(() => {
        setIsExpanded(false);
        setExpandPhase('collapsed');
      }, 300);
    }
  }, [expandPhase]);

  // Streaming text reveal buffer
  const streamBufferRef = useRef('');
  const streamDisplayedRef = useRef(0);
  const streamRafRef = useRef<number>();

  const startStreamReveal = useCallback(() => {
    const reveal = () => {
      const buffer = streamBufferRef.current;
      const displayed = streamDisplayedRef.current;
      if (displayed < buffer.length) {
        // Reveal 2-4 characters per frame for a natural typing feel
        const charsPerFrame = Math.min(3, buffer.length - displayed);
        streamDisplayedRef.current = displayed + charsPerFrame;
        setTypingContent(buffer.slice(0, streamDisplayedRef.current));
        streamRafRef.current = requestAnimationFrame(reveal);
      }
    };
    if (!streamRafRef.current) {
      streamRafRef.current = requestAnimationFrame(reveal);
    }
  }, []);

  const stopStreamReveal = useCallback(() => {
    if (streamRafRef.current) {
      cancelAnimationFrame(streamRafRef.current);
      streamRafRef.current = undefined;
    }
    // Flush remaining content
    setTypingContent(streamBufferRef.current);
    streamBufferRef.current = '';
    streamDisplayedRef.current = 0;
  }, []);

  const appendToStreamBuffer = useCallback((content: string) => {
    streamBufferRef.current += content;
    startStreamReveal();
  }, [startStreamReveal]);

  // Recalculate textarea height after layout changes (icons move between inline/toolbar)
  useEffect(() => {
    if (inputRef.current) {
      const el = inputRef.current;
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    }
  }, [isMultiline]);

  // Load conversation history when conversationId changes (but not during active streaming)
  useEffect(() => {
    if (conversationId && showHistory && !isProcessing) {
      loadHistory(conversationId);
    }
  }, [conversationId, showHistory]);

  // Sync with external conversation ID
  useEffect(() => {
    if (externalConversationId !== conversationId) {
      setConversationId(externalConversationId);
    }
  }, [externalConversationId]);

  // Auto-trigger setup/greeting on mount.
  // The backend checks args/user.yaml fields directly to decide whether to
  // run the onboarding flow or emit a personalised greeting.
  const setupCheckedRef = useRef(false);
  useEffect(() => {
    if (setupCheckedRef.current) return;
    setupCheckedRef.current = true;
    sendMessage('__setup_init__', true);
  }, []);

  const loadHistory = async (convId: string) => {
    setIsLoadingHistory(true);
    try {
      const response = await api.getChatHistory(convId);
      if (response.success && response.data) {
        setMessages(response.data.messages);
      }
    } catch (e) {
      console.error('Failed to load chat history:', e);
    }
    setIsLoadingHistory(false);
  };

  // Focus control input and set default value when a new control appears
  useEffect(() => {
    if (activeControl) {
      setControlInputValue(activeControl.default_value || '');
      setShowControlPassword(false);
      setTimeout(() => controlInputRef.current?.focus(), 100);
    }
  }, [activeControl]);

  // Core message-sending logic. When silent=true, no user bubble is shown (used for auto-trigger).
  const sendMessage = async (text: string, silent = false) => {
    setError(null);
    setIsProcessing(true);
    onStateChange?.('thinking');

    if (!silent) {
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, userMessage]);
      onSendMessage?.(text);
    }

    setIsTyping(true);
    setTypingContent('');
    streamBufferRef.current = '';
    streamDisplayedRef.current = 0;

    try {
      let fullContent = '';
      let metadata: Partial<ChatStreamChunk> = {};
      let nextControl: ChatControl | null = null;

      for await (const chunk of streamChatMessage(text, conversationId || undefined)) {
        if (chunk.type === 'chunk') {
          fullContent += chunk.content || '';
          appendToStreamBuffer(chunk.content || '');

          if (chunk.conversation_id && chunk.conversation_id !== conversationId) {
            setConversationId(chunk.conversation_id);
            onConversationChange?.(chunk.conversation_id);
          }
        } else if (chunk.type === 'control') {
          if (chunk.control_id && chunk.field && chunk.control_type) {
            nextControl = {
              control_type: chunk.control_type,
              control_id: chunk.control_id,
              label: chunk.label,
              field: chunk.field,
              options: chunk.options,
              default_value: chunk.default_value,
              placeholder: chunk.placeholder,
              required: chunk.required,
              validation: chunk.validation,
            };
          }
          if (chunk.conversation_id && chunk.conversation_id !== conversationId) {
            setConversationId(chunk.conversation_id);
            onConversationChange?.(chunk.conversation_id);
          }
        } else if (chunk.type === 'done') {
          metadata = chunk;
          if (chunk.conversation_id && chunk.conversation_id !== conversationId) {
            setConversationId(chunk.conversation_id);
            onConversationChange?.(chunk.conversation_id);
          }
        } else if (chunk.type === 'error') {
          setError(chunk.error || 'Unknown error');
          if (!fullContent) {
            fullContent = chunk.error || 'An error occurred. Please try again.';
          }
        }
      }

      stopStreamReveal();
      setIsTyping(false);
      setTypingContent('');

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: fullContent || 'No response received.',
        model: metadata.model,
        complexity: metadata.complexity,
        cost_usd: metadata.cost_usd,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMessage]);

      if (nextControl) {
        setActiveControl(nextControl);
      }

    } catch (e) {
      const errorText = e instanceof Error ? e.message : 'Failed to send message';
      setError(errorText);

      stopStreamReveal();
      setIsTyping(false);
      setTypingContent('');

      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `Error: ${errorText}`,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMessage]);
    }

    setIsProcessing(false);
    onStateChange?.('idle');
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage || isProcessing || externalIsProcessing) return;

    setMessage('');
    setIsMultiline(false);
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }

    await sendMessage(trimmedMessage);
  };

  const clearConversation = () => {
    setMessages([]);
    setConversationId(null);
    setError(null);
    setActiveControl(null);
    setControlInputValue('');
    onConversationChange?.('');
  };

  const handleControlSubmit = useCallback(async (controlId: string, field: string, value: string) => {
    setActiveControl(null);
    setControlInputValue('');
    setIsProcessing(true);
    onStateChange?.('thinking');
    setIsTyping(true);
    setTypingContent('');
    streamBufferRef.current = '';
    streamDisplayedRef.current = 0;

    try {
      let fullContent = '';
      let metadata: Partial<ChatStreamChunk> = {};
      let nextControl: ChatControl | null = null;

      for await (const chunk of streamChatMessage(
        '__control_response__',
        conversationId || undefined,
        { control_id: controlId, field, value }
      )) {
        if (chunk.type === 'chunk') {
          fullContent += chunk.content || '';
          appendToStreamBuffer(chunk.content || '');
          if (chunk.conversation_id && chunk.conversation_id !== conversationId) {
            setConversationId(chunk.conversation_id);
            onConversationChange?.(chunk.conversation_id);
          }
        } else if (chunk.type === 'control') {
          if (chunk.control_id && chunk.field && chunk.control_type) {
            nextControl = {
              control_type: chunk.control_type,
              control_id: chunk.control_id,
              label: chunk.label,
              field: chunk.field,
              options: chunk.options,
              default_value: chunk.default_value,
              placeholder: chunk.placeholder,
              required: chunk.required,
              validation: chunk.validation,
            };
          }
          if (chunk.conversation_id && chunk.conversation_id !== conversationId) {
            setConversationId(chunk.conversation_id);
            onConversationChange?.(chunk.conversation_id);
          }
        } else if (chunk.type === 'done') {
          metadata = chunk;
          if (chunk.conversation_id && chunk.conversation_id !== conversationId) {
            setConversationId(chunk.conversation_id);
            onConversationChange?.(chunk.conversation_id);
          }
        } else if (chunk.type === 'error') {
          setError(chunk.error || 'Unknown error');
          if (!fullContent) fullContent = chunk.error || 'An error occurred.';
        }
      }

      stopStreamReveal();
      setIsTyping(false);
      setTypingContent('');

      if (fullContent) {
        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: fullContent,
          model: metadata.model,
          complexity: metadata.complexity,
          cost_usd: metadata.cost_usd,
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, assistantMessage]);
      }

      if (nextControl) {
        setActiveControl(nextControl);
      }
    } catch (e) {
      stopStreamReveal();
      setIsTyping(false);
      setTypingContent('');
      setError(e instanceof Error ? e.message : 'Failed to submit control response');
    }

    setIsProcessing(false);
    onStateChange?.('idle');
    setTimeout(() => inputRef.current?.focus(), 0);
  }, [conversationId, onStateChange, onConversationChange]);

  // Submit the active control value
  const submitActiveControl = useCallback((value: string) => {
    if (!activeControl || !value.trim()) return;
    const { control_id, field } = activeControl;
    handleControlSubmit(control_id, field, value.trim());
  }, [activeControl, handleControlSubmit]);

  // Keyboard shortcut: Cmd/Ctrl + K to focus
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  const processing = isProcessing || externalIsProcessing;

  // Compute animated styles for expand/collapse
  const getExpandStyle = (): React.CSSProperties => {
    if (!isExpanded) return {};
    if (expandPhase === 'expanding' && originRect) {
      // Start at the card's position
      return {
        position: 'fixed',
        top: originRect.top,
        left: originRect.left,
        width: originRect.width,
        height: originRect.height,
        zIndex: 9999,
        transition: 'all 300ms cubic-bezier(0.4, 0, 0.2, 1)',
      };
    }
    if (expandPhase === 'expanded') {
      // Animate to full screen
      return {
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 9999,
        transition: 'all 300ms cubic-bezier(0.4, 0, 0.2, 1)',
      };
    }
    if (expandPhase === 'collapsing' && originRect) {
      // Animate back to card position
      return {
        position: 'fixed',
        top: originRect.top,
        left: originRect.left,
        width: originRect.width,
        height: originRect.height,
        zIndex: 9999,
        transition: 'all 300ms cubic-bezier(0.4, 0, 0.2, 1)',
      };
    }
    return {
      position: 'fixed',
      inset: 0,
      zIndex: 9999,
    };
  };

  const chatContent = (
    <div
      ref={!isExpanded ? containerRef : undefined}
      className={cn(
        'flex flex-col h-full',
        isExpanded ? 'bg-black' : '',
        !isExpanded && className
      )}
      style={isExpanded ? getExpandStyle() : undefined}
    >
      {/* Chat Header — always rendered, expands with the panel */}
      <div className={cn(
        'flex-shrink-0 border-b border-white/[0.04] px-5 py-4'
      )}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="text-white/40"><MessageSquare className="w-5 h-5" /></div>
            <h3 className="font-medium text-white/90">Direct Chat</h3>
          </div>
          <div className="flex items-center gap-2 text-sm text-white/40">
            <div
              className={cn(
                'w-1.5 h-1.5 rounded-full',
                isConnected ? 'bg-emerald-400' : 'bg-red-400'
              )}
            />
            {isConnected ? 'Active' : 'Offline'}
          </div>
        </div>
      </div>

      {/* Chat content area with padding */}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden p-4">

      {/* Chat History (when enabled) */}
      {showHistory && (
        <div
          className={cn(
            'flex-1 transition-all duration-300 overflow-hidden',
            messages.length > 0 || isTyping ? '' : ''
          )}
        >
          <ChatHistory
            messages={messages}
            isLoading={isLoadingHistory}
            isTyping={isTyping}
            typingContent={typingContent}
            onControlSubmit={handleControlSubmit}
            userInitials={userInitials}
            className="h-full p-2"
          />
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="px-6 py-2 bg-red-500/10 border-t border-red-500/20 flex items-center justify-between">
          <span className="text-xs text-red-400">{error}</span>
          <button
            onClick={() => setError(null)}
            className="p-1 hover:bg-red-500/20 rounded"
          >
            <X className="w-3 h-3 text-red-400" />
          </button>
        </div>
      )}

      {/* Voice Result Banner */}
      {voiceResult && (
        <div className={cn(
          'px-4 py-2 border-t flex items-center justify-between text-xs',
          voiceResult.success
            ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
            : 'bg-amber-500/10 border-amber-500/20 text-amber-400'
        )}>
          <span>{voiceResult.message}</span>
          <button
            onClick={() => setVoiceResult(null)}
            className="p-0.5 hover:bg-white/10 rounded"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* Input Area — shows either a setup control or the normal chat input */}
      <div className="flex-shrink-0 border-t border-white/[0.04] pt-3">

      {/* Setup Control (select / secure_input) — replaces the normal input while active */}
      {activeControl && !processing && (
        <div
          className={cn(
            'rounded-2xl transition-all duration-200 border',
            'bg-white/[0.02] border-white/[0.06]'
          )}
        >
          <div className="px-4 py-3">
            {activeControl.control_type === 'select' ? (
              /* Select options as buttons + "Other" */
              <div className="flex flex-wrap gap-2">
                {activeControl.options?.map(option => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => submitActiveControl(option.value)}
                    className={cn(
                      'px-3 py-2 rounded-xl text-sm transition-all text-left',
                      'bg-white/[0.04] border border-white/[0.08] text-white/70',
                      'hover:bg-white/[0.08] hover:border-white/15 hover:text-white/90'
                    )}
                  >
                    <div>{option.label}</div>
                    {option.description && (
                      <div className="text-[11px] text-white/30 mt-0.5">{option.description}</div>
                    )}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => {
                    setActiveControl(null);
                    setTimeout(() => inputRef.current?.focus(), 100);
                  }}
                  className={cn(
                    'px-3 py-2 rounded-xl text-sm transition-all',
                    'bg-white/[0.04] border border-dashed border-white/[0.12] text-white/50',
                    'hover:bg-white/[0.08] hover:border-white/20 hover:text-white/70'
                  )}
                >
                  Other
                </button>
              </div>
            ) : (
              /* Secure input (API key) */
              <div className="flex items-center gap-3">
                <div className="relative flex-1">
                  <input
                    ref={controlInputRef}
                    type={!showControlPassword ? 'password' : 'text'}
                    value={controlInputValue}
                    onChange={(e) => setControlInputValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        submitActiveControl(controlInputValue);
                      }
                    }}
                    placeholder={activeControl.placeholder || ''}
                    className="w-full bg-transparent outline-none text-white placeholder-white/30 min-h-[24px] leading-6 font-mono pr-8"
                  />
                  <button
                    type="button"
                    onClick={() => setShowControlPassword(!showControlPassword)}
                    className="absolute right-0 top-1/2 -translate-y-1/2 p-1 text-white/30 hover:text-white/50 transition-colors"
                  >
                    {showControlPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => submitActiveControl(controlInputValue)}
                  disabled={!controlInputValue.trim()}
                  className={cn(
                    'w-8 h-8 rounded-full transition-all duration-200',
                    'flex items-center justify-center',
                    controlInputValue.trim()
                      ? 'bg-white text-black hover:bg-white/90'
                      : 'bg-white/10 text-white/20 cursor-not-allowed'
                  )}
                >
                  <ArrowUp className="w-5 h-5" />
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Normal chat input — hidden while a control is active */}
      {(!activeControl || processing) && (
        <form onSubmit={handleSubmit}>
          <div
            className={cn(
              'rounded-2xl transition-all duration-200',
              'border',
              isFocused
                ? 'bg-white/[0.06] border-transparent'
                : 'bg-white/[0.02] border-white/[0.06]'
            )}
            onClick={() => inputRef.current?.focus()}
          >
            {/* Input row */}
            <div className="flex items-center gap-3 px-4 py-3">
              {/* Expand/collapse - left side, collapses when multiline */}
              {showHistory && (
                <div className={cn(
                  'flex-shrink-0 overflow-hidden transition-opacity duration-200',
                  isMultiline ? 'w-0 opacity-0' : 'w-7 opacity-100'
                )}>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleExpand();
                    }}
                    className="w-7 h-7 flex items-center justify-center text-white/30 hover:text-white/60 transition-colors rounded-lg"
                    title={isExpanded ? 'Collapse' : 'Expand'}
                  >
                    {isExpanded ? (
                      <Minimize2 className="w-5 h-5" />
                    ) : (
                      <Maximize2 className="w-5 h-5" />
                    )}
                  </button>
                </div>
              )}

              <textarea
                ref={inputRef}
                value={message}
                onChange={(e) => {
                  const val = e.target.value;
                  setMessage(val);
                  const el = e.target;
                  el.style.height = 'auto';
                  const scrollH = el.scrollHeight;
                  el.style.height = Math.min(scrollH, 160) + 'px';
                  const shouldBeMultiline = scrollH > 32;
                  requestAnimationFrame(() => {
                    if (shouldBeMultiline) setIsMultiline(true);
                    if (!val) setIsMultiline(false);
                  });
                }}
                onFocus={() => setIsFocused(true)}
                onBlur={() => setIsFocused(false)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (message.trim() && !processing) {
                      handleSubmit(e as unknown as React.FormEvent);
                    }
                  }
                }}
                placeholder={placeholder}
                disabled={processing}
                rows={1}
                className={cn(
                  'flex-1 bg-transparent outline-none focus-visible:outline-none resize-none p-0',
                  'text-white placeholder-white/30',
                  'disabled:opacity-50',
                  'max-h-40 overflow-y-auto',
                  'scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent',
                  'min-h-[24px] leading-6'
                )}
              />

              {/* Inline icons — collapse instantly, fade opacity */}
              <div className={cn(
                'flex items-center gap-1 flex-shrink-0 overflow-hidden transition-opacity duration-200',
                isMultiline ? 'w-0 opacity-0' : 'opacity-100'
              )}>
                <button
                  type="button"
                  disabled
                  onClick={(e) => e.stopPropagation()}
                  className="w-8 h-8 flex items-center justify-center text-white/20 hover:text-white/40 transition-colors disabled:cursor-not-allowed disabled:opacity-50 rounded-lg"
                  title="Attachments coming soon"
                >
                  <Paperclip className="w-5 h-5" />
                </button>

                <VoiceInput
                  chatMode={false}
                  className="h-8 flex items-center"
                  onTranscript={(text) => {
                    setMessage(text);
                    inputRef.current?.focus();
                  }}
                  onCommandResult={(result) => {
                    setVoiceResult({ message: result.message, success: result.success });
                    if (voiceResultTimeoutRef.current) clearTimeout(voiceResultTimeoutRef.current);
                    voiceResultTimeoutRef.current = setTimeout(() => setVoiceResult(null), 4000);
                  }}
                />

                <button
                  type="submit"
                  disabled={!message.trim() || processing}
                  onClick={(e) => e.stopPropagation()}
                  className={cn(
                    'w-8 h-8 rounded-full transition-all duration-200',
                    'flex items-center justify-center ml-1',
                    message.trim() && !processing
                      ? 'bg-white text-black hover:bg-white/90'
                      : 'bg-white/10 text-white/20 cursor-not-allowed'
                  )}
                >
                  {processing ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <ArrowUp className="w-5 h-5" />
                  )}
                </button>
              </div>
            </div>

            {/* Toolbar row — slides in when multiline */}
            <div className={cn(
              'overflow-hidden transition-all duration-200',
              isMultiline
                ? 'max-h-12 opacity-100 pb-2'
                : 'max-h-0 opacity-0'
            )}>
              <div className="flex items-center justify-between px-3 pt-1">
                {/* Left side - expand + clear */}
                <div className="flex items-center gap-1">
                  {showHistory && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleExpand();
                      }}
                      className="w-8 h-8 flex items-center justify-center text-white/30 hover:text-white/60 transition-colors rounded-lg"
                      title={isExpanded ? 'Collapse' : 'Expand'}
                    >
                      {isExpanded ? (
                        <Minimize2 className="w-5 h-5" />
                      ) : (
                        <Maximize2 className="w-5 h-5" />
                      )}
                    </button>
                  )}
                  {messages.length > 0 && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        clearConversation();
                      }}
                      className="w-8 h-8 flex items-center justify-center text-white/20 hover:text-white/40 transition-colors rounded-lg"
                      title="Clear conversation"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  )}
                </div>

                {/* Right side - attachments, voice, send */}
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    disabled
                    onClick={(e) => e.stopPropagation()}
                    className="w-8 h-8 flex items-center justify-center text-white/20 hover:text-white/40 transition-colors disabled:cursor-not-allowed disabled:opacity-50 rounded-lg"
                    title="Attachments coming soon"
                  >
                    <Paperclip className="w-5 h-5" />
                  </button>

                  <VoiceInput
                    chatMode={false}
                    className="h-8 flex items-center"
                    onTranscript={(text) => {
                      setMessage(text);
                      inputRef.current?.focus();
                    }}
                    onCommandResult={(result) => {
                      setVoiceResult({ message: result.message, success: result.success });
                      if (voiceResultTimeoutRef.current) clearTimeout(voiceResultTimeoutRef.current);
                      voiceResultTimeoutRef.current = setTimeout(() => setVoiceResult(null), 4000);
                    }}
                  />

                  <button
                    type="submit"
                    disabled={!message.trim() || processing}
                    onClick={(e) => e.stopPropagation()}
                    className={cn(
                      'w-8 h-8 rounded-full transition-all duration-200',
                      'flex items-center justify-center ml-1',
                      message.trim() && !processing
                        ? 'bg-white text-black hover:bg-white/90'
                        : 'bg-white/10 text-white/20 cursor-not-allowed'
                    )}
                  >
                    {processing ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <ArrowUp className="w-5 h-5" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </form>
      )}
      </div>
      </div>
    </div>
  );

  // When expanded, render via portal to escape all parent containers
  // Keep a placeholder in the original position so the card doesn't collapse
  if (isExpanded && typeof document !== 'undefined') {
    return (
      <>
        <div ref={containerRef} className={cn('flex flex-col h-full', className)} />
        {createPortal(chatContent, document.body)}
      </>
    );
  }

  return chatContent;
}
