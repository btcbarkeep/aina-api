from .building import (
    BuildingBase,
    BuildingCreate,
    BuildingRead,
    BuildingUpdate,
)

from .event import (
    EventType,
    EventBase,
    EventCreate,
    EventRead,
    EventUpdate,
)

from .document import (
    DocumentBase,
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
)

from .event_comment import (
    EventCommentBase,
    EventCommentCreate,
    EventCommentRead,
    EventCommentUpdate,
)

# NEW: Supabase User Models (Pydantic only)
from .user import (
    UserBase,
    UserCreate,
    UserRead,
    UserUpdate,
)

from .auth import LoginRequest, TokenResponse

from .signup import SignupRequest


__all__ = [
    # buildings
    "BuildingBase",
    "BuildingCreate",
    "BuildingRead",
    "BuildingUpdate",

    # events
    "EventType",
    "EventBase",
    "EventCreate",
    "EventRead",
    "EventUpdate",

    # documents
    "DocumentBase",
    "DocumentCreate",
    "DocumentRead",
    "DocumentUpdate",

    # event comments
    "EventCommentBase",
    "EventCommentCreate",
    "EventCommentRead",
    "EventCommentUpdate",

    # Supabase user models
    "UserBase",
    "UserCreate",
    "UserRead",
    "UserUpdate",

    # auth
    "LoginRequest",
    "TokenResponse",

    # signup
    "SignupRequest",
]
