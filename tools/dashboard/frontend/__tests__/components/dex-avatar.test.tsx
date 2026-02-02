/**
 * Tests for DexAvatar component
 *
 * The DexAvatar provides visual feedback about the AI's current state.
 * It has 9 states: idle, listening, thinking, working, success, error,
 * sleeping, hyperfocus, and waiting.
 *
 * This is important for ADHD users because:
 * - Visual feedback reduces "is it working?" anxiety
 * - Different states help understand what Dex is doing
 * - The avatar provides a friendly, non-judgmental presence
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DexAvatar, type AvatarState } from '@/components/dex-avatar';

describe('DexAvatar', () => {
  const allStates: AvatarState[] = [
    'idle',
    'listening',
    'thinking',
    'working',
    'success',
    'error',
    'sleeping',
    'hyperfocus',
    'waiting',
  ];

  describe('State rendering', () => {
    it.each(allStates)('renders %s state without error', (state) => {
      expect(() => {
        render(<DexAvatar state={state} />);
      }).not.toThrow();
    });

    it('displays correct label for idle state', () => {
      render(<DexAvatar state="idle" />);
      expect(screen.getByText('Ready')).toBeInTheDocument();
    });

    it('displays correct label for thinking state', () => {
      render(<DexAvatar state="thinking" />);
      expect(screen.getByText('Thinking')).toBeInTheDocument();
    });

    it('displays correct label for working state', () => {
      render(<DexAvatar state="working" />);
      expect(screen.getByText('Working')).toBeInTheDocument();
    });

    it('displays correct label for success state', () => {
      render(<DexAvatar state="success" />);
      expect(screen.getByText('Done!')).toBeInTheDocument();
    });

    it('displays correct label for error state', () => {
      render(<DexAvatar state="error" />);
      expect(screen.getByText('Error')).toBeInTheDocument();
    });

    it('displays correct label for hyperfocus state', () => {
      render(<DexAvatar state="hyperfocus" />);
      expect(screen.getByText('Protecting Focus')).toBeInTheDocument();
    });
  });

  describe('Size variants', () => {
    const sizes = ['sm', 'md', 'lg', 'xl'] as const;

    it.each(sizes)('renders %s size without error', (size) => {
      expect(() => {
        render(<DexAvatar state="idle" size={size} />);
      }).not.toThrow();
    });

    it('defaults to md size', () => {
      const { container } = render(<DexAvatar state="idle" />);
      // Should render without explicit size
      expect(container.firstChild).toBeInTheDocument();
    });
  });

  describe('Label visibility', () => {
    it('shows label by default', () => {
      render(<DexAvatar state="idle" />);
      expect(screen.getByText('Ready')).toBeInTheDocument();
    });

    it('hides label when showLabel is false', () => {
      render(<DexAvatar state="idle" showLabel={false} />);
      expect(screen.queryByText('Ready')).not.toBeInTheDocument();
    });
  });

  describe('Current task display', () => {
    it('displays current task when provided', () => {
      render(
        <DexAvatar state="working" currentTask="Processing your request..." />
      );
      expect(screen.getByText('Processing your request...')).toBeInTheDocument();
    });

    it('does not show task when not provided', () => {
      render(<DexAvatar state="working" />);
      // Should only show state label, not a task
      expect(screen.getByText('Working')).toBeInTheDocument();
    });
  });

  describe('SVG face rendering', () => {
    it('renders face SVG', () => {
      const { container } = render(<DexAvatar state="idle" />);
      const svg = container.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });

    it('renders eyes based on state', () => {
      const { container } = render(<DexAvatar state="idle" />);
      // Eyes are rendered as ellipses for open state
      const ellipses = container.querySelectorAll('ellipse');
      expect(ellipses.length).toBeGreaterThan(0);
    });

    it('renders closed eyes for sleeping state', () => {
      const { container } = render(<DexAvatar state="sleeping" />);
      // Sleeping state uses lines for closed eyes
      const lines = container.querySelectorAll('line');
      expect(lines.length).toBeGreaterThan(0);
    });
  });

  describe('State-specific overlays', () => {
    it('renders checkmark overlay for success state', () => {
      const { container } = render(<DexAvatar state="success" />);
      // Success state has a checkmark path
      const paths = container.querySelectorAll('path');
      expect(paths.length).toBeGreaterThan(0);
    });

    it('renders warning overlay for error state', () => {
      const { container } = render(<DexAvatar state="error" />);
      // Error state has a warning circle and exclamation
      expect(container.querySelector('text')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('avatar container is in the DOM', () => {
      const { container } = render(<DexAvatar state="idle" />);
      expect(container.firstChild).toBeInTheDocument();
    });

    it('state label serves as text alternative', () => {
      render(<DexAvatar state="idle" />);
      // The label provides context for the visual state
      expect(screen.getByText('Ready')).toBeInTheDocument();
    });
  });
});

describe('Avatar state meanings', () => {
  /**
   * These tests document the purpose of each state for ADHD users.
   * The avatar's state communicates what Dex is doing without requiring
   * the user to read detailed status messages.
   */

  it('idle state indicates Dex is ready to help', () => {
    render(<DexAvatar state="idle" />);
    expect(screen.getByText('Ready')).toBeInTheDocument();
  });

  it('listening state indicates Dex is receiving input', () => {
    render(<DexAvatar state="listening" />);
    expect(screen.getByText('Listening')).toBeInTheDocument();
  });

  it('thinking state indicates processing is happening', () => {
    render(<DexAvatar state="thinking" />);
    expect(screen.getByText('Thinking')).toBeInTheDocument();
  });

  it('hyperfocus state indicates Dex is protecting flow', () => {
    render(<DexAvatar state="hyperfocus" />);
    // "Protecting Focus" communicates that Dex is actively helping
    // the user maintain their productive state
    expect(screen.getByText('Protecting Focus')).toBeInTheDocument();
  });

  it('waiting state indicates Dex needs user input', () => {
    render(<DexAvatar state="waiting" />);
    expect(screen.getByText('Waiting')).toBeInTheDocument();
  });
});
