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

        # Explicit user-management permissions
        "users:create",
        "users:update",
        "users:delete",

        # Approval workflow
        "requests:approve",
    ],

    # =====================================================
    # SYSTEM ADMIN
    # =====================================================
    "admin": [
        # Core user management
        "users:read", "users:write",
        "users:create", "users:update", "users:delete",

        # Building management
        "buildings:read", "buildings:write",

        # Events
        "events:read", "events:write",

        # Documents
        "documents:read", "documents:write",

        # Access control
        "user_access:read", "user_access:write",

        # Contractor management
        "contractors:read", "contractors:write",

        # System-level actions
        "admin:daily_send",
        "admin:set_password",

        # Approval workflow
        "requests:approve",
    ],

    # =====================================================
    # PROPERTY MANAGER — cannot create/edit buildings
    # =====================================================
    "property_manager": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
        "user_access:read", "user_access:write",
    ],

    # =====================================================
    # AOAO MANAGER
    # =====================================================
    "aoao": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
    ],

    # =====================================================
    # AOAO STAFF
    # =====================================================
    "aoao_staff": [
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
        "events:read", "events:write",
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
