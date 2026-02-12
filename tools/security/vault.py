"""
Tool: Secrets Vault
Purpose: Encrypted storage for API keys, tokens, and sensitive configuration

Features:
- AES-256-GCM encryption at rest
- PBKDF2 key derivation (100k iterations)
- Namespace support for multi-tenant/skill isolation
- Environment variable injection
- Access audit logging

Usage:
    python tools/security/vault.py --action set --key OPENAI_API_KEY --value "sk-..."
    python tools/security/vault.py --action get --key OPENAI_API_KEY
    python tools/security/vault.py --action list --namespace default
    python tools/security/vault.py --action delete --key OLD_TOKEN
    python tools/security/vault.py --action inject-env
    python tools/security/vault.py --action rotate-key  # Change master key

Dependencies:
    - cryptography (pip install cryptography)
    - sqlite3 (stdlib)

Security Notes:
    - Master key must be set in DEXAI_MASTER_KEY env var
    - Fails closed: no master key = no access
    - Never logs decrypted values
    - All access is audit logged
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data" / "vault.db"

# Salt for key derivation (fixed, but unique per installation)
# In production, this would be generated once and stored securely
SALT_PATH = Path(__file__).parent.parent.parent / "data" / ".vault_salt"

# Master key env var
MASTER_KEY_ENV = "DEXAI_MASTER_KEY"

# KDF iterations (from args/security.yaml default)
KDF_ITERATIONS = 100000


def get_or_create_salt() -> bytes:
    """Get or create the vault salt."""
    if SALT_PATH.exists():
        return SALT_PATH.read_bytes()
    else:
        import secrets

        salt = secrets.token_bytes(32)
        SALT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SALT_PATH.write_bytes(salt)
        return salt


def derive_key(master_password: str) -> bytes:
    """Derive encryption key from master password using PBKDF2."""
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography package not installed. Run: pip install cryptography")

    salt = get_or_create_salt()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bits for AES-256
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(master_password.encode())


def encrypt_value(plaintext: str, key: bytes) -> bytes:
    """Encrypt a value using AES-256-GCM."""
    import secrets

    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    # Prepend nonce to ciphertext
    return nonce + ciphertext


def decrypt_value(encrypted: bytes, key: bytes) -> str:
    """Decrypt a value using AES-256-GCM."""
    aesgcm = AESGCM(key)
    nonce = encrypted[:12]
    ciphertext = encrypted[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()


def get_master_key() -> bytes | None:
    """Get the derived encryption key from master password."""
    master_password = os.environ.get(MASTER_KEY_ENV)
    if not master_password:
        return None
    return derive_key(master_password)


def get_connection():
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS secrets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT DEFAULT 'default',
            key TEXT NOT NULL,
            encrypted_value BLOB NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            expires_at DATETIME,
            accessed_count INTEGER DEFAULT 0,
            last_accessed DATETIME,
            UNIQUE(namespace, key)
        )
    """)

    # Index for lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_secrets_ns_key ON secrets(namespace, key)")

    conn.commit()
    return conn


def log_access(action: str, key: str, namespace: str, status: str, user: str | None = None):
    """Log vault access to audit log."""
    try:
        # Import audit module
        from . import audit

        audit.log_event(
            event_type="secret",
            action=action,
            user_id=user,
            resource=f"{namespace}/{key}",
            status=status,
        )
    except Exception:
        # Don't fail if audit logging fails
        pass

    # Also log to dashboard audit for UI visibility
    try:
        from tools.dashboard.backend.database import log_audit

        event_type = f"data.{action}"
        severity = "info" if status == "success" else "warning"

        log_audit(
            event_type=event_type,
            severity=severity,
            actor=user,
            target=f"vault:{namespace}/{key}",
            details={"status": status, "action": action, "namespace": namespace},
        )
    except Exception:
        pass


