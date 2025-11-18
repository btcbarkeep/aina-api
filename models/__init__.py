# -------------------------
# Building Models
# -------------------------
from .building import (
    BuildingBase,
    BuildingCreate,
    BuildingRead,
    BuildingUpdate,
)

# -------------------------
# Event Models
# -------------------------
from .event import (
    EventType,
    EventBase,
    EventCreate,
    EventRead,
    EventUpdate,
)

# -------------------------
# Document Models
# -------------------------
from .document import (
    DocumentBase,
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
)

# -------------------------
# Event Comments
# -------------------------
from .event_comment import (
    EventCommentBase,
    EventCommentCreate,
    EventCommentRead,
    EventCommentUpdate,
)

# -------------------------
# User Models (Supabase Auth)
# -------------------------
from .user import (
    UserBase,
    UserCreate,
    UserRead,
    UserUpdate,
)

# -------------------------
# Auth Models
# -------------------------
from .auth import LoginRequest, TokenResponse

# -------------------------
# Signup Models
# -------------------------
from .signup import (
    SignupRequest,
    SignupRequestCreate,
)

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

    # users
    "UserBase",
    "UserCreate",
    "UserRead",
    "UserUpdate",

    # auth
    "LoginRequest",
    "TokenResponse",

    # signup
    "SignupRequest",
    "SignupRequestCreate",
]
