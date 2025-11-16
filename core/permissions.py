ROLE_PERMISSIONS = {
    "super_admin": ["*"],

    "admin": [
        "users:read", "users:write",
        "buildings:read", "buildings:write",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "access:read", "access:write",
        "contractors:read", "contractors:write",
    ],

    "property_manager": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
        "access:read",
    ],

    "hoa": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
    ],

    "hoa_staff": [
        "buildings:read",
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
    ],

    "contractor": [
        "events:read", "events:write",
        "documents:read", "documents:write",
        "contractors:read",
    ],

    "contractor_staff": [
        "events:read",
        "events:write",
        "documents:read",
        "contractors:read",
    ],

    "auditor": [
        "events:read",
        "documents:read",
        "buildings:read",
        "contractors:read",
    ],

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

    "buyer": [
        "buildings:read",
        "events:read",
        "documents:read",
    ],

    "guest": [],
}
