"""Pure business rules: no files, no HTTP, no globals. Easy to unit test."""
from dataclasses import replace
from datetime import datetime

from .confi import SETTINGS, Settings
from .models import CANCELLED, Booking
from .timeutil import to_hhmm, to_minutes

REQUIRED_FIELDS = ["resource_id", "requester", "role", "purpose", "date", "start", "end", "capacity"]
MAX_NAME_LEN = 80
MAX_PURPOSE_LEN = 120


def overlaps(new_start: int, new_end: int, existing_start: int, existing_end: int) -> bool:
    """Half-open interval test: back-to-back bookings (10:00-11:00 then 11:00-12:00) are allowed."""
    return new_start < existing_end and new_end > existing_start


def _active_on(bookings, resource_id: str, day: str):
    return [b for b in bookings
            if b.resource_id == resource_id and b.date == day and b.status != CANCELLED]


def find_conflicts(new: Booking, bookings) -> list:
    start, end = to_minutes(new.start), to_minutes(new.end)
    return [b for b in _active_on(bookings, new.resource_id, new.date)
            if overlaps(start, end, to_minutes(b.start), to_minutes(b.end))]


def suggest_slots(new: Booking, bookings, cfg: Settings = SETTINGS, limit: int = 2) -> list:
    """Earliest free windows (same room, same day) long enough for the request."""
    duration = to_minutes(new.end) - to_minutes(new.start)
    busy = sorted((to_minutes(b.start), to_minutes(b.end))
                  for b in _active_on(bookings, new.resource_id, new.date))
    cursor, found = cfg.open_min, []
    for start, end in busy + [(cfg.close_min, cfg.close_min)]:
        if start - cursor >= duration:
            found.append({"start": to_hhmm(cursor), "end": to_hhmm(cursor + duration)})
        cursor = max(cursor, end)
    return found[:limit]


def suggest_rooms(new: Booking, bookings, cfg: Settings = SETTINGS, limit: int = 3) -> list:
    """Other rooms that are free at the same time and big enough (smallest fit first)."""
    options = []
    for room in cfg.rooms.values():
        if room.id == new.resource_id or room.capacity < new.capacity:
            continue
        if not find_conflicts(replace(new, resource_id=room.id), bookings):
            options.append({"resource_id": room.id, "name": room.name, "capacity": room.capacity})
    options.sort(key=lambda o: o["capacity"])
    return options[:limit]


def validate(data: dict, cfg: Settings = SETTINGS, now: datetime = None) -> dict:
    """Return {field: message}. An empty dict means the request is valid."""
    now = now or datetime.now()
    errors = {k: "This field is required" for k in REQUIRED_FIELDS if not str(data.get(k, "")).strip()}

    room = cfg.rooms.get(str(data.get("resource_id", "")))
    if "resource_id" not in errors and room is None:
        errors["resource_id"] = "Unknown room"
    if "role" not in errors and data["role"] not in cfg.roles:
        errors["role"] = "Unknown role"
    if "requester" not in errors and len(data["requester"]) > MAX_NAME_LEN:
        errors["requester"] = f"At most {MAX_NAME_LEN} characters"
    if "purpose" not in errors and len(data["purpose"]) > MAX_PURPOSE_LEN:
        errors["purpose"] = f"At most {MAX_PURPOSE_LEN} characters"

    day = None
    if "date" not in errors:
        try:
            day = datetime.strptime(data["date"], "%Y-%m-%d").date()
            if day < now.date():
                errors["date"] = "Date is in the past"
        except ValueError:
            errors["date"] = "Use format YYYY-MM-DD"

    minutes = {}
    for key in ("start", "end"):
        if key not in errors:
            try:
                minutes[key] = to_minutes(data[key])
            except ValueError:
                errors[key] = "Use format HH:MM"
    if len(minutes) == 2:
        if minutes["end"] <= minutes["start"]:
            errors["end"] = "End time must be after start time"
        elif minutes["start"] < cfg.open_min or minutes["end"] > cfg.close_min:
            errors["start"] = "Bookings run 08:00 to 20:00"
        elif day == now.date() and minutes["start"] < now.hour * 60 + now.minute:
            errors["start"] = "Start time has already passed"

    if "capacity" not in errors:
        try:
            seats = int(data["capacity"])
            if seats <= 0:
                errors["capacity"] = "Capacity must be at least 1"
            elif room and seats > room.capacity:
                errors["capacity"] = f"Exceeds room capacity ({room.capacity})"
        except ValueError:
            errors["capacity"] = "Capacity must be a number"
    return errors