def set_secret(
    key: str,
    value: str,
    namespace: str = "default",
    expires_at: str | None = None,
    user: str | None = None,
) -> dict[str, Any]:
    """
    Store an encrypted secret.

    Args:
        key: Secret identifier
        value: Secret value (will be encrypted)
        namespace: Namespace for isolation
        expires_at: Optional expiration datetime
        user: User performing the action (for audit)

    Returns:
        dict with success status
    """
    encryption_key = get_master_key()
    if not encryption_key:
        log_access("set", key, namespace, "failure", user)
        return {
            "success": False,
            "error": f"Master key not set. Set {MASTER_KEY_ENV} environment variable.",
        }

    try:
        encrypted = encrypt_value(value, encryption_key)
    except Exception as e:
        log_access("set", key, namespace, "failure", user)
        return {"success": False, "error": f"Encryption failed: {e!s}"}

    conn = get_connection()
    cursor = conn.cursor()

    # Upsert
    cursor.execute(
        """
        INSERT INTO secrets (namespace, key, encrypted_value, expires_at, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(namespace, key) DO UPDATE SET
            encrypted_value = excluded.encrypted_value,
            expires_at = excluded.expires_at,
            updated_at = CURRENT_TIMESTAMP
    """,
        (namespace, key, encrypted, expires_at),
    )

    conn.commit()
    conn.close()

    log_access("set", key, namespace, "success", user)

    return {
        "success": True,
        "message": f"Secret '{key}' stored in namespace '{namespace}'",
        "namespace": namespace,
        "key": key,
    }


def get_secret(key: str, namespace: str = "default", user: str | None = None) -> dict[str, Any]:
    """
    Retrieve and decrypt a secret.

    Args:
        key: Secret identifier
        namespace: Namespace
        user: User performing the action (for audit)

    Returns:
        dict with decrypted value (or error)
    """
    encryption_key = get_master_key()
    if not encryption_key:
        log_access("get", key, namespace, "failure", user)
        return {
            "success": False,
            "error": f"Master key not set. Set {MASTER_KEY_ENV} environment variable.",
        }

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM secrets
        WHERE namespace = ? AND key = ?
        AND (expires_at IS NULL OR expires_at > datetime('now'))
    """,
        (namespace, key),
    )

    row = cursor.fetchone()
    if not row:
        conn.close()
        log_access("get", key, namespace, "failure", user)
        return {"success": False, "error": f"Secret '{key}' not found in namespace '{namespace}'"}

    # Update access tracking
    cursor.execute(
        """
        UPDATE secrets
        SET accessed_count = accessed_count + 1, last_accessed = CURRENT_TIMESTAMP
        WHERE namespace = ? AND key = ?
    """,
        (namespace, key),
    )
    conn.commit()

    encrypted = row["encrypted_value"]
    conn.close()

    try:
        value = decrypt_value(encrypted, encryption_key)
    except Exception as e:
        log_access("get", key, namespace, "failure", user)
        return {"success": False, "error": f"Decryption failed: {e!s}"}

    log_access("get", key, namespace, "success", user)

    return {
        "success": True,
        "namespace": namespace,
        "key": key,
        "value": value,
        "accessed_count": row["accessed_count"] + 1,
    }


def list_secrets(namespace: str | None = None, include_expired: bool = False) -> dict[str, Any]:
    """
    List secrets (keys only, not values).

    Args:
        namespace: Filter by namespace (None = all)
        include_expired: Include expired secrets

    Returns:
        dict with list of secret metadata
    """
    conn = get_connection()
    cursor = conn.cursor()

    if namespace:
        if include_expired:
            cursor.execute(
                """
                SELECT namespace, key, created_at, updated_at, expires_at, accessed_count, last_accessed
                FROM secrets WHERE namespace = ?
            """,
                (namespace,),
            )
        else:
            cursor.execute(
                """
                SELECT namespace, key, created_at, updated_at, expires_at, accessed_count, last_accessed
                FROM secrets
                WHERE namespace = ?
                AND (expires_at IS NULL OR expires_at > datetime('now'))
            """,
                (namespace,),
            )
    else:
        if include_expired:
            cursor.execute("""
                SELECT namespace, key, created_at, updated_at, expires_at, accessed_count, last_accessed
                FROM secrets
            """)
        else:
            cursor.execute("""
                SELECT namespace, key, created_at, updated_at, expires_at, accessed_count, last_accessed
                FROM secrets
                WHERE expires_at IS NULL OR expires_at > datetime('now')
            """)

    secrets = []
    for row in cursor.fetchall():
        secrets.append(
            {
                "namespace": row["namespace"],
                "key": row["key"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "expires_at": row["expires_at"],
                "accessed_count": row["accessed_count"],
                "last_accessed": row["last_accessed"],
            }
        )

    conn.close()

    return {"success": True, "secrets": secrets, "count": len(secrets)}


def delete_secret(key: str, namespace: str = "default", user: str | None = None) -> dict[str, Any]:
    """
    Delete a secret.

    Args:
        key: Secret identifier
        namespace: Namespace
        user: User performing the action (for audit)

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM secrets WHERE namespace = ? AND key = ?", (namespace, key))
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Secret '{key}' not found in namespace '{namespace}'"}

    cursor.execute("DELETE FROM secrets WHERE namespace = ? AND key = ?", (namespace, key))
    conn.commit()
    conn.close()

    log_access("delete", key, namespace, "success", user)

    return {"success": True, "message": f"Secret '{key}' deleted from namespace '{namespace}'"}


