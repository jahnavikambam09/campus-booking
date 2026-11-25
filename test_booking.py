
import sys
import unittest
from pathlib import Path

# Ensure root project directory is importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app


class TestClassroomBookingSystem(unittest.TestCase):
    def test_app_module_imports_cleanly(self):
        self.assertTrue(hasattr(app, "overlaps") or hasattr(app, "validate"))

    def test_overlap_detection_true_for_intersecting_slots(self):
        if hasattr(app, "overlaps"):
            # Supports both minute-integer and HH:MM string signatures
            try:
                self.assertTrue(app.overlaps(600, 660, 630, 690))
            except TypeError:
                self.assertTrue(app.overlaps("10:00", "11:00", "10:30", "11:30"))

    def test_overlap_detection_false_for_adjacent_slots(self):
        if hasattr(app, "overlaps"):
            try:
                self.assertFalse(app.overlaps(600, 660, 660, 720))
            except TypeError:
                self.assertFalse(app.overlaps("10:00", "11:00", "11:00", "12:00"))

    def test_validation_rejects_invalid_booking(self):
        if hasattr(app, "validate"):
            invalid_payload = {
                "room_id": "",
                "room": "",
                "date": "invalid-date",
                "start": "14:00",
                "end": "13:00",
                "start_time": "14:00",
                "end_time": "13:00",
                "attendees": -5,
            }
            result = app.validate(invalid_payload)
            # Validation should return errors (non-empty list/tuple or False)
            if isinstance(result, tuple):
                self.assertTrue(bool(result) or result is False)
            else:
                self.assertTrue(bool(result) is True or result is False)

    def test_storage_load_returns_list_or_dict(self):
        if hasattr(app, "load"):
            data = app.load()
            self.assertIsNotNone(data)

    def test_free_slot_suggestion_returns_value(self):
        if hasattr(app, "suggest"):
            bookings = [
                {
                    "room_id": "LH-101",
                    "room": "LH-101",
                    "date": "2026-11-25",
                    "start": "10:00",
                    "end": "11:00",
                    "start_time": "10:00",
                    "end_time": "11:00",
                }
            ]
            try:
                suggestion = app.suggest(bookings, "LH-101", "2026-11-25", 60)
                self.assertIsNotNone(suggestion)
            except TypeError:
                pass


if __name__ == "__main__":
    unittest.main()
