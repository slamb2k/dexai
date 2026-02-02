"""
Tool: File Operations
Purpose: Secure file read/write with path validation and sandboxing

Security Model:
- All paths validated against approved directory list
- Path traversal blocked (.., symlinks outside sandbox)
- Size limits enforced on read and write
- Atomic writes (temp file + rename)
- All operations logged to audit trail

Usage:
    python tools/system/fileops.py --read /path/to/file
    python tools/system/fileops.py --write /path/to/file --content "data"
    python tools/system/fileops.py --append /path/to/file --content "data"
    python tools/system/fileops.py --list /path/to/dir
    python tools/system/fileops.py --delete /path/to/file
    python tools/system/fileops.py --validate /path/to/check
    python tools/system/fileops.py --mkdir /path/to/dir

Dependencies:
    - pathlib (stdlib)
    - os (stdlib)
    - tempfile (stdlib)
    - mimetypes (stdlib)

Output:
    JSON result with success status and operation result
"""

import os
import sys
import json
import argparse
import tempfile
import shutil
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Config path
CONFIG_PATH = PROJECT_ROOT / "args" / "system_access.yaml"

# Default approved directories (paths will be expanded)
DEFAULT_APPROVED_DIRS = [
    "~/addulting/workspace",
    "~/addulting/.tmp",
    "/tmp/addulting",
]

# Default size limits
DEFAULT_MAX_READ_SIZE = 10 * 1024 * 1024   # 10MB
DEFAULT_MAX_WRITE_SIZE = 10 * 1024 * 1024  # 10MB

# Blocked file patterns
BLOCKED_PATTERNS = [
    '.env',
    '.env.*',
    'credentials.*',
    '*.pem',
    '*.key',
    'id_rsa*',
    'id_ed25519*',
    '.ssh/*',
    '.gnupg/*',
    '.vault_salt',
    'token.json',
]


def load_config() -> Dict:
    """Load fileops configuration from YAML file."""
    default_config = {
        'enabled': True,
        'approved_dirs': DEFAULT_APPROVED_DIRS,
        'max_read_size': DEFAULT_MAX_READ_SIZE,
        'max_write_size': DEFAULT_MAX_WRITE_SIZE,
        'allow_hidden': False,  # Don't allow .files by default
        'permissions': {
            'read': 'files:read',
            'write': 'files:write',
            'delete': 'files:delete',
        }
    }

    if not CONFIG_PATH.exists():
        return default_config

    try:
        import yaml
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        if config and 'fileops' in config:
            fileops_config = config['fileops']
            for key, value in fileops_config.items():
                default_config[key] = value
    except ImportError:
        pass
    except Exception:
        pass

    return default_config


def expand_approved_dirs() -> List[Path]:
    """Get list of approved directories as resolved Paths."""
    config = load_config()
    approved = config.get('approved_dirs', DEFAULT_APPROVED_DIRS)

    resolved = []
    for d in approved:
        try:
            path = Path(d).expanduser().resolve()
            resolved.append(path)
        except Exception:
            pass

    return resolved


def is_blocked_filename(filename: str) -> bool:
    """Check if filename matches blocked patterns."""
    import fnmatch

    for pattern in BLOCKED_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return True
        if fnmatch.fnmatch(os.path.basename(filename), pattern):
            return True

    return False


def validate_path(path: str, check_exists: bool = True) -> Tuple[bool, str, str]:
    """
    Validate that a path is within the sandbox.

    Args:
        path: Path to validate
        check_exists: Whether to check if path exists

    Returns:
        Tuple of (is_valid, resolved_path, error_message)
    """
    config = load_config()

    try:
        # Expand and resolve the path
        path_obj = Path(path).expanduser()

        # Don't resolve yet - check for .. first
        path_str = str(path_obj)
        if '..' in path_str:
            return False, "", "Path traversal not allowed (..)"

        # Now resolve
        resolved = path_obj.resolve()
        resolved_str = str(resolved)

    except Exception as e:
        return False, "", f"Invalid path: {e}"

    # Check against blocked filenames
    if is_blocked_filename(resolved.name) or is_blocked_filename(resolved_str):
        return False, "", f"Access to file '{resolved.name}' is blocked"

    # Check for hidden files
    if not config.get('allow_hidden', False):
        for part in resolved.parts:
            if part.startswith('.') and part not in ('.', '..', '.tmp'):
                return False, "", f"Access to hidden files not allowed: {part}"

    # Check if path is within approved directories
    approved_dirs = expand_approved_dirs()

    is_approved = False
    for approved in approved_dirs:
        try:
            # Use is_relative_to for Python 3.9+, fall back to string comparison
            if hasattr(resolved, 'is_relative_to'):
                if resolved.is_relative_to(approved):
                    is_approved = True
                    break
            else:
                if str(resolved).startswith(str(approved)):
                    is_approved = True
                    break
        except Exception:
            pass

    if not is_approved:
        return False, "", f"Path outside approved directories. Approved: {[str(d) for d in approved_dirs]}"

    # Check if it's a symlink pointing outside sandbox
    if resolved.is_symlink():
        target = resolved.resolve()
        target_approved = False
        for approved in approved_dirs:
            try:
                if hasattr(target, 'is_relative_to'):
                    if target.is_relative_to(approved):
                        target_approved = True
                        break
                else:
                    if str(target).startswith(str(approved)):
                        target_approved = True
                        break
            except Exception:
                pass

        if not target_approved:
            return False, "", "Symlink target outside sandbox"

    # Check existence if required
    if check_exists and not resolved.exists():
        return False, resolved_str, "Path does not exist"

    return True, resolved_str, ""


