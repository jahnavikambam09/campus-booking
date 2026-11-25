"""Persistence: atomic JSON + CSV writes, audit log, self-healing, and one lock for all of it.

Every read-modify-write sequence must run inside ``with store.lock:`` so that two
HTTP threads can never both book the same slot.
"""
import json
import logging
import os
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .exports import bookings_to_csv
from .models import Booking

log = logging.getLogger(__name__)
MAX_AUDIT_MESSAGE = 300


def _atomic_write(path: Path, text: str) -> None:
    """Write to a temp file, flush to disk, then swap it in. A crash never leaves half a file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


class BookingStore:
    def __init__(self, data_dir, seed_factory):
        self.data_dir = Path(data_dir)
        self.json_file = self.data_dir / "bookings.json"
        self.csv_file = self.data_dir / "bookings.csv"
        self.audit_file = self.data_dir / "audit.log"
        self._seed_factory = seed_factory
        self.lock = threading.RLock()   # re-entrant: load()/save() may be called while it is held

    # ----- bookings -----
    def load(self) -> list:
        with self.lock:
            try:
                raw = json.loads(self.json_file.read_text(encoding="utf-8"))
                return [Booking(**item) for item in raw]
            except FileNotFoundError:
                reason = "missing"
            except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
                reason = "corrupted"
                self._quarantine()
            bookings = self._seed_factory()
            self.save(bookings)
            self.audit(f"SELF_HEAL bookings.json {reason}; regenerated seed data")
            return bookings

    def save(self, bookings) -> None:
        with self.lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            rows = [asdict(b) for b in bookings]
            _atomic_write(self.json_file, json.dumps(rows, indent=2))
            try:
                _atomic_write(self.csv_file, bookings_to_csv(rows))
            except PermissionError:
                # Windows: the CSV is open in Excel. JSON is the source of truth, so carry on.
                log.warning("bookings.csv is locked by another program; skipped CSV refresh")

    def _quarantine(self) -> None:
        """Keep the corrupted file for inspection instead of silently destroying it."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            os.replace(self.json_file, self.json_file.with_name(f"bookings.corrupt-{stamp}.json"))
        except OSError:
            log.warning("could not quarantine corrupted bookings.json")

    # ----- audit log -----
    def audit(self, message: str) -> None:
        # One line per event: strip newlines so a user-supplied name cannot forge log entries.
        clean = " ".join(str(message).split())[:MAX_AUDIT_MESSAGE]
        with self.lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.audit_file, "a", encoding="utf-8") as handle:
                handle.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {clean}\n")

    def read_audit(self) -> str:
        with self.lock:
            if not self.audit_file.exists():
                return ""
            return self.audit_file.read_text(encoding="utf-8")

    def count_audit(self, keyword: str) -> int:
        return sum(keyword in line for line in self.read_audit().splitlines())

    def reset_audit(self) -> None:
        with self.lock:
            self.audit_file.unlink(missing_ok=True)