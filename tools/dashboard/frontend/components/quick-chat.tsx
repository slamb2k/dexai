'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, Mic, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface QuickChatProps {
  onSendMessage?: (message: string) => void;
  isProcessing?: boolean;
  placeholder?: string;
  className?: string;
}

export function QuickChat({
  onSendMessage,
  isProcessing = false,
  placeholder = 'Ask Dex anything...',
  className,
}: QuickChatProps) {
  const [message, setMessage] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim() && !isProcessing) {
      onSendMessage?.(message.trim());
      setMessage('');
    }
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

  return (
    <div className={cn('crystal-card', className)}>
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
            disabled={isProcessing}
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
              disabled={!message.trim() || isProcessing}
              className={cn(
                'p-2 rounded-lg transition-all duration-200',
                message.trim() && !isProcessing
                  ? 'bg-accent-primary text-white hover:bg-accent-glow hover:shadow-glow-emerald'
                  : 'text-text-disabled cursor-not-allowed'
              )}
            >
              {isProcessing ? (
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
