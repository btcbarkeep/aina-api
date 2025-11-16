from enum import Enum


class EventType(str, Enum):
    maintenance = "maintenance"
    notice = "notice"
    assessment = "assessment"
    plumbing = "plumbing"
    electrical = "electrical"
    general = "general"


class EventSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class EventStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
