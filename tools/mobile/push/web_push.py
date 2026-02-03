"""
Tool: Web Push Notification Sender
Purpose: Send Web Push notifications using VAPID

Usage:
    # Generate VAPID keys (one-time setup)
    python -m tools.mobile.push.web_push generate-keys

    # Send test notification
    python -m tools.mobile.push.web_push send --subscription-id sub_123 --title "Test" --body "Hello"

    # Get public key
    python -m tools.mobile.push.web_push get-public-key

Dependencies:
    pip install pywebpush cryptography
"""

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Try to import cryptography for key generation
try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.backends import default_backend
    import base64
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# Try to import pywebpush
try:
    from pywebpush import webpush, WebPushException
    HAS_WEBPUSH = True
except ImportError:
    HAS_WEBPUSH = False

from tools.mobile import get_connection, PROJECT_ROOT, CONFIG_PATH
from tools.mobile.models import PushSubscription, DeliveryResult


# Load VAPID config from environment or config file
def _load_vapid_config() -> dict:
    """Load VAPID configuration."""
    config = {
        "public_key": os.environ.get("VAPID_PUBLIC_KEY", ""),
        "private_key": os.environ.get("VAPID_PRIVATE_KEY", ""),
        "subject": os.environ.get("VAPID_SUBJECT", "mailto:notifications@dexai.app"),
    }

    # Try loading from config file if not in env
    config_file = CONFIG_PATH / "mobile_push.yaml"
    if config_file.exists() and (not config["public_key"] or not config["private_key"]):
        try:
            import yaml
            with open(config_file) as f:
                file_config = yaml.safe_load(f) or {}
                vapid_config = file_config.get("vapid", {})
                if not config["public_key"]:
                    config["public_key"] = vapid_config.get("public_key", "")
                if not config["private_key"]:
                    config["private_key"] = vapid_config.get("private_key", "")
                if vapid_config.get("subject"):
                    config["subject"] = vapid_config["subject"]
        except Exception:
            pass

    return config


