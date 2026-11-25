import json
import os
import urllib.request
import urllib.error

API_URL = "http://127.0.0.1:8000"
LOCAL_JSON = "bookings.json"


def fetch_bookings():
    # Try fetching from your running CampusOps server first
    try:
        with urllib.request.urlopen(f"{API_URL}/api/bookings", timeout=2) as res:
            data = json.loads(res.read().decode("utf-8"))
            return data if isinstance(data, list) else data.get("bookings", [])
    except Exception:
        # Fallback to reading local JSON file if server is offline
        if os.path.exists(LOCAL_JSON):
            with open(LOCAL_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else data.get("bookings", [])
        return []


def display_table(records):
    if not records:
        print("\n[!] No booking records found. Make sure app.py is running!\n")
        return

    print("\n" + "-" * 78)
    print(f"{'ID':<10} | {'ROOM':<10} | {'DATE':<10} | {'TIME':<11} | {'REQUESTER':<15} | {'PURPOSE'}")
    print("-" * 78)
    for r in records[:15]:
        b_id = str(r.get("booking_id") or r.get("id", "N/A"))
        room = str(r.get("room_id") or r.get("room", "N/A"))
        date = str(r.get("date", "N/A"))
        t_slot = f"{r.get('start_time', r.get('start', ''))}-{r.get('end_time', r.get('end', ''))}"
        req = str(r.get("requester") or r.get("name", "N/A"))[:15]
        purp = str(r.get("purpose") or r.get("event", "N/A"))
        print(f"{b_id:<10} | {room:<10} | {date:<10} | {t_slot:<11} | {req:<15} | {purp}")
    print("-" * 78 + "\n")


def record_booking_via_api():
    print("\n--- Record New Classroom / Lab Booking ---")
    payload = {
        "room_id": input("Room ID (e.g., LH-101, LAB-201): ").strip(),
        "room": "",
        "category": input("Category (Lecture Hall / Computer Lab / Seminar Hall): ").strip(),
        "requester": input("Requester Name: ").strip(),
        "purpose": input("Purpose / Event: ").strip(),
        "date": input("Date (YYYY-MM-DD): ").strip(),
        "start_time": input("Start Time (HH:MM): ").strip(),
        "end_time": input("End Time (HH:MM): ").strip(),
        "attendees": input("Attendees count: ").strip(),
    }
    payload["room"] = payload["room_id"]

    try:
        payload["attendees"] = int(payload["attendees"])
    except ValueError:
        print("\n[VALIDATION ERROR] Attendees must be a valid number.\n")
        return

    req = urllib.request.Request(
        f"{API_URL}/api/bookings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=3) as res:
            print(f"\n[SUCCESS] Booking confirmed! Response: {res.read().decode('utf-8')}\n")
    except urllib.error.HTTPError as e:
        print(f"\n[SERVER REJECTED ({e.code})] {e.read().decode('utf-8')}\n")
    except Exception as e:
        print(f"\n[CONNECTION ERROR] Start app.py in Terminal 1 first! ({e})\n")


def search_bookings():
    kw = input("\nEnter search keyword (Room, Requester, or Purpose): ").strip().lower()
    records = fetch_bookings()
    matches = [r for r in records if kw in json.dumps(r).lower()]
    display_table(matches)


def main():
    while True:
        print("=== CAMPUSOPS TERMINAL CLI ===")
        print("1. View All Bookings")
        print("2. Record New Booking (Tests Validation & Conflict Check)")
        print("3. Search Bookings")
        print("4. Exit")
        choice = input("Choose (1-4): ").strip()

        if choice == "1":
            display_table(fetch_bookings())
        elif choice == "2":
            record_booking_via_api()
        elif choice == "3":
            search_bookings()
        elif choice == "4":
            print("Exiting CLI.")
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
