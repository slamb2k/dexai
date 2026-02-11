'use client';

import { useEffect, useRef, useState } from 'react';
import { Brain, Copy, Check, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import { ChatControlRenderer } from './chat-controls';

export interface ChatControl {
  control_type: 'select' | 'button_group' | 'text_input' | 'secure_input';
  control_id: string;
  label?: string;
  field: string;
  options?: { value: string; label: string; description?: string }[];
  default_value?: string;
  placeholder?: string;
  required?: boolean;
  validation?: string;
  multi_select?: boolean;
  allow_custom?: boolean;
  skippable?: boolean;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  model?: string;
  complexity?: string;
  cost_usd?: number;
  tool_uses?: { tool: string; input: unknown }[];
  controls?: ChatControl[];
  control_values?: Record<string, string>;
  created_at: string;
}

interface ChatHistoryProps {
  messages: ChatMessage[];
  isLoading?: boolean;
  isTyping?: boolean;
  typingContent?: string;
  className?: string;
  onRetry?: (messageId: string) => void;
  onControlSubmit?: (controlId: string, field: string, value: string) => void;
  userInitials?: string;
}

export function ChatHistory({
  messages,
  isLoading = false,
  isTyping = false,
  typingContent = '',
  className,
  onRetry,
  onControlSubmit,
  userInitials = 'U',
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
        <Loader2 className="w-6 h-6 text-white/40 animate-spin" />
      </div>
    );
  }

  if (messages.length === 0 && !isTyping) {
    return (
      <div className={cn('flex flex-col items-center justify-center p-8 text-center', className)}>
        <div className="w-16 h-16 rounded-2xl bg-white/[0.04] border border-white/[0.08] flex items-center justify-center mb-4">
          <Brain className="w-8 h-8 text-white/30" />
        </div>
        <h3 className="text-base font-medium text-white/80 mb-2">Start a conversation</h3>
        <p className="text-sm text-white/40 max-w-sm">
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
        <CrystalMessage
          key={message.id}
          message={message}
          isCopied={copiedId === message.id}
          onCopy={() => handleCopy(message.content, message.id)}
          onControlSubmit={onControlSubmit}
          formatTimestamp={formatTimestamp}
          userInitials={userInitials}
        />
      ))}

      {/* Typing indicator with streaming content */}
      {isTyping && (
        <div className="flex gap-4">
          <div className="w-10 h-10 rounded-xl bg-white/[0.04] border border-white/[0.08] flex items-center justify-center flex-shrink-0">
            <Brain className="w-5 h-5 text-white/50" />
          </div>
          <div className="max-w-[75%]">
            <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
              {typingContent ? (
                <div className="prose prose-sm prose-invert max-w-none">
                  <ReactMarkdown
                    components={{
                      p({ children }) {
                        return (
                          <p className="text-[15px] leading-relaxed text-white/80 mb-3 last:mb-0">
                            {children}
                          </p>
                        );
                      },
                      code({ node, className, children, ...props }) {
                        const match = /language-(\w+)/.exec(className || '');
                        const isInline = !match && !className;
                        if (isInline) {
                          return (
                            <code className="bg-white/[0.06] px-1.5 py-0.5 rounded text-sm font-mono text-white/70" {...props}>
                              {children}
                            </code>
                          );
                        }
                        return (
                          <pre className="bg-white/[0.04] border border-white/[0.06] rounded-xl p-4 overflow-x-auto my-3">
                            <code className={cn('text-sm font-mono text-white/70', className)} {...props}>
                              {children}
                            </code>
                          </pre>
                        );
                      },
                      ul({ children }) {
                        return <ul className="list-disc list-inside space-y-1 my-2 text-white/80">{children}</ul>;
                      },
                      ol({ children }) {
                        return <ol className="list-decimal list-inside space-y-1 my-2 text-white/80">{children}</ol>;
                      },
                      li({ children }) {
                        return <li className="text-[15px] leading-relaxed">{children}</li>;
                      },
                    }}
                  >
                    {typingContent}
                  </ReactMarkdown>
                  {/* Blinking cursor animation */}
                  <span className="inline-block w-[2px] h-[1.1em] bg-white/60 ml-0.5 align-middle animate-pulse" />
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-white/30 animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 rounded-full bg-white/30 animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 rounded-full bg-white/30 animate-bounce" style={{ animationDelay: '300ms' }} />
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

interface CrystalMessageProps {
  message: ChatMessage;
  isCopied: boolean;
  onCopy: () => void;
  onControlSubmit?: (controlId: string, field: string, value: string) => void;
  formatTimestamp: (ts: string) => string;
  userInitials: string;
}

/**
 * Crystal Dark message bubble - matches Design7 styling exactly
 */
function CrystalMessage({
  message,
  isCopied,
  onCopy,
  onControlSubmit,
  formatTimestamp,
  userInitials,
}: CrystalMessageProps) {
  const isAi = message.role === 'assistant';

  return (
    <div className={cn('flex gap-4', !isAi && 'flex-row-reverse')}>
      {/* Avatar - only for AI messages */}
      {isAi && (
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 border bg-white/[0.04] border-white/[0.08]">
          <Brain className="w-5 h-5 text-white/50" />
        </div>
      )}

      {/* Content */}
      <div className={cn('max-w-[75%]', !isAi && 'text-right ml-auto')}>
        {/* Message bubble - Design7 style */}
        <div
          className={cn(
            'group relative p-4 rounded-2xl border',
            isAi
              ? 'bg-white/[0.02] border-white/[0.04]'
              : 'bg-white/[0.05] border-white/[0.08]'
          )}
        >
          {isAi ? (
            <div className="prose prose-sm prose-invert max-w-none">
              <ReactMarkdown
                components={{
                  p({ children }) {
                    return (
                      <p className="text-[15px] leading-relaxed text-white/80 mb-3 last:mb-0">
                        {children}
                      </p>
                    );
                  },
                  code({ node, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const isInline = !match && !className;

                    if (isInline) {
                      return (
                        <code
                          className="bg-white/[0.06] px-1.5 py-0.5 rounded text-sm font-mono text-white/70"
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    }

                    return (
                      <pre className="bg-white/[0.04] border border-white/[0.06] rounded-xl p-4 overflow-x-auto my-3">
                        <code className={cn('text-sm font-mono text-white/70', className)} {...props}>
                          {children}
                        </code>
                      </pre>
                    );
                  },
                  a({ href, children }) {
                    return (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-emerald-400 hover:text-emerald-300 hover:underline"
                      >
                        {children}
                      </a>
                    );
                  },
                  ul({ children }) {
                    return <ul className="list-disc list-inside space-y-1 my-2 text-white/80">{children}</ul>;
                  },
                  ol({ children }) {
                    return <ol className="list-decimal list-inside space-y-1 my-2 text-white/80">{children}</ol>;
                  },
                  li({ children }) {
                    return <li className="text-[15px] leading-relaxed">{children}</li>;
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
              {/* Inline controls rendered after markdown content */}
              {message.controls && message.controls.length > 0 && (
                <div className="mt-2 space-y-2">
                  {message.controls.map((control) => (
                    <ChatControlRenderer
                      key={control.control_id}
                      control={control}
                      submitted={!!message.control_values?.[control.control_id]}
                      submittedValue={message.control_values?.[control.control_id]}
                      onSubmit={onControlSubmit || (() => {})}
                    />
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-[15px] leading-relaxed text-white/80">{message.content}</p>
          )}

          {/* Copy button (assistant messages only) */}
          {isAi && (
            <button
              onClick={onCopy}
              className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-white/[0.06]"
              title="Copy to clipboard"
            >
              {isCopied ? (
                <Check className="w-4 h-4 text-emerald-400" />
              ) : (
                <Copy className="w-4 h-4 text-white/30 hover:text-white/50" />
              )}
            </button>
          )}
        </div>

        {/* Timestamp - Design7 style */}
        <span className="text-[11px] text-white/20 mt-2 block">
          {formatTimestamp(message.created_at)}
          {message.model && ` · ${message.model.split('/').pop()}`}
          {message.cost_usd !== undefined && message.cost_usd > 0 && ` · $${message.cost_usd.toFixed(4)}`}
        </span>

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
        className="text-[11px] text-white/30 hover:text-white/50 flex items-center gap-1 transition-colors"
      >
        <span>{tools.length} tool{tools.length !== 1 ? 's' : ''} used</span>
        <span className={cn('transition-transform text-[10px]', expanded && 'rotate-180')}>▼</span>
      </button>
      {expanded && (
        <div className="mt-2 space-y-1">
          {tools.map((tool, idx) => (
            <div
              key={idx}
              className="bg-white/[0.04] border border-white/[0.06] rounded-lg px-2 py-1 font-mono text-[11px] text-white/40"
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
