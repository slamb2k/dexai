"""
Media Processing Submodules (Phase 15d)

Re-exports key processors for convenient access:
- LocationProcessor: Geocoding and place lookup
- ContactProcessor: vCard parsing and contact extraction
- StorageCleanup: Temp file and DB entry cleanup
"""

from __future__ import annotations

try:
    from tools.channels.media.location_processor import (
        LocationProcessor,
        get_location_processor,
    )
except ImportError:
    LocationProcessor = None  # type: ignore[assignment, misc]
    get_location_processor = None  # type: ignore[assignment]

try:
    from tools.channels.media.contact_processor import (
        ContactProcessor,
        get_contact_processor,
    )
except ImportError:
    ContactProcessor = None  # type: ignore[assignment, misc]
    get_contact_processor = None  # type: ignore[assignment]

try:
    from tools.channels.media.storage_cleanup import (
        StorageCleanup,
        get_storage_cleanup,
        run_cleanup,
    )
except ImportError:
    StorageCleanup = None  # type: ignore[assignment, misc]
    get_storage_cleanup = None  # type: ignore[assignment]
    run_cleanup = None  # type: ignore[assignment]

__all__ = [
    "LocationProcessor",
    "get_location_processor",
    "ContactProcessor",
    "get_contact_processor",
    "StorageCleanup",
    "get_storage_cleanup",
    "run_cleanup",
]
