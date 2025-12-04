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
# Unit Models
# -------------------------
from .unit import (
    UnitBase,
    UnitCreate,
    UnitRead,
    UnitUpdate,
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
# Enums
# -------------------------
from .enums import (
    EventType as EventTypeEnum,
    EventSeverity,
    EventStatus,
    ContractorRole,
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
# Redaction Models - REMOVED (replaced with manual redaction)
# -------------------------

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

    # units
    "UnitBase",
    "UnitCreate",
    "UnitRead",
    "UnitUpdate",

    # events
    "EventType",
    "EventBase",
    "EventCreate",
    "EventRead",
    "EventUpdate",
    
    # enums
    "EventSeverity",
    "EventStatus",
    "ContractorRole",

    # documents
    "DocumentBase",
    "DocumentCreate",
    "DocumentRead",
    "DocumentUpdate",

    # redaction - REMOVED

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
