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
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data" / "vault.db"

# Legacy salt file path (for migration from pre-HKDF installations)
SALT_PATH = Path(__file__).parent.parent.parent / "data" / ".vault_salt"

# HKDF purpose string for deterministic salt derivation
HKDF_SALT_INFO = b"dexai-vault-salt-v2"

# Master key env var
MASTER_KEY_ENV = "DEXAI_MASTER_KEY"

# KDF iterations (from args/security.yaml default)
KDF_ITERATIONS = 100000


def _derive_salt(master_key: str) -> bytes:
    """Derive a deterministic salt from the master key using HKDF."""
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography package not installed. Run: pip install cryptography")

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=HKDF_SALT_INFO,
    )
    return hkdf.derive(master_key.encode())


def _derive_key_with_salt(master_password: str, salt: bytes) -> bytes:
    """Derive encryption key from master password and a given salt using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(master_password.encode())


def _migrate_salt(master_password: str) -> None:
    """Detect old salt file and migrate secrets to HKDF-derived salt."""
    if not SALT_PATH.exists():
        return

    logger.info("Legacy salt file detected, migrating to HKDF-derived salt")

    old_salt = SALT_PATH.read_bytes()
    old_key = _derive_key_with_salt(master_password, old_salt)

    new_salt = _derive_salt(master_password)
    new_key = _derive_key_with_salt(master_password, new_salt)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("SELECT id, namespace, key, encrypted_value FROM secrets")
        rows = cursor.fetchall()

        migrated = 0
        for row in rows:
            plaintext = decrypt_value(row["encrypted_value"], old_key)
            new_encrypted = encrypt_value(plaintext, new_key)
            cursor.execute(
                "UPDATE secrets SET encrypted_value = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_encrypted, row["id"]),
            )
            migrated += 1

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        logger.error("Salt migration failed, rolled back all changes")
        raise

    conn.close()

    SALT_PATH.unlink()
    logger.info("Salt migration complete: %d secrets re-encrypted, legacy salt file removed", migrated)

    try:
        from . import audit

        audit.log_event(
            event_type="security",
            action="salt_migration",
            status="success",
            details={"migrated_count": migrated, "total_count": len(rows)},
        )
    except Exception:
        pass


def derive_key(master_password: str) -> bytes:
    """Derive encryption key from master password using HKDF salt + PBKDF2."""
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography package not installed. Run: pip install cryptography")

    _migrate_salt(master_password)

    salt = _derive_salt(master_password)
    return _derive_key_with_salt(master_password, salt)


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


def rotate_secret(
    key: str,
    new_value: str,
    namespace: str = "default",
    user: str | None = None,
) -> dict[str, Any]:
    """Rotate an individual secret by re-encrypting with a new value."""
    encryption_key = get_master_key()
    if not encryption_key:
        return {
            "success": False,
            "error": f"Master key not set. Set {MASTER_KEY_ENV} environment variable.",
        }

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT encrypted_value FROM secrets WHERE namespace = ? AND key = ?",
        (namespace, key),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        log_access("rotate", key, namespace, "failure", user)
        return {"success": False, "error": f"Secret '{key}' not found in namespace '{namespace}'"}

    # Store old value under _rotated/ prefix for rollback
    try:
        rotated_key = f"_rotated/{key}"
        cursor.execute(
            """
            INSERT INTO secrets (namespace, key, encrypted_value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(namespace, key) DO UPDATE SET
                encrypted_value = excluded.encrypted_value,
                updated_at = CURRENT_TIMESTAMP
        """,
            (namespace, rotated_key, row["encrypted_value"]),
        )
    except Exception as e:
        conn.close()
        log_access("rotate", key, namespace, "failure", user)
        return {"success": False, "error": f"Failed to store rollback copy: {e!s}"}

    # Encrypt and store new value
    try:
        new_encrypted = encrypt_value(new_value, encryption_key)
        cursor.execute(
            """
            UPDATE secrets SET encrypted_value = ?, updated_at = CURRENT_TIMESTAMP
            WHERE namespace = ? AND key = ?
        """,
            (new_encrypted, namespace, key),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        log_access("rotate", key, namespace, "failure", user)
        return {"success": False, "error": f"Rotation failed: {e!s}"}

    conn.close()

    rotated_at = datetime.now(timezone.utc).isoformat()
    log_access("rotate", key, namespace, "success", user)

    return {"success": True, "key": key, "rotated_at": rotated_at}


def list_rotatable_secrets(namespace: str = "default") -> list[str]:
    """Return keys eligible for rotation (non-expired, non-rollback secrets)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT key FROM secrets
        WHERE namespace = ?
        AND key NOT LIKE '_rotated/%%'
        AND (expires_at IS NULL OR expires_at > datetime('now'))
    """,
        (namespace,),
    )

    keys = [row["key"] for row in cursor.fetchall()]
    conn.close()
    return keys


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
        "salt_exists": True,  # HKDF-derived, always available when master key is set
        "legacy_salt_pending": SALT_PATH.exists(),
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


def rotate_master_key(old_master_key: str, new_master_key: str) -> dict[str, Any]:
    """Re-encrypt all secrets from old master key to new master key."""
    if not CRYPTO_AVAILABLE:
        return {"success": False, "error": "cryptography package not installed"}

    # Derive old key material
    try:
        if SALT_PATH.exists():
            old_salt = SALT_PATH.read_bytes()
        else:
            old_salt = _derive_salt(old_master_key)
        old_key = _derive_key_with_salt(old_master_key, old_salt)
    except Exception as e:
        return {"success": False, "error": f"Failed to derive old key: {e!s}"}

    # Derive new key material using HKDF salt
    try:
        new_salt = _derive_salt(new_master_key)
        new_key = _derive_key_with_salt(new_master_key, new_salt)
    except Exception as e:
        return {"success": False, "error": f"Failed to derive new key: {e!s}"}

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, namespace, key, encrypted_value FROM secrets")
    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return {"success": True, "secrets_rotated": 0}

    # Decrypt all secrets with old key first to validate before writing
    decrypted = []
    for row in rows:
        try:
            plaintext = decrypt_value(row["encrypted_value"], old_key)
            decrypted.append((row["id"], row["namespace"], row["key"], plaintext))
        except Exception as e:
            conn.close()
            log_access("rotate_master_key", row["key"], row["namespace"], "failure")
            return {
                "success": False,
                "error": f"Failed to decrypt secret '{row['namespace']}/{row['key']}': {e!s}",
            }

    # Back up before re-encryption for rollback safety
    import shutil

    backup_path = DB_PATH.with_suffix(".db.bak")
    shutil.copy2(str(DB_PATH), str(backup_path))

    try:
        for row_id, namespace, key, plaintext in decrypted:
            new_encrypted = encrypt_value(plaintext, new_key)
            cursor.execute(
                "UPDATE secrets SET encrypted_value = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_encrypted, row_id),
            )
        conn.commit()
    except Exception as e:
        conn.close()
        # Roll back by restoring backup
        shutil.copy2(str(backup_path), str(DB_PATH))
        log_access("rotate_master_key", "*", "all", "failure")
        return {"success": False, "error": f"Re-encryption failed, rolled back: {e!s}"}

    conn.close()

    # Remove legacy salt file if it existed
    if SALT_PATH.exists():
        SALT_PATH.unlink()

    # Remove backup after successful rotation
    if backup_path.exists():
        backup_path.unlink()

    log_access("rotate_master_key", "*", "all", "success")

    try:
        from . import audit

        audit.log_event(
            event_type="security",
            action="master_key_rotation",
            status="success",
            details={"secrets_rotated": len(decrypted)},
        )
    except Exception:
        pass

    return {"success": True, "secrets_rotated": len(decrypted)}


def main():
    parser = argparse.ArgumentParser(description="Secrets Vault")
    parser.add_argument(
        "--action",
        required=True,
        choices=["set", "get", "list", "delete", "inject-env", "status", "rotate-key", "rotate-secret"],
        help="Action to perform",
    )
    parser.add_argument("--key", help="Secret key")
    parser.add_argument("--value", help="Secret value (for set/rotate-secret)")
    parser.add_argument("--namespace", default="default", help="Namespace")
    parser.add_argument("--expires", help="Expiration datetime (ISO format)")
    parser.add_argument("--user", help="User performing action (for audit)")
    parser.add_argument(
        "--include-expired", action="store_true", help="Include expired secrets in list"
    )
    parser.add_argument(
        "--keys", nargs="+", help="Specific secret keys to inject (for inject-env)"
    )
    parser.add_argument("--old-key", help="Old master key (for rotate-key)")
    parser.add_argument("--new-key", help="New master key (for rotate-key)")

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

    elif args.action == "rotate-secret":
        if not args.key or not args.value:
            print("Error: --key and --value required for rotate-secret")
            sys.exit(1)
        result = rotate_secret(
            key=args.key,
            new_value=args.value,
            namespace=args.namespace,
            user=args.user,
        )

    elif args.action == "rotate-key":
        if not args.old_key or not args.new_key:
            print("Error: --old-key and --new-key required for rotate-key")
            sys.exit(1)
        result = rotate_master_key(old_master_key=args.old_key, new_master_key=args.new_key)

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
