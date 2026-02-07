'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Paperclip, Mic, Loader2, X, Maximize2, Minimize2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { ChatHistory, ChatMessage } from './chat-history';

interface QuickChatProps {
  onSendMessage?: (message: string) => void;
  onStateChange?: (state: 'idle' | 'thinking' | 'working') => void;
  isProcessing?: boolean;
  placeholder?: string;
  className?: string;
  showHistory?: boolean;
  conversationId?: string | null;
  onConversationChange?: (id: string) => void;
}

export function QuickChat({
  onSendMessage,
  onStateChange,
  isProcessing: externalIsProcessing = false,
  placeholder = 'Ask Dex anything...',
  className,
  showHistory = false,
  conversationId: externalConversationId = null,
  onConversationChange,
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
  const inputRef = useRef<HTMLInputElement>(null);

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

    try {
      // Call the chat API
      const response = await api.sendChatMessage(trimmedMessage, conversationId || undefined);

      if (response.success && response.data) {
        const data = response.data;

        // Update conversation ID if new
        if (data.conversation_id && data.conversation_id !== conversationId) {
          setConversationId(data.conversation_id);
          onConversationChange?.(data.conversation_id);
        }

        // Add assistant response
        const assistantMessage: ChatMessage = {
          id: data.message_id || `assistant-${Date.now()}`,
          role: 'assistant',
          content: data.content,
          model: data.model,
          complexity: data.complexity,
          cost_usd: data.cost_usd,
          tool_uses: data.tool_uses,
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, assistantMessage]);

        // Handle error in response
        if (data.error) {
          setError(data.error);
        }
      } else {
        setError(response.error || 'Failed to get response');

        // Add error message
        const errorMessage: ChatMessage = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: response.error || 'Something went wrong. Please try again.',
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, errorMessage]);
      }
    } catch (e) {
      const errorText = e instanceof Error ? e.message : 'Failed to send message';
      setError(errorText);

      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `Error: ${errorText}`,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMessage]);
    }

    setIsProcessing(false);
    setIsTyping(false);
    setTypingContent('');
    onStateChange?.('idle');
  };

  const clearConversation = () => {
    setMessages([]);
    setConversationId(null);
    setError(null);
    onConversationChange?.('');
  };

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
        'crystal-card overflow-hidden transition-all duration-300',
        isExpanded && 'fixed inset-4 z-50 flex flex-col',
        className
      )}
    >
      {/* Chat History (when enabled) */}
      {showHistory && (
        <div
          className={cn(
            'transition-all duration-300 overflow-hidden',
            isExpanded ? 'flex-1' : 'max-h-96',
            messages.length > 0 || isTyping ? 'p-4 border-b border-border-default' : ''
          )}
        >
          <ChatHistory
            messages={messages}
            isLoading={isLoadingHistory}
            isTyping={isTyping}
            typingContent={typingContent}
            className={cn(isExpanded ? 'h-full' : 'max-h-80')}
          />
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="px-4 py-2 bg-status-error/10 border-b border-status-error/30 flex items-center justify-between">
          <span className="text-caption text-status-error">{error}</span>
          <button
            onClick={() => setError(null)}
            className="p-1 hover:bg-status-error/20 rounded"
          >
            <X className="w-3 h-3 text-status-error" />
          </button>
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={handleSubmit}>
        <div
          className={cn(
            'flex items-center gap-3 p-4 transition-all duration-200',
            isFocused && 'ring-2 ring-accent-primary/30 rounded-2xl'
          )}
        >
          {/* Input */}
          <input
            ref={inputRef}
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={placeholder}
            disabled={processing}
            className={cn(
              'flex-1 bg-transparent text-body-lg text-text-primary',
              'placeholder:text-text-muted focus:outline-none',
              'disabled:opacity-50'
            )}
          />

          {/* Keyboard shortcut hint */}
          {!isFocused && !message && (
            <kbd className="hidden md:flex items-center gap-1 px-2 py-1 text-caption text-text-disabled bg-bg-surface rounded border border-border-default">
              <span className="text-xs">⌘</span>K
            </kbd>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-1">
            {/* Clear button (when there are messages) */}
            {messages.length > 0 && (
              <button
                type="button"
                onClick={clearConversation}
                className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors"
                title="Clear conversation"
              >
                <X className="w-5 h-5" />
              </button>
            )}

            {/* Expand/collapse (when showing history) */}
            {showHistory && (
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors"
                title={isExpanded ? 'Collapse' : 'Expand'}
              >
                {isExpanded ? (
                  <Minimize2 className="w-5 h-5" />
                ) : (
                  <Maximize2 className="w-5 h-5" />
                )}
              </button>
            )}

            {/* Attachment button (disabled for v1) */}
            <button
              type="button"
              disabled
              className="p-2 rounded-lg text-text-disabled cursor-not-allowed"
              title="Attachments coming soon"
            >
              <Paperclip className="w-5 h-5" />
            </button>

            {/* Voice button (disabled for v1) */}
            <button
              type="button"
              disabled
              className="p-2 rounded-lg text-text-disabled cursor-not-allowed"
              title="Voice input coming soon"
            >
              <Mic className="w-5 h-5" />
            </button>

            {/* Send button */}
            <button
              type="submit"
              disabled={!message.trim() || processing}
              className={cn(
                'p-2 rounded-lg transition-all duration-200',
                message.trim() && !processing
                  ? 'bg-accent-primary text-white hover:bg-accent-glow hover:shadow-glow-emerald'
                  : 'text-text-disabled cursor-not-allowed'
              )}
            >
              {processing ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
