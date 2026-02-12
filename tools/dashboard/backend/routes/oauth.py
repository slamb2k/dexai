"""
OAuth Routes - OAuth callback handlers for office integration

Provides endpoints for OAuth 2.0 flows:
- GET /oauth/google/callback - Google OAuth callback
- GET /oauth/microsoft/callback - Microsoft OAuth callback
- GET /oauth/status - Check OAuth status
- POST /oauth/revoke - Revoke OAuth tokens
"""

import html
import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from tools.office import get_connection


router = APIRouter()


# Configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "args" / "office_integration.yaml"


def load_oauth_config() -> dict:
    """Load OAuth configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}
            return config.get("office_integration", {}).get("oauth", {})
    return {}


def _parse_oauth_state(state: str | None) -> dict:
    """Parse OAuth state JSON to extract PKCE verifier, user_id, and level.

    Returns dict with keys: code_verifier, user_id, integration_level.
    All values have safe defaults if state is missing or malformed.
    """
    result = {"code_verifier": None, "user_id": "default", "integration_level": 2}
    if not state:
        return result
    try:
        state_data = json.loads(state)
        if isinstance(state_data, dict):
            result["code_verifier"] = state_data.get("code_verifier")
            result["user_id"] = state_data.get("user_id", "default")
            result["integration_level"] = state_data.get("level", 2)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse OAuth state (PKCE verification may be disabled): {e}")
    return result


# =============================================================================
# Response Models
# =============================================================================


class OAuthStatusResponse(BaseModel):
    """OAuth status response."""

    provider: str
    connected: bool
    email: str | None
    integration_level: int | None
    scopes: list[str] | None
    expires_at: str | None


class OAuthRevokeRequest(BaseModel):
    """Request to revoke OAuth tokens."""

    account_id: str


# =============================================================================
# OAuth Callbacks
# =============================================================================


@router.get("/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
):
    """
    Handle Google OAuth callback.

    Exchanges authorization code for tokens and stores them.
    """
    if error:
        return HTMLResponse(
            content=f"""
            <html>
            <head><title>OAuth Error</title></head>
            <body>
                <h1>Authentication Failed</h1>
                <p>Error: {html.escape(error)}</p>
                <p><a href="/office">Return to Services</a></p>
            </body>
            </html>
            """,
            status_code=400,
        )

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # Exchange code for tokens
    try:
        from tools.office.oauth_manager import exchange_code_for_tokens

        parsed_state = _parse_oauth_state(state)
        result = await exchange_code_for_tokens(
            "google", code, code_verifier=parsed_state["code_verifier"]
        )

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Token exchange failed"))

        # Store tokens in database
        access_token = result.get("access_token")
        if not access_token:
            raise HTTPException(status_code=500, detail="Token exchange did not return access token")
        refresh_token = result.get("refresh_token")
        expires_in = result.get("expires_in", 3600)
        scopes = result.get("scope", "").split()

        # Get user info
        from tools.office.oauth_manager import get_user_info_from_token
        user_info = await get_user_info_from_token("google", access_token)
        email = user_info.get("email", "")

        user_id = parsed_state["user_id"]
        integration_level = parsed_state["integration_level"]

        # Encrypt tokens via vault before storage
        encrypted_access = access_token
        encrypted_refresh = refresh_token
        try:
            from tools.security.vault import set_secret
            vault_key_access = f"google_{email}_access"
            set_secret(vault_key_access, access_token, namespace="office_tokens")
            encrypted_access = f"vault:google_{email}_access"

            if refresh_token:
                vault_key_refresh = f"google_{email}_refresh"
                set_secret(vault_key_refresh, refresh_token, namespace="office_tokens")
                encrypted_refresh = f"vault:google_{email}_refresh"
        except Exception:
            pass  # Fall back to raw storage if vault unavailable

        # Create account record
        account_id = str(uuid.uuid4())
        token_expiry = datetime.now() + timedelta(seconds=expires_in)

        conn = get_connection()
        cursor = conn.cursor()

        # Check if account already exists for this email
        cursor.execute(
            "SELECT id FROM office_accounts WHERE email_address = ? AND provider = ?",
            (email, "google"),
        )
        existing = cursor.fetchone()

        if existing:
            # Update existing account
            account_id = existing["id"]
            cursor.execute(
                """
                UPDATE office_accounts SET
                    access_token_encrypted = ?,
                    refresh_token_encrypted = ?,
                    token_expiry = ?,
                    scopes = ?,
                    integration_level = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    encrypted_access,
                    encrypted_refresh,
                    token_expiry.isoformat(),
                    json.dumps(scopes),
                    integration_level,
                    datetime.now().isoformat(),
                    account_id,
                ),
            )
        else:
            # Create new account
            cursor.execute(
                """
                INSERT INTO office_accounts (
                    id, user_id, provider, integration_level, email_address,
                    access_token_encrypted, refresh_token_encrypted, token_expiry,
                    scopes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    user_id,
                    "google",
                    integration_level,
                    email,
                    encrypted_access,
                    encrypted_refresh,
                    token_expiry.isoformat(),
                    json.dumps(scopes),
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )

        conn.commit()
        conn.close()

        # Redirect to success page
        return HTMLResponse(
            content=f"""
            <html>
            <head>
                <title>Connected Successfully</title>
                <script>
                    setTimeout(function() {{
                        window.location.href = '/office';
                    }}, 3000);
                </script>
            </head>
            <body style="font-family: system-ui; text-align: center; padding: 50px;">
                <h1>Google Account Connected</h1>
                <p>Successfully connected: <strong>{email}</strong></p>
                <p>Integration Level: <strong>Level {integration_level}</strong></p>
                <p>Redirecting to Services...</p>
            </body>
            </html>
            """
        )

    except ImportError:
        raise HTTPException(status_code=500, detail="OAuth module not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {e}")


@router.get("/microsoft/callback")
async def microsoft_oauth_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    state: str | None = None,
):
    """
    Handle Microsoft OAuth callback.

    Exchanges authorization code for tokens and stores them.
    """
    if error:
        return HTMLResponse(
            content=f"""
            <html>
            <head><title>OAuth Error</title></head>
            <body>
                <h1>Authentication Failed</h1>
                <p>Error: {html.escape(error)}</p>
                <p>{html.escape(error_description or '')}</p>
                <p><a href="/office">Return to Services</a></p>
            </body>
            </html>
            """,
            status_code=400,
        )

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        from tools.office.oauth_manager import exchange_code_for_tokens

        parsed_state = _parse_oauth_state(state)
        result = await exchange_code_for_tokens(
            "microsoft", code, code_verifier=parsed_state["code_verifier"]
        )

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Token exchange failed"))

        # Store tokens
        access_token = result.get("access_token")
        if not access_token:
            raise HTTPException(status_code=500, detail="Token exchange did not return access token")
        refresh_token = result.get("refresh_token")
        expires_in = result.get("expires_in", 3600)
        scopes = result.get("scope", "").split()

        # Get user info
        from tools.office.oauth_manager import get_user_info_from_token
        user_info = await get_user_info_from_token("microsoft", access_token)
        email = user_info.get("email") or user_info.get("userPrincipalName", "")

        user_id = parsed_state["user_id"]
        integration_level = parsed_state["integration_level"]

        # Encrypt tokens via vault before storage
        encrypted_access = access_token
        encrypted_refresh = refresh_token
        try:
            from tools.security.vault import set_secret
            vault_key_access = f"microsoft_{email}_access"
            set_secret(vault_key_access, access_token, namespace="office_tokens")
            encrypted_access = f"vault:microsoft_{email}_access"

            if refresh_token:
                vault_key_refresh = f"microsoft_{email}_refresh"
                set_secret(vault_key_refresh, refresh_token, namespace="office_tokens")
                encrypted_refresh = f"vault:microsoft_{email}_refresh"
        except Exception:
            pass  # Fall back to raw storage if vault unavailable

        # Create account record
        account_id = str(uuid.uuid4())
        token_expiry = datetime.now() + timedelta(seconds=expires_in)

        conn = get_connection()
        cursor = conn.cursor()

        # Check if account exists
        cursor.execute(
            "SELECT id FROM office_accounts WHERE email_address = ? AND provider = ?",
            (email, "microsoft"),
        )
        existing = cursor.fetchone()

        if existing:
            account_id = existing["id"]
            cursor.execute(
                """
                UPDATE office_accounts SET
                    access_token_encrypted = ?,
                    refresh_token_encrypted = ?,
                    token_expiry = ?,
                    scopes = ?,
                    integration_level = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    encrypted_access,
                    encrypted_refresh,
                    token_expiry.isoformat(),
                    json.dumps(scopes),
                    integration_level,
                    datetime.now().isoformat(),
                    account_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO office_accounts (
                    id, user_id, provider, integration_level, email_address,
                    access_token_encrypted, refresh_token_encrypted, token_expiry,
                    scopes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    user_id,
                    "microsoft",
                    integration_level,
                    email,
                    encrypted_access,
                    encrypted_refresh,
                    token_expiry.isoformat(),
                    json.dumps(scopes),
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )

        conn.commit()
        conn.close()

        return HTMLResponse(
            content=f"""
            <html>
            <head>
                <title>Connected Successfully</title>
                <script>
                    setTimeout(function() {{
                        window.location.href = '/office';
                    }}, 3000);
                </script>
            </head>
            <body style="font-family: system-ui; text-align: center; padding: 50px;">
                <h1>Microsoft Account Connected</h1>
                <p>Successfully connected: <strong>{email}</strong></p>
                <p>Integration Level: <strong>Level {integration_level}</strong></p>
                <p>Redirecting to Services...</p>
            </body>
            </html>
            """
        )

    except ImportError:
        raise HTTPException(status_code=500, detail="OAuth module not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {e}")


# =============================================================================
# Status and Management Endpoints
# =============================================================================


@router.get("/status")
async def get_oauth_status(user_id: str = Query("default")):
    """
    Get OAuth connection status for all providers.

    Returns status of Google and Microsoft connections for the user.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT provider, email_address, integration_level, scopes, token_expiry
        FROM office_accounts
        WHERE user_id = ?
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    statuses = []
    for row in rows:
        account = dict(row)
        scopes = json.loads(account["scopes"]) if account.get("scopes") else []

        statuses.append(OAuthStatusResponse(
            provider=account["provider"],
            connected=True,
            email=account["email_address"],
            integration_level=account["integration_level"],
            scopes=scopes,
            expires_at=account["token_expiry"],
        ))

    # Add disconnected providers
    connected_providers = {s.provider for s in statuses}
    for provider in ["google", "microsoft"]:
        if provider not in connected_providers:
            statuses.append(OAuthStatusResponse(
                provider=provider,
                connected=False,
                email=None,
                integration_level=None,
                scopes=None,
                expires_at=None,
            ))

    return statuses


@router.post("/revoke")
async def revoke_oauth_tokens(request: OAuthRevokeRequest):
    """
    Revoke OAuth tokens and disconnect an account.

    This removes the account from the database and attempts to revoke
    tokens with the provider.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get account details
    cursor.execute(
        "SELECT * FROM office_accounts WHERE id = ?",
        (request.account_id,),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")

    account = dict(row)

    # Try to revoke tokens with provider
    try:
        from tools.office.oauth_manager import revoke_token

        if account.get("access_token_encrypted"):
            await revoke_token(account["provider"], account["access_token_encrypted"])
    except Exception as e:
        # Log but don't fail - account will still be removed
        print(f"Warning: Could not revoke token with provider: {e}")

    # Remove account from database
    cursor.execute("DELETE FROM office_accounts WHERE id = ?", (request.account_id,))

    # Also clean up related drafts and meeting drafts
    cursor.execute("DELETE FROM office_drafts WHERE account_id = ?", (request.account_id,))
    cursor.execute("DELETE FROM office_meeting_drafts WHERE account_id = ?", (request.account_id,))

    conn.commit()
    conn.close()

    return {"success": True, "message": f"Account {account['email_address']} disconnected"}


@router.get("/authorize/{provider}")
async def get_authorization_url(
    provider: str,
    integration_level: int = Query(2, ge=1, le=5),
    user_id: str = Query("default"),
):
    """
    Get OAuth authorization URL for a provider.

    Returns the URL to redirect the user to for OAuth consent.
    """
    if provider not in ["google", "microsoft"]:
        raise HTTPException(status_code=400, detail="Invalid provider")

    try:
        from tools.office.oauth_manager import get_authorization_url

        state = json.dumps({"user_id": user_id, "level": integration_level})
        url = await get_authorization_url(provider, integration_level, state)

        return {"authorization_url": url}

    except ImportError:
        raise HTTPException(status_code=500, detail="OAuth module not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate authorization URL: {e}")