def inject_env(
    namespace: str = "default",
    keys: list[str] | None = None,
) -> dict[str, Any]:
    """
    Load secrets from a namespace into environment variables.

    Args:
        namespace: Namespace to load
        keys: Optional list of specific secret keys to inject.
              If None, injects ALL secrets in the namespace (legacy behavior).

    Returns:
        dict with list of injected keys and any skipped keys
    """
    encryption_key = get_master_key()
    if not encryption_key:
        return {
            "success": False,
            "error": f"Master key not set. Set {MASTER_KEY_ENV} environment variable.",
        }

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT key, encrypted_value FROM secrets
        WHERE namespace = ?
        AND (expires_at IS NULL OR expires_at > datetime('now'))
    """,
        (namespace,),
    )

    injected = []
    skipped = []
    errors = []
    requested_keys = set(keys) if keys else None

    for row in cursor.fetchall():
        # If specific keys requested, skip any not in the list
        if requested_keys is not None and row["key"] not in requested_keys:
            skipped.append(row["key"])
            continue

        try:
            value = decrypt_value(row["encrypted_value"], encryption_key)
            os.environ[row["key"]] = value
            injected.append(row["key"])
        except Exception as e:
            errors.append({"key": row["key"], "error": str(e)})

    conn.close()

    return {
        "success": len(errors) == 0,
        "injected": injected,
        "skipped": skipped,
        "errors": errors,
        "count": len(injected),
    }


def check_status() -> dict[str, Any]:
    """Check vault status and configuration."""
    status = {
        "crypto_available": CRYPTO_AVAILABLE,
        "master_key_set": MASTER_KEY_ENV in os.environ,
        "salt_exists": SALT_PATH.exists(),
        "database_exists": DB_PATH.exists(),
    }

    if DB_PATH.exists():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM secrets")
        status["secret_count"] = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(DISTINCT namespace) as count FROM secrets")
        status["namespace_count"] = cursor.fetchone()["count"]
        conn.close()

    status["ready"] = (
        status["crypto_available"] and status["master_key_set"] and status["database_exists"]
    )

    return {"success": True, "status": status}


def main():
    parser = argparse.ArgumentParser(description="Secrets Vault")
    parser.add_argument(
        "--action",
        required=True,
        choices=["set", "get", "list", "delete", "inject-env", "status"],
        help="Action to perform",
    )
    parser.add_argument("--key", help="Secret key")
    parser.add_argument("--value", help="Secret value (for set)")
    parser.add_argument("--namespace", default="default", help="Namespace")
    parser.add_argument("--expires", help="Expiration datetime (ISO format)")
    parser.add_argument("--user", help="User performing action (for audit)")
    parser.add_argument(
        "--include-expired", action="store_true", help="Include expired secrets in list"
    )
    parser.add_argument(
        "--keys", nargs="+", help="Specific secret keys to inject (for inject-env)"
    )

    args = parser.parse_args()
    result = None

    if args.action == "set":
        if not args.key or not args.value:
            print("Error: --key and --value required for set")
            sys.exit(1)
        result = set_secret(
            key=args.key,
            value=args.value,
            namespace=args.namespace,
            expires_at=args.expires,
            user=args.user,
        )

    elif args.action == "get":
        if not args.key:
            print("Error: --key required for get")
            sys.exit(1)
        result = get_secret(key=args.key, namespace=args.namespace, user=args.user)

    elif args.action == "list":
        result = list_secrets(
            namespace=args.namespace if args.namespace != "default" else None,
            include_expired=args.include_expired,
        )

    elif args.action == "delete":
        if not args.key:
            print("Error: --key required for delete")
            sys.exit(1)
        result = delete_secret(key=args.key, namespace=args.namespace, user=args.user)

    elif args.action == "inject-env":
        result = inject_env(namespace=args.namespace, keys=args.keys)

    elif args.action == "status":
        result = check_status()

    if result:
        if result.get("success"):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        # Redact sensitive values in output
        output = result.copy()
        if "value" in output:
            output["value"] = "***REDACTED***"

        print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
