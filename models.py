"""Plain data classes shared by every layer."""
from dataclasses import dataclass, fields

CONFIRMED = "Confirmed"
PENDING = "Pending"
CANCELLED = "Cancelled"
CONFLICT_FLAGGED = "Conflict Flagged"


@dataclass(frozen=True)
class Resource:
    id: str
    name: str
    type: str
    capacity: int


@dataclass
class Booking:
    id: str
    resource_id: str
    requester: str
    role: str
    purpose: str
    date: str          # YYYY-MM-DD
    start: str         # HH:MM (24h)
    end: str           # HH:MM (24h)
    capacity: int
    status: str = CONFIRMED
    created_at: str = ""


BOOKING_FIELDS = [f.name for f in fields(Booking)]