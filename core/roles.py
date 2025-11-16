# ============================================
# CENTRALIZED ROLE → PERMISSIONS MAP
# ============================================
ROLE_PERMISSIONS = {

    # =====================================================
    # SUPER ADMIN — Full access to everything
    # =====================================================
    "super_admin": ["*"],


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
    ],


    # =====================================================
    # PROPERTY MANAGER — CANNOT create/edit buildings
    # =====================================================
    "property_manager": [
        # ❌ building write removed
        "buildings:read",

        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",

        # Optional: remove this if you don't want PMs
        # assigning user access to buildings
        "access:read", "access:write",
    ],


    # =====================================================
    # AOAO MANAGER (similar to property_manager)
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
    "guest": []
}
