'use client';

/**
 * Push Notification Subscription Component
 *
 * Handles:
 * - Service worker registration
 * - Push permission request with ADHD-friendly explanation
 * - VAPID key fetch
 * - Subscription creation and backend registration
 *
 * ADHD-Friendly Design:
 * - Clear, non-pushy permission explanation
 * - No guilt if user declines
 * - Easy to understand what they're agreeing to
 */

import { useEffect, useState, useCallback } from 'react';
import { Bell, BellOff, Check, AlertCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface PushSubscriptionProps {
  onSubscribed?: (subscriptionId: string) => void;
  onUnsubscribed?: () => void;
  onError?: (error: Error) => void;
  userId?: string;
  className?: string;
}

type PermissionState = 'prompt' | 'granted' | 'denied' | 'unsupported' | 'loading';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

export function PushSubscription({
  onSubscribed,
  onUnsubscribed,
  onError,
  userId = 'default',
  className,
}: PushSubscriptionProps) {
  const [permissionState, setPermissionState] = useState<PermissionState>('loading');
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [subscriptionId, setSubscriptionId] = useState<string | null>(null);

  // Check current state on mount
  useEffect(() => {
    checkPushSupport();
  }, []);

  const checkPushSupport = async () => {
    // Check if push is supported
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      setPermissionState('unsupported');
      return;
    }

    // Check current permission state
    const permission = Notification.permission;
    setPermissionState(permission as PermissionState);

    // If granted, check if we have an active subscription
    if (permission === 'granted') {
      await checkExistingSubscription();
    }
  };

  const checkExistingSubscription = async () => {
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();

      if (subscription) {
        setIsSubscribed(true);
        // Optionally verify with backend
      }
    } catch (e) {
      console.error('Error checking subscription:', e);
    }
  };

  const subscribe = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // 1. Request notification permission
      const permission = await Notification.requestPermission();
      setPermissionState(permission as PermissionState);

      if (permission !== 'granted') {
        // User declined - no guilt, just inform
        setError(null);
        setIsLoading(false);
        return;
      }

      // 2. Register service worker if needed
      let registration = await navigator.serviceWorker.getRegistration();
      if (!registration) {
        registration = await navigator.serviceWorker.register('/sw.js');
        await navigator.serviceWorker.ready;
      }

      // 3. Get VAPID public key from backend
      const vapidResponse = await fetch(`${API_URL}/api/push/vapid-key`, {
        credentials: 'include',
      });

      if (!vapidResponse.ok) {
        throw new Error('Failed to get VAPID key');
      }

      const { public_key: vapidPublicKey } = await vapidResponse.json();

      if (!vapidPublicKey) {
        throw new Error('VAPID key not configured on server');
      }

      // 4. Convert VAPID key to Uint8Array
      const applicationServerKey = urlBase64ToUint8Array(vapidPublicKey);

      // 5. Subscribe to push
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey,
      });

      // 6. Get subscription details
      const subscriptionJson = subscription.toJSON();
      const p256dh = subscriptionJson.keys?.p256dh || '';
      const auth = subscriptionJson.keys?.auth || '';

      // 7. Register with backend
      const registerResponse = await fetch(
        `${API_URL}/api/push/subscribe?user_id=${userId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            endpoint: subscription.endpoint,
            p256dh,
            auth,
            device_name: getDeviceName(),
            device_type: 'web',
            browser: getBrowserName(),
          }),
        }
      );

      if (!registerResponse.ok) {
        throw new Error('Failed to register subscription with server');
      }

      const { subscription_id } = await registerResponse.json();

      setIsSubscribed(true);
      setSubscriptionId(subscription_id);
      onSubscribed?.(subscription_id);
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : 'Failed to subscribe';
      setError(errorMessage);
      onError?.(e instanceof Error ? e : new Error(errorMessage));
    } finally {
      setIsLoading(false);
    }
  }, [userId, onSubscribed, onError]);

  const unsubscribe = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Unsubscribe from push
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();

      if (subscription) {
        await subscription.unsubscribe();
      }

      // Notify backend if we have a subscription ID
      if (subscriptionId) {
        await fetch(`${API_URL}/api/push/subscribe/${subscriptionId}`, {
          method: 'DELETE',
          credentials: 'include',
        });
      }

      setIsSubscribed(false);
      setSubscriptionId(null);
      onUnsubscribed?.();
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : 'Failed to unsubscribe';
      setError(errorMessage);
      onError?.(e instanceof Error ? e : new Error(errorMessage));
    } finally {
      setIsLoading(false);
    }
  }, [subscriptionId, onUnsubscribed, onError]);

  // Render based on state
  if (permissionState === 'loading') {
    return (
      <div className={cn('flex items-center gap-2 text-text-muted', className)}>
        <Loader2 className="animate-spin" size={20} />
        <span>Checking notification status...</span>
      </div>
    );
  }

  if (permissionState === 'unsupported') {
    return (
      <div className={cn('card p-4 bg-bg-elevated', className)}>
        <div className="flex items-start gap-3">
          <BellOff className="text-text-muted mt-0.5" size={20} />
          <div>
            <p className="text-body text-text-primary">
              Push notifications not supported
            </p>
            <p className="text-caption text-text-muted mt-1">
              Your browser doesn't support push notifications. Try using Chrome, Firefox, or Edge.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (permissionState === 'denied') {
    return (
      <div className={cn('card p-4 bg-bg-elevated', className)}>
        <div className="flex items-start gap-3">
          <BellOff className="text-amber-500 mt-0.5" size={20} />
          <div>
            <p className="text-body text-text-primary">
              Notifications are blocked
            </p>
            <p className="text-caption text-text-muted mt-1">
              You've blocked notifications for this site. To enable them, update your browser settings.
            </p>
            <p className="text-caption text-text-muted mt-2">
              No pressure - notifications are completely optional!
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (isSubscribed) {
    return (
      <div className={cn('card p-4', className)}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-full bg-green-500/10">
              <Check className="text-green-500" size={20} />
            </div>
            <div>
              <p className="text-body text-text-primary">
                Notifications enabled
              </p>
              <p className="text-caption text-text-muted mt-1">
                You'll receive gentle reminders when things need your attention.
                Customize your preferences below.
              </p>
            </div>
          </div>
          <button
            onClick={unsubscribe}
            disabled={isLoading}
            className="btn btn-ghost text-caption"
          >
            {isLoading ? (
              <Loader2 className="animate-spin" size={16} />
            ) : (
              'Disable'
            )}
          </button>
        </div>
      </div>
    );
  }

  // Prompt state - show explanation and subscribe button
  return (
    <div className={cn('card p-4', className)}>
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-full bg-accent-primary/10">
          <Bell className="text-accent-primary" size={20} />
        </div>
        <div className="flex-1">
          <p className="text-body text-text-primary">
            Enable push notifications
          </p>
          <p className="text-caption text-text-muted mt-1">
            Get gentle reminders when tasks need attention or commitments are coming up.
            We respect your focus time and won't interrupt flow states.
          </p>

          {/* ADHD-friendly explanation */}
          <div className="mt-3 p-3 bg-bg-elevated rounded-lg">
            <p className="text-caption text-text-muted">
              <strong>What you'll get:</strong>
            </p>
            <ul className="mt-2 space-y-1 text-caption text-text-muted">
              <li className="flex items-center gap-2">
                <Check size={14} className="text-green-500 shrink-0" />
                Task reminders (batched to reduce interruptions)
              </li>
              <li className="flex items-center gap-2">
                <Check size={14} className="text-green-500 shrink-0" />
                Important deadline alerts
              </li>
              <li className="flex items-center gap-2">
                <Check size={14} className="text-green-500 shrink-0" />
                Flow state protection (won't interrupt deep work)
              </li>
            </ul>
            <p className="mt-2 text-caption text-text-muted">
              You can customize or disable anytime. No guilt, no pressure.
            </p>
          </div>

          {error && (
            <div className="mt-3 flex items-center gap-2 text-red-500 text-caption">
              <AlertCircle size={14} />
              {error}
            </div>
          )}

          <button
            onClick={subscribe}
            disabled={isLoading}
            className="btn btn-primary mt-4 flex items-center gap-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="animate-spin" size={16} />
                Enabling...
              </>
            ) : (
              <>
                <Bell size={16} />
                Enable Notifications
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Convert URL-safe base64 to Uint8Array
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/**
 * Get device name for subscription
 */
function getDeviceName(): string {
  const ua = navigator.userAgent;

  if (/Mobile|Android|iPhone|iPad/.test(ua)) {
    if (/iPhone|iPad/.test(ua)) return 'iOS Device';
    if (/Android/.test(ua)) return 'Android Device';
    return 'Mobile Device';
  }

  if (/Mac/.test(ua)) return 'Mac';
  if (/Win/.test(ua)) return 'Windows';
  if (/Linux/.test(ua)) return 'Linux';

  return 'Desktop';
}

/**
 * Get browser name for subscription
 */
function getBrowserName(): string {
  const ua = navigator.userAgent;

  if (/Firefox/.test(ua)) return 'firefox';
  if (/Edg/.test(ua)) return 'edge';
  if (/Chrome/.test(ua)) return 'chrome';
  if (/Safari/.test(ua)) return 'safari';

  return 'unknown';
}

export default PushSubscription;
