"""
Native Push Token Handler - Expo/FCM/APNs Token Registration and Delivery

Handles native push tokens from the Expo mobile wrapper application.
Supports:
- Expo Push Token (managed service)
- FCM (Firebase Cloud Messaging) for Android
- APNs (Apple Push Notification service) for iOS

This complements the Web Push system by enabling native mobile push
notifications with richer features (badge, sounds, background delivery).
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any
import sqlite3
import asyncio
import aiohttp

from tools.mobile import get_connection, PROJECT_ROOT, DB_PATH


# =============================================================================
# Constants
# =============================================================================

# Expo Push API endpoint
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# Token types
TOKEN_TYPE_EXPO = "expo"
TOKEN_TYPE_FCM = "fcm"
TOKEN_TYPE_APNS = "apns"

VALID_TOKEN_TYPES = {TOKEN_TYPE_EXPO, TOKEN_TYPE_FCM, TOKEN_TYPE_APNS}


# =============================================================================
# Database Schema Migration
# =============================================================================


def ensure_native_token_columns() -> None:
    """
    Ensure native token columns exist in push_subscriptions table.

    This is a migration-safe approach that checks for column existence
    before attempting to add them.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(push_subscriptions)")
    columns = {row["name"] for row in cursor.fetchall()}

    # Add missing columns
    new_columns = [
        ("expo_token", "TEXT"),
        ("fcm_token", "TEXT"),
        ("apns_token", "TEXT"),
        ("device_info", "TEXT"),  # JSON string with device details
    ]

    for col_name, col_type in new_columns:
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE push_subscriptions ADD COLUMN {col_name} {col_type}")
            print(f"Added column: {col_name}")

    conn.commit()
    conn.close()


# Ensure columns exist on module load
ensure_native_token_columns()


# =============================================================================
# Token Registration
# =============================================================================