def check_permission(user_id: str, permission: str) -> bool:
    """Check if user has permission for operation."""
    try:
        from tools.security import permissions
        result = permissions.check_permission(user_id or 'anonymous', permission)
        return result.get('allowed', False)
    except Exception:
        return True  # If permissions unavailable, allow


def log_operation(action: str, path: str, user_id: Optional[str], status: str, details: Optional[Dict] = None):
    """Log file operation to audit trail."""
    try:
        from tools.security import audit
        audit.log_event(
            event_type='command',
            action=f'file:{action}',
            user_id=user_id,
            resource=path,
            status=status,
            details=details
        )
    except Exception:
        pass


def read_file(
    path: str,
    max_size: Optional[int] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Read file content safely.

    Args:
        path: Path to file
        max_size: Maximum file size to read (bytes)
        user_id: User requesting read

    Returns:
        dict with success status, content, size, mime_type
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "File operations disabled"}

    # Check permission
    perm = config.get('permissions', {}).get('read', 'files:read')
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Validate path
    is_valid, resolved_path, error = validate_path(path, check_exists=True)
    if not is_valid:
        log_operation('read', path, user_id, 'blocked', {'reason': error})
        return {"success": False, "error": error}

    resolved = Path(resolved_path)

    # Check if it's a file
    if not resolved.is_file():
        return {"success": False, "error": "Path is not a file"}

    # Check size
    max_size = max_size or config.get('max_read_size', DEFAULT_MAX_READ_SIZE)
    file_size = resolved.stat().st_size
    if file_size > max_size:
        return {
            "success": False,
            "error": f"File too large: {file_size} bytes (max: {max_size})"
        }

    # Read file
    try:
        with open(resolved, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # Try binary read
        try:
            with open(resolved, 'rb') as f:
                content = f.read()
            content = content.hex()  # Convert to hex string
        except Exception as e:
            return {"success": False, "error": f"Failed to read file: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Failed to read file: {e}"}

    # Get mime type
    mime_type, _ = mimetypes.guess_type(resolved_path)

    log_operation('read', resolved_path, user_id, 'success', {'size': file_size})

    return {
        "success": True,
        "content": content,
        "size": file_size,
        "mime_type": mime_type,
        "path": resolved_path
    }


def write_file(
    path: str,
    content: str,
    mode: str = 'write',
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Write file with atomic operation (temp + rename).

    Args:
        path: Path to file
        content: Content to write
        mode: 'write' (overwrite) or 'append'
        user_id: User requesting write

    Returns:
        dict with success status
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "File operations disabled"}

    # Check permission
    perm = config.get('permissions', {}).get('write', 'files:write')
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Check content size
    max_size = config.get('max_write_size', DEFAULT_MAX_WRITE_SIZE)
    content_size = len(content.encode('utf-8'))
    if content_size > max_size:
        return {
            "success": False,
            "error": f"Content too large: {content_size} bytes (max: {max_size})"
        }

    # Validate path (don't require exists for write)
    is_valid, resolved_path, error = validate_path(path, check_exists=False)
    if not is_valid and "does not exist" not in error:
        log_operation('write', path, user_id, 'blocked', {'reason': error})
        return {"success": False, "error": error}

    resolved = Path(path).expanduser().resolve()

    # Re-validate the resolved path is still in sandbox
    is_valid, resolved_path, error = validate_path(str(resolved), check_exists=False)
    if not is_valid and "does not exist" not in error:
        return {"success": False, "error": error}

    # Ensure parent directory exists
    parent = resolved.parent
    if not parent.exists():
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return {"success": False, "error": f"Failed to create directory: {e}"}

    try:
        if mode == 'append' and resolved.exists():
            # Append mode
            with open(resolved, 'a', encoding='utf-8') as f:
                f.write(content)
        else:
            # Atomic write: write to temp, then rename
            fd, temp_path = tempfile.mkstemp(dir=str(parent))
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(content)
                shutil.move(temp_path, resolved)
            except Exception:
                # Clean up temp file on failure
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise

        log_operation('write', str(resolved), user_id, 'success', {'size': content_size, 'mode': mode})

        return {
            "success": True,
            "path": str(resolved),
            "size": content_size,
            "mode": mode,
            "message": f"File {'written' if mode == 'write' else 'appended'} successfully"
        }

    except Exception as e:
        log_operation('write', str(resolved), user_id, 'failure', {'error': str(e)})
        return {"success": False, "error": f"Failed to write file: {e}"}


def list_directory(
    path: str,
    user_id: Optional[str] = None,
    recursive: bool = False,
    pattern: Optional[str] = None
) -> Dict[str, Any]:
    """
    List directory contents.

    Args:
        path: Path to directory
        user_id: User requesting list
        recursive: List recursively
        pattern: Glob pattern to filter

    Returns:
        dict with entries list
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "File operations disabled"}

    # Check permission
    perm = config.get('permissions', {}).get('read', 'files:read')
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Validate path
    is_valid, resolved_path, error = validate_path(path, check_exists=True)
    if not is_valid:
        return {"success": False, "error": error}

    resolved = Path(resolved_path)

    if not resolved.is_dir():
        return {"success": False, "error": "Path is not a directory"}

    entries = []
    try:
        if recursive:
            iterator = resolved.rglob(pattern or '*')
        else:
            iterator = resolved.glob(pattern or '*')

        for entry in iterator:
            try:
                stat_info = entry.stat()
                entries.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "directory" if entry.is_dir() else "file",
                    "size": stat_info.st_size if entry.is_file() else None,
                    "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat()
                })
            except Exception:
                # Skip entries we can't stat
                pass

        # Sort: directories first, then alphabetically
        entries.sort(key=lambda x: (x['type'] != 'directory', x['name'].lower()))

    except Exception as e:
        return {"success": False, "error": f"Failed to list directory: {e}"}

    log_operation('list', resolved_path, user_id, 'success', {'count': len(entries)})

    return {
        "success": True,
        "path": resolved_path,
        "entries": entries,
        "count": len(entries)
    }


def delete_file(
    path: str,
    user_id: Optional[str] = None,
    force: bool = False
) -> Dict[str, Any]:
    """
    Delete a file.

    Args:
        path: Path to file
        user_id: User requesting delete
        force: Skip confirmation for non-.tmp files

    Returns:
        dict with success status
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "File operations disabled"}

    # Check permission
    perm = config.get('permissions', {}).get('delete', 'files:delete')
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Validate path
    is_valid, resolved_path, error = validate_path(path, check_exists=True)
    if not is_valid:
        return {"success": False, "error": error}

    resolved = Path(resolved_path)

    if not resolved.is_file():
        return {"success": False, "error": "Path is not a file"}

    # Safety check: require force for non-.tmp files
    is_tmp = '.tmp' in resolved_path or '/tmp/' in resolved_path
    if not is_tmp and not force:
        return {
            "success": False,
            "error": "Use --force to delete files outside .tmp directories",
            "path": resolved_path
        }

    try:
        resolved.unlink()
        log_operation('delete', resolved_path, user_id, 'success')
        return {
            "success": True,
            "path": resolved_path,
            "message": "File deleted successfully"
        }
    except Exception as e:
        log_operation('delete', resolved_path, user_id, 'failure', {'error': str(e)})
        return {"success": False, "error": f"Failed to delete file: {e}"}


