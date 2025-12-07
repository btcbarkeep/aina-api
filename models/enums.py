from enum import Enum


class BaseStrEnum(str, Enum):
    """
    Base enum that serializes cleanly to a string
    and provides a .list() method for UI dropdowns.
    """

    def __str__(self):
        return str(self.value)

    @classmethod
    def list(cls):
        return [item.value for item in cls]


# -----------------------------------------------------
# EVENT TYPE
# -----------------------------------------------------
class EventType(BaseStrEnum):
    """Used for categorizing events (AOAO notices, repairs, etc.)."""

    maintenance = "maintenance"
    notice = "notice"
    assessment = "assessment"
    plumbing = "plumbing"
    electrical = "electrical"
    general = "general"
    warning = "Warning"  # AOAO violations, warnings, etc.


# -----------------------------------------------------
# EVENT SEVERITY
# -----------------------------------------------------
class EventSeverity(BaseStrEnum):
    """Indicates importance/priority of the event."""

    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


# -----------------------------------------------------
# EVENT STATUS
# -----------------------------------------------------
class EventStatus(BaseStrEnum):
    """Workflow state for an event."""

    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"  # Alternative to resolved


# -----------------------------------------------------
# CONTRACTOR ROLE
# -----------------------------------------------------
class ContractorRole(BaseStrEnum):
    """Type of contractor/service provider."""

    electrician = "electrician"
    plumber = "plumber"
    painter = "painter"
    handyman = "handyman"
    inspector = "inspector"
    appraiser = "appraiser"
    landscaper = "landscaper"
    other = "other"


# -----------------------------------------------------
# CONTRACTOR SUBSCRIPTION TIER
# -----------------------------------------------------
class SubscriptionTier(BaseStrEnum):
    """Contractor subscription tier for UI display and feature access."""

    free = "free"
    paid = "paid"


# -----------------------------------------------------
# SUBSCRIPTION STATUS
# -----------------------------------------------------
class SubscriptionStatus(BaseStrEnum):
    """Stripe subscription status."""

    active = "active"
    canceled = "canceled"
    past_due = "past_due"
    unpaid = "unpaid"
    trialing = "trialing"
    incomplete = "incomplete"
    incomplete_expired = "incomplete_expired"
