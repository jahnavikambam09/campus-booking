
import json
import pytest
from pathlib import Path
from datetime import datetime


def time_to_minutes(time_str: str) -> int:
    hours, minutes = map(int, time_str.split(":"))
    return hours * 60 + minutes


def has_schedule_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    s_a, e_a = time_to_minutes(start_a), time_to_minutes(end_a)
    s_b, e_b = time_to_minutes(start_b), time_to_minutes(end_b)
    return s_a < e_b and e_a > s_b


def validate_booking_payload(payload: dict, rooms_config: dict) -> list[str]:
    errors = []
    room = payload.get("room_id", "").strip().upper()
    if room not in rooms_config:
        errors.append("Invalid room ID")
    attendees = payload.get("attendees", 0)
    if not isinstance(attendees, int) or attendees <= 0:
        errors.append("Attendees must be a positive integer")
    elif room in rooms_config and attendees > rooms_config[room]["capacity"]:
        errors.append("Capacity exceeded")
    if time_to_minutes(payload["end_time"]) <= time_to_minutes(payload["start_time"]):
        errors.append("End time must be after start time")
    return errors


# --- AUTOMATED UNIT TESTS ---

def test_exact_time_overlap_detected():
    assert has_schedule_overlap("10:00", "11:00", "10:00", "11:00") is True


def test_partial_overlap_detected():
    assert has_schedule_overlap("10:30", "11:30", "10:00", "11:00") is True


def test_adjacent_back_to_back_bookings_allowed():
    assert has_schedule_overlap("11:00", "12:00", "10:00", "11:00") is False


def test_validation_rejects_capacity_overflow():
    rooms = {"LAB-201": {"capacity": 40}}
    errs = validate_booking_payload(
        {"room_id": "LAB-201", "attendees": 75, "start_time": "09:00", "end_time": "10:00"},
        rooms,
    )
    assert "Capacity exceeded" in errs


def test_validation_rejects_inverted_time_range():
    rooms = {"LH-101": {"capacity": 60}}
    errs = validate_booking_payload(
        {"room_id": "LH-101", "attendees": 30, "start_time": "14:00", "end_time": "13:00"},
        rooms,
    )
    assert "End time must be after start time" in errs


def test_corrupted_json_recovery(tmp_path: Path):
    corrupt_file = tmp_path / "bookings.json"
    corrupt_file.write_text("{corrupted_json:", encoding="utf-8")

    try:
        json.loads(corrupt_file.read_text(encoding="utf-8"))
        recovered = False
    except json.JSONDecodeError:
        corrupt_file.write_text("[]", encoding="utf-8")
        recovered = True

    assert recovered is True
    assert json.loads(corrupt_file.read_text(encoding="utf-8")) == []
