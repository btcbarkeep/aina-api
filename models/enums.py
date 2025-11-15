# models/enums.py
from enum import Enum

class EventType(str, Enum):
    maintenance = "maintenance"
    notice = "notice"
    assessment = "assessment"
    plumbing = "plumbing"
    electrical = "electrical"
    general = "general"
