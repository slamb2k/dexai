/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Core Colors
        bg: {
          primary: '#0a0a0f',
          surface: '#12121a',
          elevated: '#1a1a2e',
          input: '#0f0f16',
        },
        // Accent Colors
        accent: {
          primary: '#3b82f6',
          glow: '#60a5fa',
          secondary: '#06b6d4',
        },
        // Status Colors
        status: {
          success: '#10b981',
          warning: '#f59e0b',
          error: '#ef4444',
          info: '#3b82f6',
        },
        // Text Colors
        text: {
          primary: '#f8fafc',
          secondary: '#94a3b8',
          muted: '#64748b',
          disabled: '#475569',
        },
        // Border Colors
        border: {
          default: '#1e293b',
          focus: '#3b82f6',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        'page-title': ['24px', { lineHeight: '32px', fontWeight: '600' }],
        'section-header': ['18px', { lineHeight: '28px', fontWeight: '600' }],
        'card-title': ['16px', { lineHeight: '24px', fontWeight: '500' }],
        'body': ['14px', { lineHeight: '20px', fontWeight: '400' }],
        'caption': ['12px', { lineHeight: '16px', fontWeight: '400' }],
        'code': ['13px', { lineHeight: '20px', fontWeight: '400' }],
      },
      boxShadow: {
        'card': '0 4px 6px -1px rgba(0, 0, 0, 0.3)',
        'glow-blue': '0 0 20px rgba(59, 130, 246, 0.3)',
        'glow-green': '0 0 20px rgba(16, 185, 129, 0.3)',
        'glow-red': '0 0 20px rgba(239, 68, 68, 0.3)',
        'glow-amber': '0 0 20px rgba(245, 158, 11, 0.3)',
        'glow-cyan': '0 0 20px rgba(6, 182, 212, 0.3)',
        'glow-purple': '0 0 20px rgba(168, 85, 247, 0.3)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 8s linear infinite',
        'bounce-subtle': 'bounce-subtle 2s ease-in-out infinite',
        'glow': 'glow 2s ease-in-out infinite',
      },
      keyframes: {
        'bounce-subtle': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-5%)' },
        },
        'glow': {
          '0%, 100%': { opacity: '0.5' },
          '50%': { opacity: '1' },
        },
      },
      borderRadius: {
        'card': '12px',
        'button': '8px',
      },
    },
  },
  plugins: [],
};
