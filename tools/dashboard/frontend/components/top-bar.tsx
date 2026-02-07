'use client';

import { Settings, User, Bell, Search } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { ThemeToggle } from './theme-toggle';
import { FlowBadge } from './flow-indicator';

interface TopBarProps {
  isInFlow?: boolean;
  flowMinutes?: number;
  notificationCount?: number;
}

export function TopBar({
  isInFlow = false,
  flowMinutes,
  notificationCount = 0,
}: TopBarProps) {
  const [searchFocused, setSearchFocused] = useState(false);

  return (
    <header className="h-16 bg-bg-surface/50 backdrop-blur-crystal border-b border-border-default flex items-center justify-between px-6">
      {/* Search */}
      <div className="flex-1 max-w-md">
        <div
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-xl border transition-all duration-200',
            searchFocused
              ? 'border-border-focus bg-bg-input shadow-glow-emerald/20'
              : 'border-border-default bg-bg-input'
          )}
        >
          <Search size={18} className="text-text-muted flex-shrink-0" />
          <input
            type="text"
            placeholder="Search tasks, memory..."
            className="flex-1 bg-transparent text-body text-text-primary placeholder:text-text-muted focus:outline-none"
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
          />
          <kbd className="hidden sm:inline-flex px-2 py-0.5 text-caption text-text-disabled bg-bg-surface rounded border border-border-default">
            /
          </kbd>
        </div>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-2">
        {/* Flow state badge */}
        <FlowBadge isInFlow={isInFlow} elapsedMinutes={flowMinutes} />

        {/* Theme toggle */}
        <ThemeToggle />

        {/* Notifications */}
        <button
          className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors relative"
          aria-label="Notifications"
        >
          <Bell size={20} />
          {notificationCount > 0 && (
            <span className="absolute top-1 right-1 w-4 h-4 flex items-center justify-center rounded-full bg-status-error text-white text-xs font-medium">
              {notificationCount > 9 ? '9+' : notificationCount}
            </span>
          )}
        </button>

        {/* Settings */}
        <Link
          href="/settings"
          className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          aria-label="Settings"
        >
          <Settings size={20} />
        </Link>

        {/* User menu */}
        <button
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl hover:bg-bg-hover transition-colors"
          aria-label="User menu"
        >
          <div className="w-8 h-8 rounded-full bg-accent-muted flex items-center justify-center">
            <User size={18} className="text-accent-primary" />
          </div>
          <span className="hidden sm:block text-body text-text-primary">User</span>
        </button>
      </div>
    </header>
  );
}
