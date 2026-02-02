/**
 * Tests for StatCard component
 *
 * The StatCard displays metrics in ADHD-friendly format:
 * - Clear labels
 * - Large values
 * - Optional trend indicators
 * - Sparkline visualizations
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Activity } from 'lucide-react';
import { StatCard, AccentStatCard } from '@/components/stat-card';

describe('StatCard', () => {
  describe('Basic rendering', () => {
    it('renders label and value', () => {
      render(<StatCard label="Active Tasks" value={5} />);

      expect(screen.getByText('Active Tasks')).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('renders string values', () => {
      render(<StatCard label="Status" value="Active" />);

      expect(screen.getByText('Active')).toBeInTheDocument();
    });

    it('renders with icon', () => {
      render(<StatCard label="Activity" value={42} icon={Activity} />);

      // Icon should be rendered (as svg)
      const icon = document.querySelector('svg');
      expect(icon).toBeInTheDocument();
    });
  });

  describe('Trend indicators', () => {
    it('renders upward trend', () => {
      render(
        <StatCard
          label="Tasks"
          value={10}
          trend={{ value: 25, direction: 'up' }}
        />
      );

      expect(screen.getByText('25%')).toBeInTheDocument();
    });

    it('renders downward trend', () => {
      render(
        <StatCard
          label="Tasks"
          value={10}
          trend={{ value: 15, direction: 'down' }}
        />
      );

      expect(screen.getByText('15%')).toBeInTheDocument();
    });

    it('renders neutral trend', () => {
      render(
        <StatCard
          label="Tasks"
          value={10}
          trend={{ value: 0, direction: 'neutral' }}
        />
      );

      expect(screen.getByText('0%')).toBeInTheDocument();
    });
  });

  describe('Sparkline', () => {
    it('renders sparkline when data provided', () => {
      const data = [1, 2, 3, 4, 5];
      render(<StatCard label="Activity" value={5} sparklineData={data} />);

      // SVG sparkline should be rendered
      const svg = document.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });

    it('does not render sparkline when no data', () => {
      const { container } = render(<StatCard label="Activity" value={5} />);

      // Should only have icon SVG if no sparkline
      const svgs = container.querySelectorAll('svg');
      expect(svgs.length).toBeLessThanOrEqual(1); // Only icon if present
    });
  });

  describe('Custom className', () => {
    it('applies custom className', () => {
      const { container } = render(
        <StatCard label="Test" value={1} className="custom-class" />
      );

      expect(container.firstChild).toHaveClass('custom-class');
    });
  });
});

describe('AccentStatCard', () => {
  it('renders with default blue accent', () => {
    const { container } = render(<AccentStatCard label="Test" value={1} />);

    expect(container.firstChild).toHaveClass('border-l-4');
  });

  it('renders with different accent colors', () => {
    const colors = ['blue', 'green', 'amber', 'red', 'cyan', 'purple'] as const;

    colors.forEach((color) => {
      const { container } = render(
        <AccentStatCard key={color} label="Test" value={1} accentColor={color} />
      );

      expect(container.firstChild).toHaveClass('border-l-4');
    });
  });
});
