# models/enums.py

from enum import Enum


class BaseStrEnum(str, Enum):
    """
    Ensures enum serializes cleanly as a plain string
    and supports helper .list() method for dropdowns.
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
    maintenance = "maintenance"
    notice = "notice"
    assessment = "assessment"
    plumbing = "plumbing"
    electrical = "electrical"
    general = "general"

    """
    Used for categorizing events (HOA notices, repairs, etc.)
    """


# -----------------------------------------------------
# EVENT SEVERITY
# -----------------------------------------------------
class EventSeverity(BaseStrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"

    """
    Indicates importance/priority of event.
    """


# -----------------------------------------------------
# EVENT STATUS
# -----------------------------------------------------
class EventStatus(BaseStrEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"

    """
    Workflow state for an event.
    """
