"""
Tool: OAuth Manager
Purpose: OAuth 2.0 flows for Google Workspace and Microsoft 365

Handles:
- OAuth authorization URL generation
- Token exchange (auth code -> tokens)
- Token refresh
- Secure token storage in vault
- Scope management per integration level

Usage:
    python tools/office/oauth_manager.py --provider google --action authorize --level 2
    python tools/office/oauth_manager.py --provider microsoft --action exchange --code <code>
    python tools/office/oauth_manager.py --provider google --action refresh --account-id <id>

Dependencies:
    - aiohttp (pip install aiohttp)
    - pyyaml (pip install pyyaml)
"""

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import CONFIG_PATH, get_connection  # noqa: E402
from tools.office.models import IntegrationLevel, OfficeAccount  # noqa: E402


# OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2/token"
MICROSOFT_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"

# Default scopes by level
GOOGLE_SCOPES = {
    IntegrationLevel.READ_ONLY: [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
    IntegrationLevel.COLLABORATIVE: [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
    IntegrationLevel.MANAGED_PROXY: [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
    IntegrationLevel.AUTONOMOUS: [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/contacts",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
}

MICROSOFT_SCOPES = {
    IntegrationLevel.READ_ONLY: [
        "Mail.Read",
        "Calendars.Read",
        "User.Read",
        "offline_access",
    ],
    IntegrationLevel.COLLABORATIVE: [
        "Mail.ReadWrite",
        "Calendars.ReadWrite",
        "User.Read",
        "offline_access",
    ],
    IntegrationLevel.MANAGED_PROXY: [
        "Mail.ReadWrite",
        "Mail.Send",
        "Calendars.ReadWrite",
        "User.Read",
        "offline_access",
    ],
    IntegrationLevel.AUTONOMOUS: [
        "Mail.ReadWrite",
        "Mail.Send",
        "Calendars.ReadWrite",
        "Contacts.ReadWrite",
        "User.Read",
        "offline_access",
    ],
}


def load_oauth_config() -> dict[str, Any]:
    """Load OAuth configuration from args/office_integration.yaml."""
    import yaml

    config_path = CONFIG_PATH / "office_integration.yaml"
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
            return config.get("office_integration", {}).get("platforms", {})
    return {}


def _generate_pkce_pair() -> tuple[str, str]:
    """
    Generate PKCE code verifier and challenge pair per RFC 7636.

    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    import base64
    import hashlib
    import secrets

    # Generate 43 random bytes, base64url-encode
    verifier_bytes = secrets.token_bytes(43)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode("ascii")

    # SHA256 hash the verifier, base64url-encode
    challenge_bytes = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")

    return code_verifier, code_challenge


def get_google_credentials() -> tuple[str, str]:
    """
    Get Google OAuth credentials from environment or vault.

    Returns:
        Tuple of (client_id, client_secret)

    Raises:
        ValueError: If credentials not found
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        # Try vault
        try:
            from tools.security import vault

            result = vault.get_secret("GOOGLE_CLIENT_ID", namespace="oauth")
            if result.get("success"):
                client_id = result["value"]
            result = vault.get_secret("GOOGLE_CLIENT_SECRET", namespace="oauth")
            if result.get("success"):
                client_secret = result["value"]
        except Exception:
            pass

    if not client_id or not client_secret:
        raise ValueError(
            "Google OAuth credentials not found. "
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables "
            "or store them in the vault under the 'oauth' namespace."
        )

    return client_id, client_secret


def get_microsoft_credentials() -> tuple[str, str, str]:
    """
    Get Microsoft OAuth credentials from environment or vault.

    Returns:
        Tuple of (client_id, client_secret, tenant)

    Raises:
        ValueError: If credentials not found
    """
    client_id = os.environ.get("MICROSOFT_CLIENT_ID")
    client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET")
    tenant = os.environ.get("MICROSOFT_TENANT", "common")

    if not client_id or not client_secret:
        # Try vault
        try:
            from tools.security import vault

            result = vault.get_secret("MICROSOFT_CLIENT_ID", namespace="oauth")
            if result.get("success"):
                client_id = result["value"]
            result = vault.get_secret("MICROSOFT_CLIENT_SECRET", namespace="oauth")
            if result.get("success"):
                client_secret = result["value"]
            result = vault.get_secret("MICROSOFT_TENANT", namespace="oauth")
            if result.get("success"):
                tenant = result["value"]
        except Exception:
            pass

    if not client_id or not client_secret:
        raise ValueError(
            "Microsoft OAuth credentials not found. "
            "Set MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET environment variables "
            "or store them in the vault under the 'oauth' namespace."
        )

    return client_id, client_secret, tenant


def get_redirect_uri(provider: str) -> str:
    """Get the OAuth redirect URI for a provider."""
    config = load_oauth_config()
    provider_config = config.get(provider, {}).get("oauth", {})
    return provider_config.get(
        "redirect_uri", f"http://localhost:8080/oauth/{provider}/callback"
    )


def get_scopes_for_level(provider: str, level: IntegrationLevel) -> list[str]:
    """
    Get OAuth scopes required for a given integration level.

    Args:
        provider: 'google' or 'microsoft'
        level: Integration level

    Returns:
        List of OAuth scope strings
    """
    if level == IntegrationLevel.SANDBOXED:
        return []  # No OAuth needed for sandboxed

    if provider == "google":
        return GOOGLE_SCOPES.get(level, GOOGLE_SCOPES[IntegrationLevel.READ_ONLY])
    elif provider == "microsoft":
        return MICROSOFT_SCOPES.get(level, MICROSOFT_SCOPES[IntegrationLevel.READ_ONLY])
    else:
        raise ValueError(f"Unknown provider: {provider}")


def generate_authorization_url(
    provider: str,
    level: IntegrationLevel,
    state: str | None = None,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    """
    Generate OAuth authorization URL for user to grant permissions.

    Args:
        provider: 'google' or 'microsoft'
        level: Desired integration level (determines scopes)
        state: Optional state parameter for CSRF protection
        redirect_uri: Optional override for redirect URI

    Returns:
        dict with authorization URL and state
    """
    if level == IntegrationLevel.SANDBOXED:
        return {
            "success": False,
            "error": "Sandboxed level does not require OAuth",
        }

    if not state:
        state = str(uuid.uuid4())

    # OAUTH-1: Generate PKCE pair per RFC 7636
    code_verifier, code_challenge = _generate_pkce_pair()

    # Embed PKCE verifier in state for stateless retrieval
    try:
        state_dict = json.loads(state) if state else {}
    except (json.JSONDecodeError, TypeError):
        state_dict = {"original_state": state}
    state_dict["code_verifier"] = code_verifier
    state_with_verifier = json.dumps(state_dict)

    scopes = get_scopes_for_level(provider, level)
    redirect = redirect_uri or get_redirect_uri(provider)

    try:
        if provider == "google":
            client_id, _ = get_google_credentials()
            params = {
                "client_id": client_id,
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": " ".join(scopes),
                "state": state_with_verifier,
                "access_type": "offline",  # Get refresh token
                "prompt": "consent",  # Force consent to ensure refresh token
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
            url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

        elif provider == "microsoft":
            client_id, _, tenant = get_microsoft_credentials()
            params = {
                "client_id": client_id,
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": " ".join(scopes),
                "state": state_with_verifier,
                "response_mode": "query",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
            auth_url = MICROSOFT_AUTH_URL.format(tenant=tenant)
            url = f"{auth_url}?{urlencode(params)}"

        else:
            return {"success": False, "error": f"Unknown provider: {provider}"}

        return {
            "success": True,
            "authorization_url": url,
            "state": state_with_verifier,
            "code_verifier": code_verifier,
            "provider": provider,
            "level": level.value,
            "scopes": scopes,
        }

    except ValueError as e:
        return {"success": False, "error": str(e)}


async def exchange_code_for_tokens(
    provider: str,
    code: str,
    redirect_uri: str | None = None,
    code_verifier: str | None = None,
) -> dict[str, Any]:
    """
    Exchange authorization code for access and refresh tokens.

    Args:
        provider: 'google' or 'microsoft'
        code: Authorization code from callback
        redirect_uri: Redirect URI used in authorization
        code_verifier: PKCE code verifier (RFC 7636) for proof of possession

    Returns:
        dict with tokens and user info
    """
    try:
        import aiohttp
    except ImportError:
        return {"success": False, "error": "aiohttp not installed. Run: pip install aiohttp"}

    redirect = redirect_uri or get_redirect_uri(provider)

    try:
        if provider == "google":
            client_id, client_secret = get_google_credentials()
            token_data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
            }
            # OAUTH-1: Include PKCE verifier for proof of possession
            if code_verifier:
                token_data["code_verifier"] = code_verifier

            async with aiohttp.ClientSession() as session:
                # Exchange code for tokens
                async with session.post(GOOGLE_TOKEN_URL, data=token_data) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        return {"success": False, "error": f"Token exchange failed: {error}"}
                    tokens = await resp.json()

                # Get user info
                headers = {"Authorization": f"Bearer {tokens['access_token']}"}
                async with session.get(GOOGLE_USERINFO_URL, headers=headers) as resp:
                    if resp.status == 200:
                        user_info = await resp.json()
                    else:
                        user_info = {}

            return {
                "success": True,
                "provider": "google",
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_in": tokens.get("expires_in", 3600),
                "scope": tokens.get("scope", ""),
                "email": user_info.get("email"),
                "name": user_info.get("name"),
            }

        elif provider == "microsoft":
            client_id, client_secret, tenant = get_microsoft_credentials()
            token_data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
            }
            # OAUTH-1: Include PKCE verifier for proof of possession
            if code_verifier:
                token_data["code_verifier"] = code_verifier

            token_url = MICROSOFT_TOKEN_URL.format(tenant=tenant)

            async with aiohttp.ClientSession() as session:
                # Exchange code for tokens
                async with session.post(token_url, data=token_data) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        return {"success": False, "error": f"Token exchange failed: {error}"}
                    tokens = await resp.json()

                # Get user info
                headers = {"Authorization": f"Bearer {tokens['access_token']}"}
                async with session.get(MICROSOFT_USERINFO_URL, headers=headers) as resp:
                    if resp.status == 200:
                        user_info = await resp.json()
                    else:
                        user_info = {}

            return {
                "success": True,
                "provider": "microsoft",
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_in": tokens.get("expires_in", 3600),
                "scope": tokens.get("scope", ""),
                "email": user_info.get("mail") or user_info.get("userPrincipalName"),
                "name": user_info.get("displayName"),
            }

        else:
            return {"success": False, "error": f"Unknown provider: {provider}"}

    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Token exchange error: {e!s}"}


async def refresh_access_token(
    provider: str,
    refresh_token: str,
) -> dict[str, Any]:
    """
    Refresh an expired access token.

    Args:
        provider: 'google' or 'microsoft'
        refresh_token: Refresh token

    Returns:
        dict with new access token
    """
    try:
        import aiohttp
    except ImportError:
        return {"success": False, "error": "aiohttp not installed"}

    try:
        if provider == "google":
            client_id, client_secret = get_google_credentials()
            token_data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(GOOGLE_TOKEN_URL, data=token_data) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        return {"success": False, "error": f"Token refresh failed: {error}"}
                    tokens = await resp.json()

            return {
                "success": True,
                "provider": "google",
                "access_token": tokens.get("access_token"),
                "expires_in": tokens.get("expires_in", 3600),
            }

        elif provider == "microsoft":
            client_id, client_secret, tenant = get_microsoft_credentials()
            token_data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }

            token_url = MICROSOFT_TOKEN_URL.format(tenant=tenant)

            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=token_data) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        return {"success": False, "error": f"Token refresh failed: {error}"}
                    tokens = await resp.json()

            return {
                "success": True,
                "provider": "microsoft",
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),  # Microsoft may rotate
                "expires_in": tokens.get("expires_in", 3600),
            }

        else:
            return {"success": False, "error": f"Unknown provider: {provider}"}

    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Token refresh error: {e!s}"}


def is_token_expiring_soon(
    provider: str,
    account_id: str,
    threshold_minutes: int = 5,
) -> bool:
    """
    Check if an account's access token is expiring within the threshold.

    Args:
        provider: 'google' or 'microsoft'
        account_id: Account ID
        threshold_minutes: Minutes before expiry to consider "expiring soon"

    Returns:
        True if token expires within threshold or is already expired
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT token_expiry FROM office_accounts WHERE id = ? AND provider = ?",
        (account_id, provider),
    )
    row = cursor.fetchone()
    conn.close()

    if not row or not row["token_expiry"]:
        return True  # No expiry recorded — treat as expiring

    try:
        expiry = datetime.fromisoformat(row["token_expiry"])
    except (TypeError, ValueError):
        return True

    return (expiry - datetime.now()) < timedelta(minutes=threshold_minutes)


async def get_valid_access_token(
    provider: str,
    account_id: str,
) -> str | None:
    """
    Get a valid (non-expired) access token, refreshing proactively if needed.

    Loads the token from storage, checks if it expires within 5 minutes,
    and refreshes proactively if so.  Returns the valid access token or
    None on failure (caller handles).

    Args:
        provider: 'google' or 'microsoft'
        account_id: Account ID

    Returns:
        Valid access token string, or None if refresh fails
    """
    account_result = get_account(account_id)
    if not account_result.get("success"):
        logger.error(
            "get_valid_access_token: account %s not found: %s",
            account_id,
            account_result.get("error"),
        )
        return None

    account = account_result["account"]
    access_token = account.get("access_token")
    refresh_token = account.get("refresh_token")

    # Check if token is expiring soon (within 5 minutes)
    if not is_token_expiring_soon(provider, account_id, threshold_minutes=5):
        # Token still valid — return it directly
        return access_token

    # Token is expiring or expired — attempt proactive refresh
    if not refresh_token:
        logger.warning(
            "get_valid_access_token: token expiring for %s/%s but no refresh token",
            provider,
            account_id,
        )
        return access_token  # Return current token; caller will see 401 if expired

    logger.info(
        "Proactively refreshing expiring token for %s/%s",
        provider,
        account_id,
    )

    result = await refresh_access_token(provider, refresh_token)
    if not result.get("success"):
        logger.error(
            "Proactive token refresh failed for %s/%s: %s",
            provider,
            account_id,
            result.get("error"),
        )
        return None

    # Persist the refreshed token
    new_access = result["access_token"]
    new_refresh = result.get("refresh_token")  # Microsoft may rotate
    expires_in = result.get("expires_in", 3600)
    new_expiry = datetime.now() + timedelta(seconds=expires_in)

    from tools.security import vault

    conn = get_connection()
    cursor = conn.cursor()

    # Encrypt and store new access token
    try:
        vault.set_secret(
            f"office_access_{account_id}",
            new_access,
            namespace="office_tokens",
        )
    except Exception as exc:
        logger.error("Failed to store refreshed access token in vault: %s", exc)

    # Update expiry in database
    cursor.execute(
        "UPDATE office_accounts SET token_expiry = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_expiry.isoformat(), account_id),
    )

    # If provider rotated the refresh token, persist it too
    if new_refresh and new_refresh != refresh_token:
        try:
            vault.set_secret(
                f"office_refresh_{account_id}",
                new_refresh,
                namespace="office_tokens",
            )
        except Exception as exc:
            logger.error("Failed to store rotated refresh token in vault: %s", exc)

    conn.commit()
    conn.close()

    return new_access


def save_account(
    user_id: str,
    provider: str,
    level: IntegrationLevel,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
    scopes: list[str],
    email: str,
    name: str | None = None,
) -> dict[str, Any]:
    """
    Save or update an office account with tokens.

    Tokens are encrypted before storage using the vault.

    Args:
        user_id: DexAI user ID
        provider: 'google' or 'microsoft'
        level: Integration level
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        expires_in: Token expiry in seconds
        scopes: Granted OAuth scopes
        email: User's email address
        name: User's display name

    Returns:
        dict with account ID and status
    """
    from tools.security import vault

    account_id = str(uuid.uuid4())
    token_expiry = datetime.now() + timedelta(seconds=expires_in)

    # Encrypt tokens
    access_encrypted = None
    refresh_encrypted = None

    try:
        # Store tokens in vault with account-specific keys
        vault.set_secret(
            f"office_access_{account_id}",
            access_token,
            namespace="office_tokens",
        )
        access_encrypted = f"vault:office_access_{account_id}"

        if refresh_token:
            vault.set_secret(
                f"office_refresh_{account_id}",
                refresh_token,
                namespace="office_tokens",
            )
            refresh_encrypted = f"vault:office_refresh_{account_id}"
    except Exception as e:
        return {"success": False, "error": f"Failed to encrypt tokens: {e!s}"}

    # Save to database
    conn = get_connection()
    cursor = conn.cursor()

    # Check if account already exists for this user/provider
    cursor.execute(
        "SELECT id FROM office_accounts WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )
    existing = cursor.fetchone()

    if existing:
        # Update existing account
        account_id = existing["id"]
        cursor.execute(
            """
            UPDATE office_accounts SET
                integration_level = ?,
                email_address = ?,
                access_token_encrypted = ?,
                refresh_token_encrypted = ?,
                token_expiry = ?,
                scopes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                level.value,
                email,
                access_encrypted,
                refresh_encrypted,
                token_expiry.isoformat(),
                json.dumps(scopes),
                account_id,
            ),
        )
    else:
        # Insert new account
        cursor.execute(
            """
            INSERT INTO office_accounts
            (id, user_id, provider, integration_level, email_address,
             access_token_encrypted, refresh_token_encrypted, token_expiry, scopes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                user_id,
                provider,
                level.value,
                email,
                access_encrypted,
                refresh_encrypted,
                token_expiry.isoformat(),
                json.dumps(scopes),
            ),
        )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "account_id": account_id,
        "email": email,
        "provider": provider,
        "level": level.value,
    }


def get_account(account_id: str) -> dict[str, Any]:
    """
    Get an office account by ID.

    Args:
        account_id: Account ID

    Returns:
        dict with account data (tokens decrypted)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM office_accounts WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": "Account not found"}

    account = dict(row)

    # Decrypt tokens if stored in vault
    from tools.security import vault

    if account.get("access_token_encrypted", "").startswith("vault:"):
        key = account["access_token_encrypted"].replace("vault:", "")
        result = vault.get_secret(key, namespace="office_tokens")
        if result.get("success"):
            account["access_token"] = result["value"]
        else:
            logger.warning(f"Vault decryption failed for access token (account {account_id}): {result.get('error', 'unknown')}")
            account["access_token"] = None

    if account.get("refresh_token_encrypted", "").startswith("vault:"):
        key = account["refresh_token_encrypted"].replace("vault:", "")
        result = vault.get_secret(key, namespace="office_tokens")
        if result.get("success"):
            account["refresh_token"] = result["value"]
        else:
            logger.warning(f"Vault decryption failed for refresh token (account {account_id}): {result.get('error', 'unknown')}")
            account["refresh_token"] = None

    # Parse scopes
    if account.get("scopes"):
        account["scopes"] = json.loads(account["scopes"])

    # Parse level
    account["integration_level"] = IntegrationLevel(account["integration_level"])

    return {"success": True, "account": account}


def get_accounts_for_user(user_id: str) -> dict[str, Any]:
    """
    Get all office accounts for a user.

    Args:
        user_id: DexAI user ID

    Returns:
        dict with list of accounts (tokens not included)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, user_id, provider, integration_level, email_address,
               token_expiry, scopes, created_at, updated_at
        FROM office_accounts WHERE user_id = ?
        """,
        (user_id,),
    )

    accounts = []
    for row in cursor.fetchall():
        account = dict(row)
        if account.get("scopes"):
            account["scopes"] = json.loads(account["scopes"])
        account["integration_level"] = IntegrationLevel(account["integration_level"])
        accounts.append(account)

    conn.close()

    return {"success": True, "accounts": accounts}


