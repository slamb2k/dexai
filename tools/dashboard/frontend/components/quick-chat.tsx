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

      {/* Input Form - Design7 styling */}
      <div className="-mx-6 px-6 border-t border-white/[0.04] pt-6">
        <form onSubmit={handleSubmit}>
          <div className="flex gap-4">
            {/* Input container - Design7 style */}
            <div
              className={cn(
                'flex-1 flex items-center gap-3',
                'bg-white/[0.02] border rounded-xl px-5 py-4',
                'transition-all duration-200',
                isFocused ? 'border-white/20' : 'border-white/[0.06]'
              )}
            >
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
                  'flex-1 bg-transparent outline-none',
                  'text-white placeholder-white/20',
                  'disabled:opacity-50'
                )}
              />

              {/* Clear button (when there are messages) */}
              {messages.length > 0 && (
                <button
                  type="button"
                  onClick={clearConversation}
                  className="text-white/20 hover:text-white/40 transition-colors"
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
                  className="text-white/20 hover:text-white/40 transition-colors"
                  title={isExpanded ? 'Collapse' : 'Expand'}
                >
                  {isExpanded ? (
                    <Minimize2 className="w-5 h-5" />
                  ) : (
                    <Maximize2 className="w-5 h-5" />
                  )}
                </button>
              )}

              {/* Attachment button */}
              <button
                type="button"
                disabled
                className="text-white/20 hover:text-white/40 cursor-pointer transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                title="Attachments coming soon"
              >
                <Paperclip className="w-5 h-5" />
              </button>

              {/* Voice button */}
              <button
                type="button"
                disabled
                className="text-white/20 hover:text-white/40 cursor-pointer transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                title="Voice input coming soon"
              >
                <Mic className="w-5 h-5" />
              </button>
            </div>

            {/* Send button - Design7 style */}
            <button
              type="submit"
              disabled={!message.trim() || processing}
              className={cn(
                'px-6 rounded-xl transition-all duration-200',
                'border flex items-center justify-center',
                message.trim() && !processing
                  ? 'bg-white/10 hover:bg-white/15 border-white/10'
                  : 'bg-white/[0.02] border-white/[0.04] cursor-not-allowed'
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
