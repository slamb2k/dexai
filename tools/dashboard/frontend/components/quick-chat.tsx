'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Paperclip, Loader2, X, Maximize2, Minimize2 } from 'lucide-react';
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
  const [error, setError] = useState<string | null>(null);
  const [voiceResult, setVoiceResult] = useState<{ message: string; success: boolean } | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const voiceResultTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  // Load conversation history when conversationId changes
  useEffect(() => {
    if (conversationId && showHistory) {
      loadHistory(conversationId);
    }
  }, [conversationId, showHistory]);

  // Sync with external conversation ID
  useEffect(() => {
    if (externalConversationId !== conversationId) {
      setConversationId(externalConversationId);
    }
  }, [externalConversationId]);

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage || isProcessing || externalIsProcessing) return;

    setError(null);
    setMessage('');
    // Reset textarea height after clearing
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
    setIsProcessing(true);
    onStateChange?.('thinking');

    // Add user message to local state immediately
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmedMessage,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMessage]);

    // Notify parent if provided
    onSendMessage?.(trimmedMessage);

    // Show typing indicator
    setIsTyping(true);
    setTypingContent('');

    try {
      // Use WebSocket streaming for progressive response display
      let fullContent = '';
      let metadata: Partial<ChatStreamChunk> = {};
      const pendingControls: ChatControl[] = [];

      for await (const chunk of streamChatMessage(trimmedMessage, conversationId || undefined)) {
        if (chunk.type === 'chunk') {
          // Accumulate content and update typing indicator
          fullContent += chunk.content || '';
          setTypingContent(fullContent);

          // Update conversation ID if provided
          if (chunk.conversation_id && chunk.conversation_id !== conversationId) {
            setConversationId(chunk.conversation_id);
            onConversationChange?.(chunk.conversation_id);
          }
        } else if (chunk.type === 'control') {
          // Accumulate control for attaching to the assistant message
          if (chunk.control_id && chunk.field && chunk.control_type) {
            pendingControls.push({
              control_type: chunk.control_type,
              control_id: chunk.control_id,
              label: chunk.label,
              field: chunk.field,
              options: chunk.options,
              default_value: chunk.default_value,
              placeholder: chunk.placeholder,
              required: chunk.required,
              validation: chunk.validation,
            });
          }
          // Update conversation ID if provided
          if (chunk.conversation_id && chunk.conversation_id !== conversationId) {
            setConversationId(chunk.conversation_id);
            onConversationChange?.(chunk.conversation_id);
          }
        } else if (chunk.type === 'done') {
          // Store metadata for the final message
          metadata = chunk;
          if (chunk.conversation_id && chunk.conversation_id !== conversationId) {
            setConversationId(chunk.conversation_id);
            onConversationChange?.(chunk.conversation_id);
          }
        } else if (chunk.type === 'error') {
          setError(chunk.error || 'Unknown error');
          // Still add what we have as the response
          if (!fullContent) {
            fullContent = chunk.error || 'An error occurred. Please try again.';
          }
        }
      }

      // Hide typing indicator
      setIsTyping(false);
      setTypingContent('');

      // Add assistant response with accumulated content and any controls
      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: fullContent || 'No response received.',
        model: metadata.model,
        complexity: metadata.complexity,
        cost_usd: metadata.cost_usd,
        controls: pendingControls.length > 0 ? pendingControls : undefined,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMessage]);

    } catch (e) {
      const errorText = e instanceof Error ? e.message : 'Failed to send message';
      setError(errorText);

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
    // Return focus to the input after sending
    inputRef.current?.focus();
  };

  const clearConversation = () => {
    setMessages([]);
    setConversationId(null);
    setError(null);
    onConversationChange?.('');
  };

  const handleControlSubmit = useCallback(async (controlId: string, field: string, value: string) => {
    // Mark the control as submitted in the message that contains it
    setMessages(prev => prev.map(msg => {
      if (!msg.controls?.some(c => c.control_id === controlId)) return msg;
      return {
        ...msg,
        control_values: { ...msg.control_values, [controlId]: value },
      };
    }));

    // Send the control response as a special message via the normal stream path
    setIsProcessing(true);
    onStateChange?.('thinking');
    setIsTyping(true);
    setTypingContent('');

    try {
      let fullContent = '';
      let metadata: Partial<ChatStreamChunk> = {};
      const pendingControls: ChatControl[] = [];

      for await (const chunk of streamChatMessage(
        '__control_response__',
        conversationId || undefined,
        { control_id: controlId, field, value }
      )) {
        if (chunk.type === 'chunk') {
          fullContent += chunk.content || '';
          setTypingContent(fullContent);
          if (chunk.conversation_id && chunk.conversation_id !== conversationId) {
            setConversationId(chunk.conversation_id);
            onConversationChange?.(chunk.conversation_id);
          }
        } else if (chunk.type === 'control') {
          if (chunk.control_id && chunk.field && chunk.control_type) {
            pendingControls.push({
              control_type: chunk.control_type,
              control_id: chunk.control_id,
              label: chunk.label,
              field: chunk.field,
              options: chunk.options,
              default_value: chunk.default_value,
              placeholder: chunk.placeholder,
              required: chunk.required,
              validation: chunk.validation,
            });
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
          controls: pendingControls.length > 0 ? pendingControls : undefined,
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, assistantMessage]);
      }
    } catch (e) {
      setIsTyping(false);
      setTypingContent('');
      setError(e instanceof Error ? e.message : 'Failed to submit control response');
    }

    setIsProcessing(false);
    onStateChange?.('idle');
  }, [conversationId, onStateChange, onConversationChange]);

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

  return (
    <div
      className={cn(
        'flex flex-col h-full transition-all duration-300',
        isExpanded && 'fixed inset-4 z-50 bg-black rounded-2xl border border-white/[0.06]',
        className
      )}
    >
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

      {/* Input Form - Design7 styling */}
      <div className="flex-shrink-0 border-t border-white/[0.04] pt-3">
        <form onSubmit={handleSubmit}>
          <div className="flex gap-3 items-end">
            {/* Input container - panel changes bg on focus, no border change */}
            <div
              className={cn(
                'flex-1 flex items-end gap-2',
                'rounded-xl px-4 py-3',
                'transition-all duration-200',
                isFocused
                  ? 'bg-white/[0.06]'
                  : 'bg-white/[0.02] border border-white/[0.06]'
              )}
              onClick={() => inputRef.current?.focus()}
            >
              <textarea
                ref={inputRef}
                value={message}
                onChange={(e) => {
                  setMessage(e.target.value);
                  // Auto-resize textarea
                  const el = e.target;
                  el.style.height = 'auto';
                  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
                }}
                onFocus={() => setIsFocused(true)}
                onBlur={() => setIsFocused(false)}
                onKeyDown={(e) => {
                  // Submit on Enter (without Shift)
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
                  'flex-1 bg-transparent outline-none resize-none',
                  'text-white placeholder-white/20',
                  'disabled:opacity-50',
                  'max-h-40 overflow-y-auto',
                  'scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent',
                  'min-h-[24px] leading-6'
                )}
              />

              {/* Action buttons - aligned to bottom */}
              <div className="flex items-center gap-1 flex-shrink-0 pb-0.5">
                {/* Clear button (when there are messages) */}
                {messages.length > 0 && (
                  <button
                    type="button"
                    onClick={clearConversation}
                    className="text-white/20 hover:text-white/40 transition-colors p-1"
                    title="Clear conversation"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}

                {/* Expand/collapse (when showing history) */}
                {showHistory && (
                  <button
                    type="button"
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="text-white/20 hover:text-white/40 transition-colors p-1"
                    title={isExpanded ? 'Collapse' : 'Expand'}
                  >
                    {isExpanded ? (
                      <Minimize2 className="w-4 h-4" />
                    ) : (
                      <Maximize2 className="w-4 h-4" />
                    )}
                  </button>
                )}

                {/* Attachment button */}
                <button
                  type="button"
                  disabled
                  className="text-white/20 hover:text-white/40 transition-colors disabled:cursor-not-allowed disabled:opacity-50 p-1"
                  title="Attachments coming soon"
                >
                  <Paperclip className="w-4 h-4" />
                </button>

                {/* Voice input */}
                <VoiceInput
                  chatMode={false}
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
              </div>
            </div>

            {/* Send button - Design7 style */}
            <button
              type="submit"
              disabled={!message.trim() || processing}
              className={cn(
                'px-6 py-3 rounded-xl transition-all duration-200',
                'flex items-center justify-center self-end',
                message.trim() && !processing
                  ? 'bg-white/10 hover:bg-white/15'
                  : 'bg-white/[0.02] border border-white/[0.04] cursor-not-allowed'
              )}
            >
              {processing ? (
                <Loader2 className="w-5 h-5 text-white/40 animate-spin" />
              ) : (
                <Send className={cn(
                  'w-5 h-5 transition-colors',
                  message.trim() ? 'text-white/70' : 'text-white/20'
                )} />
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
