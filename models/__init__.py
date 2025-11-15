from .building import (
    BuildingBase,
    Building,
    BuildingCreate,
    BuildingRead,
    BuildingUpdate,
)

from .event import (
    EventType,
    EventBase,
    Event,
    EventCreate,
    EventRead,
    EventUpdate,
)

from .document import (
    DocumentBase,
    Document,
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
)

from .user import (
    User,
    UserBuildingAccess,
    PasswordResetToken,
)

from .auth import LoginRequest, TokenResponse

from .signup import SignupRequest


__all__ = [
    # buildings
    "BuildingBase",
    "Building",
    "BuildingCreate",
    "BuildingRead",
    "BuildingUpdate",

    # events
    "EventType",
    "EventBase",
    "Event",
    "EventCreate",
    "EventRead",
    "EventUpdate",

    # documents
    "DocumentBase",
    "Document",
    "DocumentCreate",
    "DocumentRead",
    "DocumentUpdate",

    # user + permissions
    "User",
    "UserBuildingAccess",
    "PasswordResetToken",

    # auth models
    "LoginRequest",
    "TokenResponse",

    # signup / onboarding requests
    "SignupRequest",
]
