# core/permissions.py

ROLE_PERMISSIONS = {
    # ----------------------------------------------------
    # Full System Access
    # ----------------------------------------------------
    "super_admin": ["*"],

    # ----------------------------------------------------
    # System Admin
    # ----------------------------------------------------
    "admin": [
        "users:read", "users:write",
        "buildings:read", "buildings:write",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "access:read", "access:write",
        "contractors:read", "contractors:write",

        # ⭐ NEW — needed for POST /admin-daily/send
        "admin:daily_send",
    ],

    # ----------------------------------------------------
    # Property Manager
    # ----------------------------------------------------
    "property_manager": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
        "access:read",
    ],

    # ----------------------------------------------------
    # HOA Manager
    # ----------------------------------------------------
    "hoa": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
    ],

    # ----------------------------------------------------
    # HOA Staff
    # ----------------------------------------------------
    "hoa_staff": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
    ],

    # ----------------------------------------------------
    # Contractors
    # ----------------------------------------------------
    "contractor": [
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
    ],

    "contractor_staff": [
        "events:read", "events:write",
        "documents:read",
        "contractors:read",
    ],

    # ----------------------------------------------------
    # Auditors
    # ----------------------------------------------------
    "auditor": [
        "events:read",
        "documents:read",
        "buildings:read",
        "contractors:read",
    ],

    # ----------------------------------------------------
    # Owners / Tenants
    # ----------------------------------------------------
    "owner": [
        "events:read",
        "documents:read",
        "buildings:read",
    ],

    "tenant": [
        "events:read",
        "documents:read",
        "buildings:read",
    ],

    # ----------------------------------------------------
    # AinaReports Purchasers
    # ----------------------------------------------------
    "buyer": [
        "buildings:read",
        "events:read",
        "documents:read",
    ],

    # ----------------------------------------------------
    # No Access
    # ----------------------------------------------------
    "guest": [],
}
