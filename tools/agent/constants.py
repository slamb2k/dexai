"""
DexAI Agent Constants

Single-tenant constants used throughout the system.
DexAI is a single-user system — all operations belong to the owner.
"""

# The single owner user ID used across all subsystems.
# Replaces dynamic user_id parameters that were threaded through
# 50+ function signatures for multi-tenancy that was never used.
OWNER_USER_ID = "owner"
