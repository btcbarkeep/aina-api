# core/roles.py

# ============================================
# CENTRALIZED ROLE → PERMISSIONS MAP
# ============================================
ROLE_PERMISSIONS = {
    "super_admin": ["*"],  # Full access to everything

    "admin": [
        "users:read", "users:write",
        "buildings:read", "buildings:write",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "access:read", "access:write"
    ],

    "hoa": [
        "buildings:read", "buildings:write",
        "events:read", "events:write",
        "documents:read", "documents:write",
    ],

    "contractor": [
        "events:write",
        "documents:write",
        "events:read",
        "documents:read",
    ],

    "auditor": [
        "events:read",
        "documents:read",
        "buildings:read",
    ],

    # fallback
    "guest": []
}