def generate_vapid_keys() -> dict:
    """
    Generate new VAPID key pair for Web Push.

    Returns:
        {"success": True, "public_key": str, "private_key": str}
        or {"success": False, "error": str}

    Note:
        Store the private key securely in environment variables or vault.
        The public key is shared with clients for subscription.
    """
    if not HAS_CRYPTO:
        return {
            "success": False,
            "error": "cryptography library not installed. Run: pip install cryptography",
        }

    try:
        # Generate EC key pair using P-256 curve (required for Web Push)
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        public_key = private_key.public_key()

        # Export private key in PEM format
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        # Export public key in uncompressed point format for Web Push
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )

        # URL-safe base64 encode without padding
        public_b64 = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode("ascii")

        # Also encode private key for VAPID claims
        private_numbers = private_key.private_numbers()
        private_bytes = private_numbers.private_value.to_bytes(32, byteorder="big")
        private_b64 = base64.urlsafe_b64encode(private_bytes).rstrip(b"=").decode("ascii")

        return {
            "success": True,
            "public_key": public_b64,
            "private_key": private_b64,
            "private_key_pem": private_pem,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_vapid_public_key() -> str:
    """
    Get the server's VAPID public key for client subscription.

    Returns:
        The public key string (URL-safe base64) or empty string if not configured.
    """
    config = _load_vapid_config()
    return config.get("public_key", "")


def _get_subscription(subscription_id: str) -> PushSubscription | None:
    """Get subscription from database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM push_subscriptions WHERE id = ? AND is_active = TRUE",
        (subscription_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return PushSubscription.from_dict(dict(row))


async def send_push(
    subscription_id: str,
    title: str,
    body: str | None = None,
    data: dict | None = None,
    icon_url: str | None = None,
    action_url: str | None = None,
    ttl: int = 86400,
    tag: str | None = None,
    require_interaction: bool = False,
    silent: bool = False,
) -> dict:
    """
    Send a Web Push notification.

    Args:
        subscription_id: Database ID of the subscription
        title: Notification title
        body: Notification body text
        data: Additional data payload for click handling
        icon_url: URL to notification icon
        action_url: URL to open when notification is clicked
        ttl: Time to live in seconds (default 24 hours)
        tag: Tag for notification grouping (replaces existing with same tag)
        require_interaction: If True, notification won't auto-dismiss
        silent: If True, notification won't make sound

    Returns:
        {"success": True, "delivery_id": str} or
        {"success": False, "error": str, "should_unsubscribe": bool}
    """
    if not HAS_WEBPUSH:
        return {
            "success": False,
            "error": "pywebpush library not installed. Run: pip install pywebpush",
            "should_unsubscribe": False,
        }

    # Get subscription from database
    subscription = _get_subscription(subscription_id)
    if not subscription:
        return {
            "success": False,
            "error": "Subscription not found or inactive",
            "should_unsubscribe": False,
        }

    # Load VAPID config
    vapid_config = _load_vapid_config()
    if not vapid_config["public_key"] or not vapid_config["private_key"]:
        return {
            "success": False,
            "error": "VAPID keys not configured. Generate with: python -m tools.mobile.push.web_push generate-keys",
            "should_unsubscribe": False,
        }

    # Build notification payload
    payload = {
        "title": title,
        "body": body,
        "icon": icon_url or "/icons/dex-192.png",
        "badge": "/icons/badge-72.png",
        "data": {
            **(data or {}),
            "action_url": action_url or "/",
        },
        "tag": tag,
        "requireInteraction": require_interaction,
        "silent": silent,
    }

    delivery_id = f"del_{uuid.uuid4().hex[:12]}"

    try:
        # Send push notification
        response = webpush(
            subscription_info=subscription.get_subscription_info(),
            data=json.dumps(payload),
            vapid_private_key=vapid_config["private_key"],
            vapid_claims={"sub": vapid_config["subject"]},
            ttl=ttl,
        )

        # Update last_used_at
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE push_subscriptions SET last_used_at = ? WHERE id = ?",
            (datetime.now().isoformat(), subscription_id),
        )
        conn.commit()
        conn.close()

        return {
            "success": True,
            "delivery_id": delivery_id,
            "status_code": response.status_code if hasattr(response, 'status_code') else 201,
        }

    except WebPushException as e:
        error_info = {
            "success": False,
            "error": str(e),
            "should_unsubscribe": False,
        }

        # Check for 410 Gone (endpoint invalid)
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code == 410:
                error_info["should_unsubscribe"] = True
                error_info["error"] = "Subscription expired or invalid (410 Gone)"

                # Mark subscription as inactive
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE push_subscriptions SET is_active = FALSE WHERE id = ?",
                    (subscription_id,),
                )
                conn.commit()
                conn.close()

            elif e.response.status_code == 429:
                # Rate limited
                retry_after = e.response.headers.get("Retry-After", 60)
                error_info["retry_after"] = int(retry_after)
                error_info["error"] = f"Rate limited. Retry after {retry_after} seconds"

        return error_info

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "should_unsubscribe": False,
        }


async def send_batch(
    subscription_id: str,
    notifications: list[dict],
) -> dict:
    """
    Send a batched notification summarizing multiple items.

    Creates a single summary notification instead of multiple interruptions.

    Args:
        subscription_id: Database ID of the subscription
        notifications: List of notification dicts with title, body, category

    Returns:
        {"success": True, "delivery_id": str, "count": int}
    """
    if not notifications:
        return {"success": True, "delivery_id": None, "count": 0}

    # Create summary notification
    count = len(notifications)
    categories = set(n.get("category", "notification") for n in notifications)

    if count == 1:
        # Single notification - send as-is
        n = notifications[0]
        return await send_push(
            subscription_id=subscription_id,
            title=n.get("title", "Notification"),
            body=n.get("body"),
            data=n.get("data"),
            action_url=n.get("action_url"),
            tag=n.get("batch_key"),
        )

    # Multiple notifications - create summary
    category_name = categories.pop() if len(categories) == 1 else "items"

    # ADHD-friendly: Clear, concise summary
    title = f"{count} {category_name}s ready for you"
    body = _create_batch_body(notifications)

    return await send_push(
        subscription_id=subscription_id,
        title=title,
        body=body,
        data={
            "notification_ids": [n.get("id") for n in notifications if n.get("id")],
            "is_batch": True,
            "count": count,
        },
        action_url="/notifications",  # Link to notification center
        tag=f"batch_{category_name}",
    )


def _create_batch_body(notifications: list[dict]) -> str:
    """Create a summary body for batched notifications."""
    # Show first 2-3 items
    preview_count = min(3, len(notifications))
    previews = []

    for n in notifications[:preview_count]:
        title = n.get("title", "")
        if len(title) > 30:
            title = title[:27] + "..."
        previews.append(f"- {title}")

    body = "\n".join(previews)

    remaining = len(notifications) - preview_count
    if remaining > 0:
        body += f"\n...and {remaining} more"

    return body


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Web Push notification tools")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Generate keys
    gen_parser = subparsers.add_parser("generate-keys", help="Generate VAPID key pair")

    # Get public key
    pub_parser = subparsers.add_parser("get-public-key", help="Get VAPID public key")

    # Send notification
    send_parser = subparsers.add_parser("send", help="Send test notification")
    send_parser.add_argument("--subscription-id", "-s", required=True, help="Subscription ID")
    send_parser.add_argument("--title", "-t", required=True, help="Notification title")
    send_parser.add_argument("--body", "-b", help="Notification body")
    send_parser.add_argument("--url", "-u", help="Action URL")

    args = parser.parse_args()

    if args.command == "generate-keys":
        result = generate_vapid_keys()
        if result["success"]:
            print("VAPID Keys Generated Successfully")
            print("-" * 40)
            print(f"Public Key:  {result['public_key']}")
            print(f"Private Key: {result['private_key']}")
            print("-" * 40)
            print("\nAdd to your .env file:")
            print(f"VAPID_PUBLIC_KEY={result['public_key']}")
            print(f"VAPID_PRIVATE_KEY={result['private_key']}")
            print("VAPID_SUBJECT=mailto:notifications@yourdomain.com")
        else:
            print(f"Error: {result['error']}")

    elif args.command == "get-public-key":
        key = get_vapid_public_key()
        if key:
            print(f"VAPID Public Key: {key}")
        else:
            print("VAPID public key not configured")
            print("Run: python -m tools.mobile.push.web_push generate-keys")

    elif args.command == "send":
        result = asyncio.run(send_push(
            subscription_id=args.subscription_id,
            title=args.title,
            body=args.body,
            action_url=args.url,
        ))
        if result["success"]:
            print(f"Notification sent! Delivery ID: {result['delivery_id']}")
        else:
            print(f"Failed to send: {result['error']}")
            if result.get("should_unsubscribe"):
                print("Note: Subscription should be removed (endpoint invalid)")

    else:
        parser.print_help()