async def register_native_token(
    user_id: str,
    token: str,
    token_type: str,
    device_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Register a native push token for a user.

    Args:
        user_id: User identifier
        token: The push token string (Expo/FCM/APNs)
        token_type: Type of token ('expo', 'fcm', 'apns')
        device_info: Optional device information dict

    Returns:
        {
            "success": True,
            "subscription_id": str,
            "reactivated": bool  # True if existing subscription was reactivated
        }
        or
        {
            "success": False,
            "error": str
        }
    """
    if token_type not in VALID_TOKEN_TYPES:
        return {
            "success": False,
            "error": f"Invalid token type: {token_type}. Must be one of: {VALID_TOKEN_TYPES}",
        }

    if not token:
        return {"success": False, "error": "Token cannot be empty"}

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Check if token already exists
        token_column = f"{token_type}_token"
        cursor.execute(
            f"SELECT id, is_active FROM push_subscriptions WHERE {token_column} = ?",
            (token,),
        )
        existing = cursor.fetchone()

        if existing:
            # Reactivate if inactive, update last_used_at
            subscription_id = existing["id"]
            was_inactive = not existing["is_active"]

            cursor.execute(
                """
                UPDATE push_subscriptions
                SET is_active = TRUE,
                    last_used_at = CURRENT_TIMESTAMP,
                    device_info = ?,
                    user_id = ?
                WHERE id = ?
                """,
                (json.dumps(device_info) if device_info else None, user_id, subscription_id),
            )
            conn.commit()

            return {
                "success": True,
                "subscription_id": subscription_id,
                "reactivated": was_inactive,
            }

        # Create new subscription
        subscription_id = str(uuid.uuid4())

        # Determine device type from token type or device_info
        device_type = "mobile"
        if device_info:
            platform = device_info.get("platform", "").lower()
            if platform == "ios":
                device_type = "ios"
            elif platform == "android":
                device_type = "android"

        cursor.execute(
            f"""
            INSERT INTO push_subscriptions (
                id, user_id, endpoint, p256dh_key, auth_key,
                device_name, device_type, {token_column}, device_info,
                created_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, TRUE)
            """,
            (
                subscription_id,
                user_id,
                f"native:{token_type}:{token[:20]}",  # Pseudo-endpoint for compatibility
                "",  # p256dh not used for native
                "",  # auth not used for native
                device_info.get("model", "Mobile Device") if device_info else "Mobile Device",
                device_type,
                token,
                json.dumps(device_info) if device_info else None,
            ),
        )
        conn.commit()

        return {"success": True, "subscription_id": subscription_id, "reactivated": False}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


async def unregister_native_token(
    token: str,
    token_type: str | None = None,
) -> dict[str, Any]:
    """
    Unregister (deactivate) a native push token.

    Args:
        token: The push token to unregister
        token_type: Optional token type for faster lookup

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        if token_type:
            token_column = f"{token_type}_token"
            cursor.execute(
                f"UPDATE push_subscriptions SET is_active = FALSE WHERE {token_column} = ?",
                (token,),
            )
        else:
            # Search all token columns
            cursor.execute(
                """
                UPDATE push_subscriptions
                SET is_active = FALSE
                WHERE expo_token = ? OR fcm_token = ? OR apns_token = ?
                """,
                (token, token, token),
            )

        conn.commit()

        if cursor.rowcount == 0:
            return {"success": False, "error": "Token not found"}

        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


async def get_native_tokens(
    user_id: str,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """
    Get all native tokens for a user.

    Returns:
        List of subscription dicts with native token info
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        query = """
            SELECT id, user_id, device_name, device_type,
                   expo_token, fcm_token, apns_token, device_info,
                   created_at, last_used_at, is_active
            FROM push_subscriptions
            WHERE user_id = ?
              AND (expo_token IS NOT NULL OR fcm_token IS NOT NULL OR apns_token IS NOT NULL)
        """

        if active_only:
            query += " AND is_active = TRUE"

        cursor.execute(query, (user_id,))
        rows = cursor.fetchall()

        tokens = []
        for row in rows:
            token_dict = dict(row)
            if token_dict.get("device_info"):
                try:
                    token_dict["device_info"] = json.loads(token_dict["device_info"])
                except json.JSONDecodeError:
                    pass
            tokens.append(token_dict)

        return tokens

    finally:
        conn.close()


# =============================================================================
# Push Sending
# =============================================================================


async def send_native_push(
    token: str,
    token_type: str,
    notification: dict[str, Any],
) -> dict[str, Any]:
    """
    Send a push notification to a native token.

    Args:
        token: The push token
        token_type: Type of token ('expo', 'fcm', 'apns')
        notification: Notification payload with:
            - title: Notification title
            - body: Notification body
            - data: Optional data payload
            - badge: Optional badge count
            - sound: Optional sound name
            - priority: Optional priority level

    Returns:
        {"success": True, "receipt_id": str} or
        {"success": False, "error": str, "should_unregister": bool}
    """
    if token_type == TOKEN_TYPE_EXPO:
        return await _send_expo_push(token, notification)
    elif token_type == TOKEN_TYPE_FCM:
        return await _send_fcm_push(token, notification)
    elif token_type == TOKEN_TYPE_APNS:
        return await _send_apns_push(token, notification)
    else:
        return {"success": False, "error": f"Unsupported token type: {token_type}"}


async def _send_expo_push(
    token: str,
    notification: dict[str, Any],
) -> dict[str, Any]:
    """
    Send push notification via Expo Push Service.

    Expo handles FCM/APNs under the hood, making this the simplest option.
    """
    message = {
        "to": token,
        "title": notification.get("title", "DexAI"),
        "body": notification.get("body", ""),
        "data": notification.get("data", {}),
        "sound": notification.get("sound", "default"),
        "priority": "high" if notification.get("priority", 5) >= 8 else "default",
    }

    # Add badge if specified
    if "badge" in notification:
        message["badge"] = notification["badge"]

    # Add category for actionable notifications
    if "category" in notification.get("data", {}):
        message["categoryId"] = notification["data"]["category"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                EXPO_PUSH_URL,
                json=message,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            ) as response:
                result = await response.json()

                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"Expo API error: {response.status}",
                        "should_unregister": False,
                    }

                # Check for errors in response
                if "data" in result:
                    ticket = result["data"]
                    if isinstance(ticket, list):
                        ticket = ticket[0] if ticket else {}

                    status = ticket.get("status")

                    if status == "ok":
                        return {
                            "success": True,
                            "receipt_id": ticket.get("id"),
                        }
                    elif status == "error":
                        error_type = ticket.get("details", {}).get("error", "")
                        should_unregister = error_type in [
                            "DeviceNotRegistered",
                            "InvalidCredentials",
                        ]
                        return {
                            "success": False,
                            "error": ticket.get("message", "Unknown error"),
                            "should_unregister": should_unregister,
                        }

                return {
                    "success": False,
                    "error": "Unexpected response format",
                    "should_unregister": False,
                }

    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "should_unregister": False,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "should_unregister": False,
        }


async def _send_fcm_push(
    token: str,
    notification: dict[str, Any],
) -> dict[str, Any]:
    """
    Send push notification via Firebase Cloud Messaging.

    Requires FCM_SERVER_KEY environment variable.
    For production, consider using Firebase Admin SDK.
    """
    fcm_key = os.environ.get("FCM_SERVER_KEY")
    if not fcm_key:
        return {
            "success": False,
            "error": "FCM_SERVER_KEY not configured",
            "should_unregister": False,
        }

    message = {
        "to": token,
        "notification": {
            "title": notification.get("title", "DexAI"),
            "body": notification.get("body", ""),
            "sound": notification.get("sound", "default"),
        },
        "data": notification.get("data", {}),
        "priority": "high" if notification.get("priority", 5) >= 8 else "normal",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://fcm.googleapis.com/fcm/send",
                json=message,
                headers={
                    "Authorization": f"key={fcm_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                result = await response.json()

                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"FCM API error: {response.status}",
                        "should_unregister": False,
                    }

                if result.get("success") == 1:
                    return {
                        "success": True,
                        "receipt_id": result.get("message_id"),
                    }

                # Check for unregistered device
                error = result.get("results", [{}])[0].get("error", "")
                should_unregister = error in [
                    "NotRegistered",
                    "InvalidRegistration",
                ]

                return {
                    "success": False,
                    "error": error or "FCM delivery failed",
                    "should_unregister": should_unregister,
                }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "should_unregister": False,
        }


async def _send_apns_push(
    token: str,
    notification: dict[str, Any],
) -> dict[str, Any]:
    """
    Send push notification via Apple Push Notification service.

    For direct APNs, requires APNs auth key and proper setup.
    In most cases, Expo Push or FCM should be used instead.
    """
    # APNs direct integration is complex and requires:
    # - APNs Auth Key (.p8 file)
    # - Key ID
    # - Team ID
    # - HTTP/2 connection

    # For simplicity, recommend using Expo Push which handles APNs
    return {
        "success": False,
        "error": "Direct APNs not implemented. Use Expo Push tokens instead.",
        "should_unregister": False,
    }


# =============================================================================
# Batch Sending
# =============================================================================


async def send_native_push_batch(
    user_id: str,
    notification: dict[str, Any],
) -> dict[str, Any]:
    """
    Send push notification to all native tokens for a user.

    Args:
        user_id: User identifier
        notification: Notification payload

    Returns:
        {
            "success": True,
            "sent": int,
            "failed": int,
            "results": list
        }
    """
    tokens = await get_native_tokens(user_id, active_only=True)

    if not tokens:
        return {
            "success": False,
            "error": "No active native tokens for user",
            "sent": 0,
            "failed": 0,
        }

    results = []
    sent = 0
    failed = 0
    to_unregister = []

    for sub in tokens:
        # Determine token type and value
        if sub.get("expo_token"):
            token = sub["expo_token"]
            token_type = TOKEN_TYPE_EXPO
        elif sub.get("fcm_token"):
            token = sub["fcm_token"]
            token_type = TOKEN_TYPE_FCM
        elif sub.get("apns_token"):
            token = sub["apns_token"]
            token_type = TOKEN_TYPE_APNS
        else:
            continue

        result = await send_native_push(token, token_type, notification)
        result["subscription_id"] = sub["id"]
        result["token_type"] = token_type
        results.append(result)

        if result.get("success"):
            sent += 1
        else:
            failed += 1
            if result.get("should_unregister"):
                to_unregister.append((token, token_type))

    # Unregister invalid tokens
    for token, token_type in to_unregister:
        await unregister_native_token(token, token_type)

    return {
        "success": sent > 0,
        "sent": sent,
        "failed": failed,
        "results": results,
    }


# =============================================================================
# CLI Interface
# =============================================================================


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Native push token management and testing"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Register token
    register_parser = subparsers.add_parser("register", help="Register a native token")
    register_parser.add_argument("--user-id", required=True, help="User ID")
    register_parser.add_argument("--token", required=True, help="Push token")
    register_parser.add_argument(
        "--type",
        choices=["expo", "fcm", "apns"],
        required=True,
        help="Token type",
    )

    # List tokens
    list_parser = subparsers.add_parser("list", help="List native tokens for user")
    list_parser.add_argument("--user-id", required=True, help="User ID")

    # Send test
    send_parser = subparsers.add_parser("send", help="Send test notification")
    send_parser.add_argument("--user-id", required=True, help="User ID")
    send_parser.add_argument("--title", default="Test", help="Notification title")
    send_parser.add_argument("--body", default="Test notification", help="Body")

    args = parser.parse_args()

    if args.command == "register":
        result = asyncio.run(
            register_native_token(
                user_id=args.user_id,
                token=args.token,
                token_type=args.type,
            )
        )
        print(json.dumps(result, indent=2))

    elif args.command == "list":
        tokens = asyncio.run(get_native_tokens(args.user_id))
        for t in tokens:
            print(json.dumps(t, indent=2, default=str))

    elif args.command == "send":
        result = asyncio.run(
            send_native_push_batch(
                user_id=args.user_id,
                notification={"title": args.title, "body": args.body},
            )
        )
        print(json.dumps(result, indent=2))
