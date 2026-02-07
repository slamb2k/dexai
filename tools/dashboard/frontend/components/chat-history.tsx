'use client';

import { useEffect, useRef, useState } from 'react';
import { Bot, User, Copy, Check, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  model?: string;
  complexity?: string;
  cost_usd?: number;
  tool_uses?: { tool: string; input: unknown }[];
  created_at: string;
}

interface ChatHistoryProps {
  messages: ChatMessage[];
  isLoading?: boolean;
  isTyping?: boolean;
  typingContent?: string;
  className?: string;
  onRetry?: (messageId: string) => void;
}

export function ChatHistory({
  messages,
  isLoading = false,
  isTyping = false,
  typingContent = '',
  className,
  onRetry,
}: ChatHistoryProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, typingContent]);

  const handleCopy = async (content: string, id: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (e) {
      console.error('Failed to copy:', e);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  if (isLoading) {
    return (
      <div className={cn('flex items-center justify-center p-8', className)}>
        <Loader2 className="w-6 h-6 text-text-muted animate-spin" />
      </div>
    );
  }

  if (messages.length === 0 && !isTyping) {
    return (
      <div className={cn('flex flex-col items-center justify-center p-8 text-center', className)}>
        <div className="w-16 h-16 rounded-full bg-accent-muted flex items-center justify-center mb-4">
          <Bot className="w-8 h-8 text-accent-primary" />
        </div>
        <h3 className="text-body-lg text-text-primary mb-2">Start a conversation</h3>
        <p className="text-body text-text-muted max-w-sm">
          Ask Dex anything. I&apos;m here to help you get things done.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={cn('flex flex-col space-y-4 overflow-y-auto', className)}
    >
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          isCopied={copiedId === message.id}
          onCopy={() => handleCopy(message.content, message.id)}
          formatTimestamp={formatTimestamp}
        />
      ))}

      {/* Typing indicator */}
      {isTyping && (
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-accent-primary flex items-center justify-center">
            <Bot className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1 max-w-[80%]">
            <div className="crystal-card p-4">
              {typingContent ? (
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown>{typingContent}</ReactMarkdown>
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-text-muted animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 rounded-full bg-text-muted animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 rounded-full bg-text-muted animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
  isCopied: boolean;
  onCopy: () => void;
  formatTimestamp: (ts: string) => string;
}

function MessageBubble({ message, isCopied, onCopy, formatTimestamp }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        'flex items-start gap-3',
        isUser && 'flex-row-reverse'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center',
          isUser ? 'bg-bg-surface' : 'bg-accent-primary'
        )}
      >
        {isUser ? (
          <User className="w-4 h-4 text-text-muted" />
        ) : (
          <Bot className="w-4 h-4 text-white" />
        )}
      </div>

      {/* Content */}
      <div className={cn('flex-1 max-w-[80%]', isUser && 'flex flex-col items-end')}>
        <div
          className={cn(
            'group relative',
            isUser
              ? 'bg-accent-primary text-white rounded-2xl rounded-tr-sm px-4 py-2'
              : 'crystal-card p-4'
          )}
        >
          {isUser ? (
            <p className="text-body">{message.content}</p>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown
                components={{
                  // Style code blocks
                  code({ node, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const isInline = !match && !className;

                    if (isInline) {
                      return (
                        <code
                          className="bg-bg-surface px-1.5 py-0.5 rounded text-sm font-mono"
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    }

                    return (
                      <pre className="bg-bg-surface rounded-lg p-3 overflow-x-auto">
                        <code className={cn('text-sm font-mono', className)} {...props}>
                          {children}
                        </code>
                      </pre>
                    );
                  },
                  // Style links
                  a({ href, children }) {
                    return (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent-primary hover:underline"
                      >
                        {children}
                      </a>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {/* Copy button (assistant messages only) */}
          {!isUser && (
            <button
              onClick={onCopy}
              className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-bg-surface"
              title="Copy to clipboard"
            >
              {isCopied ? (
                <Check className="w-4 h-4 text-status-success" />
              ) : (
                <Copy className="w-4 h-4 text-text-muted" />
              )}
            </button>
          )}
        </div>

        {/* Metadata row */}
        <div
          className={cn(
            'flex items-center gap-2 mt-1 text-caption text-text-disabled',
            isUser && 'flex-row-reverse'
          )}
        >
          <span>{formatTimestamp(message.created_at)}</span>
          {message.model && (
            <>
              <span>•</span>
              <span>{message.model.split('/').pop()}</span>
            </>
          )}
          {message.cost_usd !== undefined && message.cost_usd > 0 && (
            <>
              <span>•</span>
              <span>${message.cost_usd.toFixed(4)}</span>
            </>
          )}
        </div>

        {/* Tool uses (collapsed by default) */}
        {message.tool_uses && message.tool_uses.length > 0 && (
          <ToolUsesDisplay tools={message.tool_uses} />
        )}
      </div>
    </div>
  );
}

interface ToolUsesDisplayProps {
  tools: { tool: string; input: unknown }[];
}

function ToolUsesDisplay({ tools }: ToolUsesDisplayProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-caption text-text-muted hover:text-text-secondary flex items-center gap-1"
      >
        <span>{tools.length} tool{tools.length !== 1 ? 's' : ''} used</span>
        <span className={cn('transition-transform', expanded && 'rotate-180')}>▼</span>
      </button>
      {expanded && (
        <div className="mt-2 space-y-1 text-caption">
          {tools.map((tool, idx) => (
            <div
              key={idx}
              className="bg-bg-surface rounded px-2 py-1 font-mono text-text-muted"
            >
              {tool.tool}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ChatHistory;
