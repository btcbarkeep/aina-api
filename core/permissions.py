# ============================================
# CENTRALIZED ROLE → PERMISSIONS MAP
# ============================================
ROLE_PERMISSIONS = {

    # =====================================================
    # SUPER ADMIN — Full access to everything
    # =====================================================
    "super_admin": [
        "*",
        # Explicit system-level permissions
        "admin:daily_send",
        "admin:set_password",
    ],

    # =====================================================
    # SYSTEM ADMIN
    # =====================================================
    "admin": [
        "users:read", "users:write",
        "buildings:read", "buildings:write",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "access:read", "access:write",
        "contractors:read", "contractors:write",

        # Required for daily summary emails
        "admin:daily_send",

        # Required for POST /admin/admin-set-password
        "admin:set_password",
    ],

    # =====================================================
    # PROPERTY MANAGER — cannot create/edit buildings
    # =====================================================
    "property_manager": [
        "buildings:read",

        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",

        # You previously allowed this — keeping it as-is
        "access:read", "access:write",
    ],

    # =====================================================
    # AOAO MANAGER
    # =====================================================
    "hoa": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
    ],

    # =====================================================
    # AOAO STAFF
    # =====================================================
    "hoa_staff": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
    ],

    # =====================================================
    # CONTRACTOR
    # =====================================================
    "contractor": [
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
    ],

    # =====================================================
    # CONTRACTOR STAFF
    # =====================================================
    "contractor_staff": [
        "events:read",
        "events:write",
        "documents:read",
        "contractors:read",
    ],

    # =====================================================
    # AUDITOR
    # =====================================================
    "auditor": [
        "events:read",
        "documents:read",
        "buildings:read",
        "contractors:read",
    ],

    # =====================================================
    # OWNER
    # =====================================================
    "owner": [
        "events:read",
        "documents:read",
        "buildings:read",
    ],

    # =====================================================
    # TENANT
    # =====================================================
    "tenant": [
        "events:read",
        "documents:read",
        "buildings:read",
    ],

    # =====================================================
    # BUYER — AinaReports purchasers
    # =====================================================
    "buyer": [
        "buildings:read",
        "events:read",
        "documents:read",
    ],

    # =====================================================
    # FALLBACK
    # =====================================================
    "guest": [],
}
