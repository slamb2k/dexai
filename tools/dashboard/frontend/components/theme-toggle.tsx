'use client';

import { Moon, Sun, Monitor } from 'lucide-react';
import { useTheme } from '@/lib/theme-provider';
import { cn } from '@/lib/utils';

interface ThemeToggleProps {
  showLabel?: boolean;
  className?: string;
}

export function ThemeToggle({ showLabel = false, className }: ThemeToggleProps) {
  const { theme, resolvedTheme, setTheme, toggleTheme } = useTheme();

  // Simple toggle button
  if (!showLabel) {
    return (
      <button
        onClick={toggleTheme}
        className={cn(
          'p-2 rounded-lg transition-all duration-200',
          'text-text-secondary hover:text-text-primary',
          'hover:bg-bg-hover',
          className
        )}
        aria-label="Toggle theme"
      >
        {resolvedTheme === 'dark' ? (
          <Moon className="h-5 w-5" />
        ) : (
          <Sun className="h-5 w-5" />
        )}
      </button>
    );
  }

  // Segmented control for theme selection
  return (
    <div
      className={cn(
        'inline-flex items-center p-1 rounded-xl',
        'bg-bg-surface border border-border-default',
        className
      )}
    >
      <ThemeButton
        active={theme === 'light'}
        onClick={() => setTheme('light')}
        icon={<Sun className="h-4 w-4" />}
        label="Light"
      />
      <ThemeButton
        active={theme === 'dark'}
        onClick={() => setTheme('dark')}
        icon={<Moon className="h-4 w-4" />}
        label="Dark"
      />
      <ThemeButton
        active={theme === 'system'}
        onClick={() => setTheme('system')}
        icon={<Monitor className="h-4 w-4" />}
        label="System"
      />
    </div>
  );
}

function ThemeButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200',
        active
          ? 'bg-accent-primary text-white shadow-glow-emerald'
          : 'text-text-secondary hover:text-text-primary hover:bg-bg-hover'
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}
