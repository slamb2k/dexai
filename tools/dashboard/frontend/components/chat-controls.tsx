'use client';

import { useState } from 'react';
import { Check, ChevronDown, Eye, EyeOff, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatControl } from './chat-history';

interface ChatControlProps {
  control: ChatControl;
  submitted?: boolean;
  submittedValue?: string;
  onSubmit: (controlId: string, field: string, value: string) => void;
}

/**
 * Dropdown select control rendered inline in assistant messages.
 */
export function ChatSelect({ control, submitted, submittedValue, onSubmit }: ChatControlProps) {
  const [value, setValue] = useState(control.default_value || '');
  const [isOpen, setIsOpen] = useState(false);

  if (submitted) {
    const selectedOption = control.options?.find(o => o.value === submittedValue);
    return (
      <div className="mt-3 flex items-center gap-2">
        {control.label && <span className="text-xs text-white/40">{control.label}:</span>}
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-sm text-emerald-400">
          <Check className="w-3.5 h-3.5" />
          {selectedOption?.label || submittedValue}
        </span>
      </div>
    );
  }

  return (
    <div className="mt-3">
      {control.label && (
        <label className="block text-xs text-white/50 mb-1.5">{control.label}</label>
      )}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            className={cn(
              'w-full flex items-center justify-between gap-2',
              'px-3 py-2 rounded-lg text-sm text-left',
              'bg-white/[0.04] border border-white/[0.08]',
              'hover:border-white/15 transition-colors',
              isOpen && 'border-white/20'
            )}
          >
            <span className={value ? 'text-white/80' : 'text-white/30'}>
              {control.options?.find(o => o.value === value)?.label || control.placeholder || 'Select...'}
            </span>
            <ChevronDown className={cn('w-4 h-4 text-white/30 transition-transform', isOpen && 'rotate-180')} />
          </button>
          {isOpen && (
            <div className="absolute z-10 mt-1 w-full rounded-lg bg-[#1a1a2e] border border-white/[0.08] shadow-xl overflow-hidden">
              {control.options?.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    setValue(option.value);
                    setIsOpen(false);
                  }}
                  className={cn(
                    'w-full text-left px-3 py-2 text-sm transition-colors',
                    'hover:bg-white/[0.06]',
                    value === option.value ? 'text-emerald-400 bg-white/[0.04]' : 'text-white/70'
                  )}
                >
                  <div>{option.label}</div>
                  {option.description && (
                    <div className="text-xs text-white/30 mt-0.5">{option.description}</div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => value && onSubmit(control.control_id, control.field, value)}
          disabled={!value}
          className={cn(
            'px-4 py-2 rounded-lg text-sm border transition-all',
            value
              ? 'bg-white/10 hover:bg-white/15 border-white/10 text-white/80'
              : 'bg-white/[0.02] border-white/[0.04] text-white/20 cursor-not-allowed'
          )}
        >
          Confirm
        </button>
      </div>
    </div>
  );
}

/**
 * Row of toggle buttons. Click to select and immediately submit.
 */
export function ChatButtonGroup({ control, submitted, submittedValue, onSubmit }: ChatControlProps) {
  if (submitted) {
    const selectedOption = control.options?.find(o => o.value === submittedValue);
    return (
      <div className="mt-3 flex items-center gap-2">
        {control.label && <span className="text-xs text-white/40">{control.label}:</span>}
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-sm text-emerald-400">
          <Check className="w-3.5 h-3.5" />
          {selectedOption?.label || submittedValue}
        </span>
      </div>
    );
  }

  return (
    <div className="mt-3">
      {control.label && (
        <label className="block text-xs text-white/50 mb-1.5">{control.label}</label>
      )}
      <div className="flex flex-wrap gap-2">
        {control.options?.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onSubmit(control.control_id, control.field, option.value)}
            className={cn(
              'px-4 py-2 rounded-lg text-sm border transition-all',
              'bg-white/[0.04] border-white/[0.08] text-white/70',
              'hover:bg-white/[0.08] hover:border-white/15 hover:text-white/90'
            )}
            title={option.description}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * Text input with submit button.
 */
export function ChatTextInput({ control, submitted, submittedValue, onSubmit }: ChatControlProps) {
  const [value, setValue] = useState(control.default_value || '');
  const [validating, setValidating] = useState(false);

  if (submitted) {
    return (
      <div className="mt-3 flex items-center gap-2">
        {control.label && <span className="text-xs text-white/40">{control.label}:</span>}
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-sm text-emerald-400">
          <Check className="w-3.5 h-3.5" />
          {submittedValue}
        </span>
      </div>
    );
  }

  const handleSubmit = () => {
    if (!value.trim()) return;
    setValidating(true);
    onSubmit(control.control_id, control.field, value.trim());
  };

  return (
    <div className="mt-3">
      {control.label && (
        <label className="block text-xs text-white/50 mb-1.5">{control.label}</label>
      )}
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          placeholder={control.placeholder || ''}
          className={cn(
            'flex-1 px-3 py-2 rounded-lg text-sm',
            'bg-white/[0.04] border border-white/[0.08]',
            'text-white/80 placeholder-white/20',
            'outline-none focus:border-white/20 transition-colors'
          )}
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!value.trim() || validating}
          className={cn(
            'px-4 py-2 rounded-lg text-sm border transition-all',
            value.trim() && !validating
              ? 'bg-white/10 hover:bg-white/15 border-white/10 text-white/80'
              : 'bg-white/[0.02] border-white/[0.04] text-white/20 cursor-not-allowed'
          )}
        >
          {validating ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Confirm'}
        </button>
      </div>
    </div>
  );
}

/**
 * Secure (password) input with eye toggle and submit button.
 */
export function ChatSecureInput({ control, submitted, submittedValue, onSubmit }: ChatControlProps) {
  const [value, setValue] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (submitted) {
    // Mask the value for display
    const masked = submittedValue ? submittedValue.slice(0, 7) + '...' + submittedValue.slice(-4) : '***';
    return (
      <div className="mt-3 flex items-center gap-2">
        {control.label && <span className="text-xs text-white/40">{control.label}:</span>}
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-sm text-emerald-400">
          <Check className="w-3.5 h-3.5" />
          {masked}
        </span>
      </div>
    );
  }

  const handleSubmit = () => {
    if (!value.trim()) return;
    setError(null);
    setValidating(true);
    onSubmit(control.control_id, control.field, value.trim());
  };

  return (
    <div className="mt-3">
      {control.label && (
        <label className="block text-xs text-white/50 mb-1.5">{control.label}</label>
      )}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            type={showPassword ? 'text' : 'password'}
            value={value}
            onChange={(e) => { setValue(e.target.value); setError(null); }}
            onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            placeholder={control.placeholder || 'Enter key...'}
            className={cn(
              'w-full px-3 py-2 pr-10 rounded-lg text-sm',
              'bg-white/[0.04] border',
              error ? 'border-red-500/40' : 'border-white/[0.08]',
              'text-white/80 placeholder-white/20',
              'outline-none focus:border-white/20 transition-colors',
              'font-mono'
            )}
          />
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-white/30 hover:text-white/50 transition-colors"
          >
            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!value.trim() || validating}
          className={cn(
            'px-4 py-2 rounded-lg text-sm border transition-all',
            value.trim() && !validating
              ? 'bg-white/10 hover:bg-white/15 border-white/10 text-white/80'
              : 'bg-white/[0.02] border-white/[0.04] text-white/20 cursor-not-allowed'
          )}
        >
          {validating ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Confirm'}
        </button>
      </div>
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
    </div>
  );
}

/**
 * Renders the appropriate control component based on control_type.
 */
export function ChatControlRenderer({
  control,
  submitted,
  submittedValue,
  onSubmit,
}: ChatControlProps) {
  const props = { control, submitted, submittedValue, onSubmit };
  switch (control.control_type) {
    case 'select':
      return <ChatSelect {...props} />;
    case 'button_group':
      return <ChatButtonGroup {...props} />;
    case 'text_input':
      return <ChatTextInput {...props} />;
    case 'secure_input':
      return <ChatSecureInput {...props} />;
    default:
      return null;
  }
}
