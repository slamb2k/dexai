# DexAI Mobile Assets

This directory contains placeholder assets. Replace these with actual branded assets before building for production.

## Required Assets

| File | Size | Purpose |
|------|------|---------|
| `icon.png` | 1024x1024 | App store icon (iOS/Android) |
| `adaptive-icon.png` | 1024x1024 | Android adaptive icon foreground |
| `splash.png` | 1284x2778 | Splash screen (iPhone 13 Pro Max size) |
| `favicon.png` | 48x48 | Web favicon |
| `notification-icon.png` | 96x96 | Android notification icon (white on transparent) |

## Design Guidelines

### Colors
- Primary: #4F46E5 (Indigo-600)
- Background: #F9FAFB (Gray-50)
- Text: #111827 (Gray-900)

### Style
- Use the Dex avatar/mascot as the main icon element
- Keep designs simple and ADHD-friendly (not overly stimulating)
- Ensure high contrast for accessibility

## Generating Assets

Use Expo's asset generator or create manually:

```bash
# Using Expo CLI
npx expo-optimize --quality 90

# Or use figma/sketch exports
```

## Current Placeholders

The placeholder files are solid color squares in the DexAI primary color (#4F46E5).
These must be replaced before App Store submission.
