"""
Dashboard Authentication Routes

Provides endpoints for session-based authentication:
- POST /api/auth/login  - Authenticate with master key
- POST /api/auth/logout - Destroy session
- GET  /api/auth/check  - Validate current session
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

router = APIRouter()

# Cookie settings
COOKIE_NAME = "dexai_session"
COOKIE_MAX_AGE = 86400  # 24 hours


class LoginRequest(BaseModel):
    """Login request with master key."""

    password: str = Field(..., min_length=1)


class AuthStatus(BaseModel):
    """Authentication status response."""

    authenticated: bool
    user_id: str | None = None
    role: str | None = None


@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """
    Authenticate using the master key.

    Returns a session cookie on success.
    """
    master_key = os.environ.get("DEXAI_MASTER_KEY", "")

    if not master_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication not configured. Set DEXAI_MASTER_KEY.",
        )

    if request.password != master_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Create session via the security session module
    try:
        from tools.security.session import create_session

        session_result = create_session(
            user_id="owner",
            channel="dashboard",
            metadata={"role": "admin"},
        )

        if not session_result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create session",
            )

        token = session_result["token"]

        # Set session cookie
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=False,  # Set True when behind HTTPS proxy
        )

        return {"success": True, "user_id": "owner", "role": "admin"}

    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session module not available",
        )


@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie."""
    response.delete_cookie(key=COOKIE_NAME)
    return {"success": True}


@router.get("/check", response_model=AuthStatus)
async def check_auth(request: Request):
    """Check if current session is valid."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        # Try Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return AuthStatus(authenticated=False)

    # Validate session
    try:
        from tools.security.session import validate_session

        result = validate_session(token, update_activity=True)

        if result.get("valid"):
            return AuthStatus(
                authenticated=True,
                user_id=result.get("user_id"),
                role=result.get("metadata", {}).get("role", "user"),
            )
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Session validation error: {e}")

    return AuthStatus(authenticated=False)