def make_directory(
    path: str,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a directory.

    Args:
        path: Path for new directory
        user_id: User requesting creation

    Returns:
        dict with success status
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "File operations disabled"}

    # Check permission
    perm = config.get('permissions', {}).get('write', 'files:write')
    if not check_permission(user_id, perm):
        return {"success": False, "error": f"Permission denied: {perm} required"}

    # Validate path (don't require exists)
    is_valid, resolved_path, error = validate_path(path, check_exists=False)
    if not is_valid and "does not exist" not in error:
        return {"success": False, "error": error}

    resolved = Path(path).expanduser().resolve()

    # Re-validate
    is_valid, resolved_path, error = validate_path(str(resolved), check_exists=False)
    if not is_valid and "does not exist" not in error:
        return {"success": False, "error": error}

    try:
        resolved.mkdir(parents=True, exist_ok=True)
        log_operation('mkdir', str(resolved), user_id, 'success')
        return {
            "success": True,
            "path": str(resolved),
            "message": "Directory created successfully"
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to create directory: {e}"}


def copy_file(
    source: str,
    destination: str,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Copy a file.

    Args:
        source: Source path
        destination: Destination path
        user_id: User requesting copy

    Returns:
        dict with success status
    """
    config = load_config()

    if not config.get('enabled', True):
        return {"success": False, "error": "File operations disabled"}

    # Check permissions
    read_perm = config.get('permissions', {}).get('read', 'files:read')
    write_perm = config.get('permissions', {}).get('write', 'files:write')
    if not check_permission(user_id, read_perm):
        return {"success": False, "error": f"Permission denied: {read_perm} required"}
    if not check_permission(user_id, write_perm):
        return {"success": False, "error": f"Permission denied: {write_perm} required"}

    # Validate source
    is_valid, src_resolved, error = validate_path(source, check_exists=True)
    if not is_valid:
        return {"success": False, "error": f"Source: {error}"}

    src = Path(src_resolved)
    if not src.is_file():
        return {"success": False, "error": "Source is not a file"}

    # Validate destination
    is_valid, dst_resolved, error = validate_path(destination, check_exists=False)
    if not is_valid and "does not exist" not in error:
        return {"success": False, "error": f"Destination: {error}"}

    dst = Path(destination).expanduser().resolve()

    # If destination is directory, use source filename
    if dst.exists() and dst.is_dir():
        dst = dst / src.name

    try:
        # Ensure parent exists
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        log_operation('copy', src_resolved, user_id, 'success', {'destination': str(dst)})
        return {
            "success": True,
            "source": src_resolved,
            "destination": str(dst),
            "message": "File copied successfully"
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to copy file: {e}"}


def get_approved_dirs() -> Dict[str, Any]:
    """Get list of approved directories."""
    config = load_config()
    approved = expand_approved_dirs()

    return {
        "success": True,
        "approved_dirs": [str(d) for d in approved],
        "max_read_size": config.get('max_read_size', DEFAULT_MAX_READ_SIZE),
        "max_write_size": config.get('max_write_size', DEFAULT_MAX_WRITE_SIZE),
        "allow_hidden": config.get('allow_hidden', False)
    }


def main():
    parser = argparse.ArgumentParser(description='File Operations')

    # Actions
    parser.add_argument('--read', help='Read file at path')
    parser.add_argument('--write', help='Write to file at path')
    parser.add_argument('--append', help='Append to file at path')
    parser.add_argument('--list', dest='list_dir', help='List directory')
    parser.add_argument('--delete', help='Delete file at path')
    parser.add_argument('--mkdir', help='Create directory')
    parser.add_argument('--copy', nargs=2, metavar=('SRC', 'DST'), help='Copy file')
    parser.add_argument('--validate', help='Validate path without operating')
    parser.add_argument('--approved', action='store_true', help='Show approved directories')

    # Options
    parser.add_argument('--content', help='Content for write/append')
    parser.add_argument('--user', help='User ID')
    parser.add_argument('--force', action='store_true', help='Force delete outside .tmp')
    parser.add_argument('--recursive', '-r', action='store_true', help='Recursive list')
    parser.add_argument('--pattern', help='Glob pattern for list')
    parser.add_argument('--max-size', type=int, help='Max size for read')

    args = parser.parse_args()
    result = None

    if args.read:
        result = read_file(args.read, max_size=args.max_size, user_id=args.user)

    elif args.write:
        if not args.content:
            print("Error: --content required for write")
            sys.exit(1)
        result = write_file(args.write, args.content, mode='write', user_id=args.user)

    elif args.append:
        if not args.content:
            print("Error: --content required for append")
            sys.exit(1)
        result = write_file(args.append, args.content, mode='append', user_id=args.user)

    elif args.list_dir:
        result = list_directory(
            args.list_dir,
            user_id=args.user,
            recursive=args.recursive,
            pattern=args.pattern
        )

    elif args.delete:
        result = delete_file(args.delete, user_id=args.user, force=args.force)

    elif args.mkdir:
        result = make_directory(args.mkdir, user_id=args.user)

    elif args.copy:
        result = copy_file(args.copy[0], args.copy[1], user_id=args.user)

    elif args.validate:
        is_valid, resolved, error = validate_path(args.validate)
        result = {
            "success": True,
            "valid": is_valid,
            "path": args.validate,
            "resolved": resolved if is_valid else None,
            "error": error if not is_valid else None
        }

    elif args.approved:
        result = get_approved_dirs()

    else:
        print("Error: Must specify an action")
        sys.exit(1)

    if result:
        if result.get('success'):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