def delete_account(account_id: str) -> dict[str, Any]:
    """
    Delete an office account and its tokens.

    Args:
        account_id: Account ID

    Returns:
        dict with success status
    """
    from tools.security import vault

    conn = get_connection()
    cursor = conn.cursor()

    # Get token keys before deleting
    cursor.execute(
        "SELECT access_token_encrypted, refresh_token_encrypted FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"success": False, "error": "Account not found"}

    # Delete from database
    cursor.execute("DELETE FROM office_accounts WHERE id = ?", (account_id,))
    conn.commit()
    conn.close()

    # Delete tokens from vault
    try:
        if row["access_token_encrypted"] and row["access_token_encrypted"].startswith("vault:"):
            key = row["access_token_encrypted"].replace("vault:", "")
            vault.delete_secret(key, namespace="office_tokens")

        if row["refresh_token_encrypted"] and row["refresh_token_encrypted"].startswith("vault:"):
            key = row["refresh_token_encrypted"].replace("vault:", "")
            vault.delete_secret(key, namespace="office_tokens")
    except Exception:
        pass  # Best effort token cleanup

    return {"success": True, "message": f"Account {account_id} deleted"}


def main():
    parser = argparse.ArgumentParser(description="Office OAuth Manager")
    parser.add_argument(
        "--provider",
        required=True,
        choices=["google", "microsoft"],
        help="OAuth provider",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["authorize", "exchange", "refresh", "status"],
        help="Action to perform",
    )
    parser.add_argument("--level", type=int, default=2, help="Integration level (2-5)")
    parser.add_argument("--code", help="Authorization code (for exchange)")
    parser.add_argument("--account-id", help="Account ID (for refresh)")
    parser.add_argument("--user-id", default="default", help="User ID")

    args = parser.parse_args()

    if args.action == "authorize":
        level = IntegrationLevel(args.level)
        result = generate_authorization_url(args.provider, level)
        if result["success"]:
            print(f"Authorization URL:\n{result['authorization_url']}")
            print(f"\nState: {result['state']}")
            print(f"Scopes: {', '.join(result['scopes'])}")
        else:
            print(f"Error: {result['error']}")
            sys.exit(1)

    elif args.action == "exchange":
        if not args.code:
            print("Error: --code required for exchange")
            sys.exit(1)

        import asyncio

        result = asyncio.run(exchange_code_for_tokens(args.provider, args.code))
        if result["success"]:
            print(f"Token exchange successful!")
            print(f"Email: {result.get('email')}")
            print(f"Name: {result.get('name')}")

            # Save account
            level = IntegrationLevel(args.level)
            save_result = save_account(
                user_id=args.user_id,
                provider=args.provider,
                level=level,
                access_token=result["access_token"],
                refresh_token=result.get("refresh_token"),
                expires_in=result["expires_in"],
                scopes=result.get("scope", "").split(),
                email=result["email"],
                name=result.get("name"),
            )
            if save_result["success"]:
                print(f"Account saved: {save_result['account_id']}")
            else:
                print(f"Warning: Failed to save account: {save_result['error']}")
        else:
            print(f"Error: {result['error']}")
            sys.exit(1)

    elif args.action == "refresh":
        if not args.account_id:
            print("Error: --account-id required for refresh")
            sys.exit(1)

        account_result = get_account(args.account_id)
        if not account_result["success"]:
            print(f"Error: {account_result['error']}")
            sys.exit(1)

        account = account_result["account"]
        refresh_token = account.get("refresh_token")
        if not refresh_token:
            print("Error: No refresh token available")
            sys.exit(1)

        import asyncio

        result = asyncio.run(refresh_access_token(args.provider, refresh_token))
        print(json.dumps(result, indent=2))

    elif args.action == "status":
        result = get_accounts_for_user(args.user_id)
        if result["success"]:
            print(f"Found {len(result['accounts'])} account(s):")
            for acc in result["accounts"]:
                print(f"  - {acc['provider']}: {acc['email_address']} (Level {acc['integration_level'].value})")
        else:
            print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
