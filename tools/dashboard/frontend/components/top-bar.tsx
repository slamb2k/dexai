'use client';

import { Settings, User, Bell, Search } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { cn } from '@/lib/utils';

export function TopBar() {
  const [searchFocused, setSearchFocused] = useState(false);

  return (
    <header className="h-16 bg-bg-surface border-b border-border-default flex items-center justify-between px-6">
      {/* Search */}
      <div className="flex-1 max-w-md">
        <div
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-button border transition-all duration-200',
            searchFocused
              ? 'border-border-focus bg-bg-input shadow-glow-blue'
              : 'border-border-default bg-bg-input'
          )}
        >
          <Search size={18} className="text-text-muted" />
          <input
            type="text"
            placeholder="Search tasks, activity..."
            className="flex-1 bg-transparent text-body text-text-primary placeholder:text-text-muted focus:outline-none"
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
          />
          <kbd className="hidden sm:inline-flex px-2 py-0.5 text-caption text-text-disabled bg-bg-elevated rounded">
            /
          </kbd>
        </div>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-2">
        {/* Notifications */}
        <button
          className="p-2 rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors relative"
          aria-label="Notifications"
        >
          <Bell size={20} />
          {/* Notification badge */}
          <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-status-error" />
        </button>

        {/* Settings */}
        <Link
          href="/settings"
          className="p-2 rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
          aria-label="Settings"
        >
          <Settings size={20} />
        </Link>

        {/* User menu */}
        <button
          className="flex items-center gap-2 px-3 py-1.5 rounded-button hover:bg-bg-elevated transition-colors"
          aria-label="User menu"
        >
          <div className="w-8 h-8 rounded-full bg-accent-primary/20 flex items-center justify-center">
            <User size={18} className="text-accent-primary" />
          </div>
          <span className="hidden sm:block text-body text-text-primary">User</span>
        </button>
      </div>
    </header>
  );
}
