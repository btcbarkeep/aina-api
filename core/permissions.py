ROLE_PERMISSIONS = {
    # ----------------------------------------------------
    # Full System Access (Master)
    # ----------------------------------------------------
    "super_admin": [
        "*",
        "admin:daily_send",
        "admin:set_password",
    ],

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

        "admin:daily_send",
        "admin:set_password",
    ],

    # ----------------------------------------------------
    # Property Manager (NO building access assignment)
    # ----------------------------------------------------
    "property_manager": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",

        # ❌ Removed: "access:write"
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
    # Contractor + Staff
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
    # Audit Roles
    # ----------------------------------------------------
    "auditor": [
        "events:read",
        "documents:read",
        "buildings:read",
        "contractors:read",
    ],

    # ----------------------------------------------------
    # Owner / Tenant
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
    # AinaReports Buyer
    # ----------------------------------------------------
    "buyer": [
        "buildings:read",
        "events:read",
        "documents:read",
    ],

    # ----------------------------------------------------
    # Guest
    # ----------------------------------------------------
    "guest": [],
}
