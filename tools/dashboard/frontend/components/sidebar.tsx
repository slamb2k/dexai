'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home,
  ListTodo,
  Activity,
  BarChart3,
  Shield,
  Settings,
  Bug,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';

const navItems = [
  { href: '/', icon: Home, label: 'Home' },
  { href: '/tasks', icon: ListTodo, label: 'Tasks' },
  { href: '/activity', icon: Activity, label: 'Activity' },
  { href: '/metrics', icon: BarChart3, label: 'Metrics' },
  { href: '/audit', icon: Shield, label: 'Audit' },
  { href: '/settings', icon: Settings, label: 'Settings' },
  { href: '/debug', icon: Bug, label: 'Debug', admin: true },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        'bg-bg-surface border-r border-border-default flex flex-col transition-all duration-300',
        collapsed ? 'w-16' : 'w-56'
      )}
    >
      {/* Logo */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-border-default">
        {!collapsed && (
          <span className="text-section-header font-semibold text-text-primary">
            DexAI
          </span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-button hover:bg-bg-elevated text-text-muted hover:text-text-primary transition-colors"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4">
        <ul className="space-y-1 px-2">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;

            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2.5 rounded-button transition-all duration-200',
                    isActive
                      ? 'bg-accent-primary/10 text-accent-primary'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated',
                    collapsed && 'justify-center'
                  )}
                >
                  <Icon size={20} className={isActive ? 'text-accent-primary' : ''} />
                  {!collapsed && (
                    <span className="text-body">{item.label}</span>
                  )}
                  {isActive && !collapsed && (
                    <span className="ml-auto w-1.5 h-1.5 rounded-full bg-accent-primary" />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Bottom section */}
      <div className="p-4 border-t border-border-default">
        {!collapsed && (
          <div className="text-caption text-text-muted">
            <p>DexAI v0.1.0</p>
            <p className="text-text-disabled">Phase 7 Dashboard</p>
          </div>
        )}
      </div>
    </aside>
  );
}
