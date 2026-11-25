"""CampusOps - Classroom Resource Booking. ONE file, Python standard library only.
Run:  python app.py      then open  http://127.0.0.1:8000
"""
import csv, io, json, os, random
from collections import Counter
from dataclasses import dataclass, asdict, fields
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
JSON_F, CSV_F, AUDIT_F = DATA / "bookings.json", DATA / "bookings.csv", DATA / "audit.log"
OPEN, CLOSE = 8 * 60, 20 * 60


@dataclass
class Resource:
    id: str; name: str; type: str; capacity: int


@dataclass
class Booking:
    id: str; resource_id: str; requester: str; role: str; purpose: str
    date: str; start: str; end: str; capacity: int
    status: str = "Confirmed"; created_at: str = ""


FIELDS = [f.name for f in fields(Booking)]
ROOMS = {r.id: r for r in [
    Resource("LH-101", "Lecture Hall 101", "Lecture Hall", 120), Resource("LH-102", "Lecture Hall 102", "Lecture Hall", 90),
    Resource("LH-201", "Lecture Hall 201", "Lecture Hall", 60), Resource("LAB-301", "Computer Lab 301", "Computer Lab", 40),
    Resource("LAB-302", "Computer Lab 302", "Computer Lab", 35), Resource("LAB-401", "Physics Lab 401", "Computer Lab", 30),
    Resource("SH-01", "Seminar Hall A", "Seminar Hall", 80), Resource("SH-02", "Seminar Hall B", "Seminar Hall", 50)]}
SLOTS = [("08:00", "10:00"), ("10:00", "11:30"), ("11:30", "13:00"), ("14:00", "16:00"), ("16:00", "18:00"), ("18:00", "20:00")]
PEOPLE = [("Dr. Rao", "Faculty"), ("Prof. Sharma", "Faculty"), ("Ananya K.", "Student Club"), ("Dr. Iyer", "Faculty"), ("Rahul M.", "Student Rep"), ("Admin Office", "Staff")]
PURPOSES = ["Data Structures lecture", "Python workshop", "Guest talk", "Lab exam", "Club meeting", "Thesis defence", "Placement drive", "Robotics demo", "Revision class"]
REQ = ["resource_id", "requester", "role", "purpose", "date", "start", "end", "capacity"]


# ---------- time + conflict logic ----------
def m(t): h, mi = t.split(":"); return int(h) * 60 + int(mi)
def hm(x): return f"{x // 60:02d}:{x % 60:02d}"
def overlaps(ns, ne, es, ee): return ns < ee and ne > es   # touching edges are allowed


def find_conflicts(n, bs):
    return [b for b in bs if b.resource_id == n.resource_id and b.date == n.date and b.status != "Cancelled"
            and overlaps(m(n.start), m(n.end), m(b.start), m(b.end))]


def suggest(n, bs, limit=2):
    dur, cur, out = m(n.end) - m(n.start), OPEN, []
    busy = sorted((m(b.start), m(b.end)) for b in bs if b.resource_id == n.resource_id and b.date == n.date and b.status != "Cancelled")
    for s, e in busy + [(CLOSE, CLOSE)]:
        if s - cur >= dur: out.append({"start": hm(cur), "end": hm(cur + dur)})
        cur = max(cur, e)
    return out[:limit]


def validate(d):
    e = {k: "This field is required" for k in REQ if not str(d.get(k, "")).strip()}
    room = ROOMS.get(str(d.get("resource_id", "")))
    if "resource_id" not in e and not room: e["resource_id"] = "Unknown room"
    day, mins = None, {}
    if "date" not in e:
        try:
            day = datetime.strptime(d["date"], "%Y-%m-%d").date()
            if day < date.today(): e["date"] = "Date is in the past"
        except ValueError: e["date"] = "Use format YYYY-MM-DD"
    for k in ("start", "end"):
        if k not in e:
            try: datetime.strptime(d[k], "%H:%M"); mins[k] = m(d[k])
            except ValueError: e[k] = "Use format HH:MM"
    if len(mins) == 2:
        now = datetime.now()
        if mins["end"] <= mins["start"]: e["end"] = "End time must be after start time"
        elif mins["start"] < OPEN or mins["end"] > CLOSE: e["start"] = "Bookings run 08:00 to 20:00"
        elif day == date.today() and mins["start"] < now.hour * 60 + now.minute: e["start"] = "Start time has already passed"
    if "capacity" not in e:
        try:
            c = int(d["capacity"])
            if c <= 0: e["capacity"] = "Capacity must be at least 1"
            elif room and c > room.capacity: e["capacity"] = f"Exceeds room capacity ({room.capacity})"
        except ValueError: e["capacity"] = "Capacity must be a number"
    return e


# ---------- persistence (self-healing JSON + CSV) ----------
def audit(msg):
    DATA.mkdir(exist_ok=True)
    with open(AUDIT_F, "a", encoding="utf-8") as f: f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def seed():
    rnd = random.Random(22)
    combos = [(r, d, s) for r in ROOMS.values() for d in range(7) for s in SLOTS]
    rnd.shuffle(combos); out = []
    for i, (r, d, s) in enumerate(combos[:38], 1):
        name, role = rnd.choice(PEOPLE)
        st = "Pending" if i % 6 == 0 else "Conflict Flagged" if i in (11, 23) else "Confirmed"
        age = timedelta(days=3) if i % 12 == 0 else timedelta(hours=1)
        out.append(Booking(f"B{i:03d}", r.id, name, role, rnd.choice(PURPOSES), (date.today() + timedelta(d)).isoformat(),
                           s[0], s[1], r.capacity if i == 5 else rnd.randint(10, r.capacity), st,
                           (datetime.now() - age).isoformat(timespec="seconds")))
    return out


def save(bs):
    DATA.mkdir(exist_ok=True)
    tmp = JSON_F.with_suffix(".tmp"); tmp.write_text(json.dumps([asdict(b) for b in bs], indent=2), encoding="utf-8"); os.replace(tmp, JSON_F)
    tmp = CSV_F.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(asdict(b) for b in bs)
    os.replace(tmp, CSV_F)


def load():
    try: return [Booking(**d) for d in json.loads(JSON_F.read_text(encoding="utf-8"))]
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        bs = seed(); save(bs); audit("SELF_HEAL bookings.json missing or corrupted; regenerated seed data"); return bs


def warnings(b):
    w = []
    if b.status == "Pending" and datetime.fromisoformat(b.created_at) < datetime.now() - timedelta(hours=48): w.append("Overdue approval")
    if b.capacity >= 0.9 * ROOMS[b.resource_id].capacity: w.append("High capacity")
    return w


def create(p, bs):
    p = {k: str(v).strip() for k, v in p.items()}
    err = validate(p)
    if err: audit(f"VALIDATION_REJECTED {sorted(err)}"); return None, err, [], []
    nid = max([int(b.id[1:]) for b in bs] + [0]) + 1
    n = Booking(f"B{nid:03d}", p["resource_id"], p["requester"], p["role"], p["purpose"], p["date"], p["start"], p["end"],
                int(p["capacity"]), "Confirmed", datetime.now().isoformat(timespec="seconds"))
    c = find_conflicts(n, bs)
    if c:
        audit(f"CONFLICT_REJECTED {n.resource_id} {n.date} {n.start}-{n.end} clashes with {c[0].id}")
        return None, {}, c, suggest(n, bs)
    bs.append(n); save(bs); audit(f"BOOKING_CREATED {n.id} {n.resource_id} {n.date} {n.start}-{n.end} by {n.requester}")
    return n, {}, [], []


def stats(bs):
    act = [b for b in bs if b.status != "Cancelled"]
    hrs = {f"{h:02d}:00": sum(m(b.start) < (h + 1) * 60 and m(b.end) > h * 60 for b in act) for h in range(8, 20)}
    booked, days = Counter(), max(len({b.date for b in act}), 1)
    for b in act: booked[b.resource_id] += (m(b.end) - m(b.start)) / 60
    cp = sum("CONFLICT_REJECTED" in l for l in AUDIT_F.read_text(encoding="utf-8").splitlines()) if AUDIT_F.exists() else 0
    return {"kpis": {"Total bookings": len(act), "Conflicts prevented": cp,
                     "Pending": sum(b.status == "Pending" for b in act), "Overdue approvals": sum("Overdue approval" in warnings(b) for b in act),
                     "Peak hour": max(hrs, key=hrs.get)},
            "hours": hrs, "occ": {r: round(booked[r] / (12 * days) * 100) for r in ROOMS}}


def report_csv(bs):
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=FIELDS); w.writeheader(); w.writerows(asdict(b) for b in bs); return buf.getvalue()


def report_md(bs):
    s = stats(bs)
    L = ["# Campus Booking Summary", f"_Generated {datetime.now():%Y-%m-%d %H:%M}_", "", "| Metric | Value |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in s["kpis"].items()] + ["", "## Room occupancy", "", "| Room | Occupancy |", "|---|---|"]
    L += [f"| {r} | {p}% |" for r, p in sorted(s["occ"].items(), key=lambda x: -x[1])] + ["", "## Bookings per hour", "", "| Hour | Bookings |", "|---|---|"]
    return "\n".join(L + [f"| {h} | {n} |" for h, n in s["hours"].items()]) + "\n"


# ---------- web server ----------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, body, ctype="application/json", code=200, name=None):
        data = (body if isinstance(body, str) else json.dumps(body)).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if name: self.send_header("Content-Disposition", f"attachment; filename={name}")
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        bs, p = load(), self.path.split("?")[0]
        if p in ("/", "/index.html"): self.send(PAGE, "text/html")
        elif p == "/api/state": self.send({"rooms": [asdict(r) for r in ROOMS.values()], "bookings": [{**asdict(b), "warnings": warnings(b)} for b in bs]})
        elif p == "/api/stats": self.send(stats(bs))
        elif p == "/export/csv": self.send(report_csv(bs), "text/csv", name="bookings_report.csv")
        elif p == "/export/md": self.send(report_md(bs), "text/markdown", name="summary.md")
        elif p == "/export/txt": self.send(AUDIT_F.read_text(encoding="utf-8") if AUDIT_F.exists() else "No audit entries yet.\n", "text/plain", name="audit_log.txt")
        else: self.send({"error": "not found"}, code=404)

    def do_POST(self):
        bs, p = load(), self.path
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8-sig")
        if p == "/api/book":
            n, err, conf, sug = create(json.loads(raw), bs)
            if n: self.send({"ok": asdict(n)}, code=201)
            elif err: self.send({"errors": err}, code=422)
            else: self.send({"conflicts": [asdict(c) for c in conf], "suggestions": sug}, code=409)
        elif p == "/api/approve":
            bid = json.loads(raw).get("id")
            for b in bs:
                if b.id == bid: b.status = "Confirmed"; save(bs); audit(f"STATUS_CHANGED {bid} -> Confirmed")
            self.send({"ok": True})
        elif p == "/api/import":
            log, ok = [], 0
            for n, row in enumerate(csv.DictReader(io.StringIO(raw)), 2):
                b, err, conf, _ = create({k.strip(): (v or "") for k, v in row.items() if k}, bs)
                if b: ok += 1; log.append({"row": n, "ok": True, "msg": "Imported as " + b.id})
                else: log.append({"row": n, "ok": False, "msg": "; ".join(f"{k}: {v}" for k, v in err.items()) if err else "Conflicts with " + conf[0].id})
            audit(f"IMPORT {ok} imported, {len(log) - ok} rejected")
            self.send({"imported": ok, "rejected": len(log) - ok, "log": log})
        elif p == "/api/reset":
            AUDIT_F.unlink(missing_ok=True); save(seed()); audit("RESET demo data restored"); self.send({"ok": True})
        else: self.send({"error": "not found"}, code=404)


# ---------- the dashboard page (HTML + CSS + JS) ----------
PAGE = r"""
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CampusOps - Resource Booking</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#F8FAFC;--card:#fff;--line:#E2E8F0;--ink:#0F172A;--mute:#64748B;--pri:#4F46E5;--ok:#10B981;--bad:#F43F5E;--warn:#F59E0B}
*{box-sizing:border-box}
body{margin:0;display:flex;min-height:100vh;background:var(--bg);color:var(--ink);font:14px/1.45 'Plus Jakarta Sans',system-ui,sans-serif}
.mono,.rl b,.blk span,.tile b,.heat b,.hb span{font-family:'JetBrains Mono',monospace}
h2,h3{margin:0 0 12px}h3{font-size:15px}
aside{width:212px;background:var(--ink);color:#CBD5E1;padding:22px 14px;display:flex;flex-direction:column;position:sticky;top:0;height:100vh}
aside h1{font-size:19px;color:#fff;margin:0 0 4px 10px;letter-spacing:-.3px}aside>small{margin:0 0 26px 10px;color:#64748B}
nav button{display:flex;gap:10px;width:100%;padding:10px 12px;margin-bottom:3px;border:0;border-radius:9px;background:none;color:#CBD5E1;font:inherit;cursor:pointer;text-align:left}
nav button:hover{background:#1E293B}nav button.on{background:var(--pri);color:#fff}
.live{margin-top:auto;padding:12px;border-radius:10px;background:#1E293B;font-size:12px}
.live i{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--ok);margin-right:6px;animation:blink 2s infinite}
@keyframes blink{50%{opacity:.3}}
main{flex:1;padding:22px 30px;min-width:0}
header{display:flex;gap:12px;align-items:center;margin-bottom:20px}header input{flex:1}header .dt{color:var(--mute);white-space:nowrap}
input,select{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:#fff;font:inherit;color:var(--ink)}
button{padding:9px 16px;border:1px solid var(--line);border-radius:9px;background:#fff;font:inherit;cursor:pointer}
button.primary{background:var(--pri);border-color:var(--pri);color:#fff;font-weight:600}
:focus-visible{outline:2px solid var(--pri);outline-offset:1px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:16px}
.grid{display:grid;gap:16px;margin-bottom:16px}.g2{grid-template-columns:2fr 1fr}.g3{grid-template-columns:repeat(3,1fr)}.g5{grid-template-columns:repeat(5,1fr)}
.grid .card{margin:0}
.bar{display:flex;gap:8px;align-items:center;margin-bottom:14px;flex-wrap:wrap}
.pill{border-radius:99px;padding:5px 14px;font-size:13px}.pill.on{background:var(--ink);color:#fff;border-color:var(--ink)}
/* hero */
.hero{border-radius:18px;padding:26px;margin-bottom:16px;color:#fff;background:radial-gradient(900px 300px at 85% -20%,rgba(79,70,229,.55),transparent),var(--ink)}
.hero small{color:#94A3B8}.hero h2{font-size:30px;margin:4px 0 4px;letter-spacing:-.6px}.hero p{margin:0 0 18px;color:#CBD5E1}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.tile{padding:11px 12px;border-radius:11px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.1)}
.tile b{font-size:13px}.tile span{display:block;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}.tile em{font-style:normal;font-size:11px;color:#94A3B8}
.tile.busy{background:var(--pri);border-color:transparent}.tile.busy em{color:#C7D2FE}.tile.free b::before{content:'';display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--ok);margin-right:6px}
/* kpi */
.kpi b{display:block;font-size:32px;letter-spacing:-1px;line-height:1.1}.kpi span{color:var(--mute);font-size:13px}.kpi i{display:block;height:3px;border-radius:3px;margin-bottom:12px;width:28px}
/* charts */
.cols{display:flex;align-items:flex-end;gap:12px;height:170px}.col{flex:1;text-align:center;font-size:12px;color:var(--mute)}
.col div{background:var(--pri);border-radius:7px 7px 0 0;height:0;transition:height 1s cubic-bezier(.2,.8,.2,1);margin-bottom:6px;position:relative}
.col div em{position:absolute;top:-18px;left:0;right:0;font-style:normal;color:var(--ink);font-weight:600}
.col.t div{background:var(--ok)}
.ring{position:relative;width:150px;height:150px;margin:0 auto}.ring svg{transform:rotate(-90deg)}
.ring circle{fill:none;stroke-width:10}.rt{stroke:var(--line)}.rf{stroke:var(--pri);stroke-linecap:round;transition:stroke-dashoffset 1.3s cubic-bezier(.2,.8,.2,1)}
.ring b{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:30px;letter-spacing:-1px}
.ring small{display:block;text-align:center;color:var(--mute);margin-top:8px}
.donut{width:150px;height:150px;border-radius:50%;margin:0 auto}.donut::after{content:'';display:block;width:90px;height:90px;border-radius:50%;background:#fff;position:relative;top:30px;left:30px}
.leg{display:flex;gap:14px;justify-content:center;margin-top:14px;font-size:12px;flex-wrap:wrap}.leg i{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:5px}
.hb{display:flex;align-items:center;gap:10px;margin:7px 0}.hb span{width:72px;font-size:12px}.hb div{height:11px;width:0;border-radius:6px;background:var(--pri);transition:width 1s cubic-bezier(.2,.8,.2,1)}.hb small{color:var(--mute)}
.heat{display:grid;grid-template-columns:70px repeat(12,1fr);gap:3px;font-size:11px}.heat small{text-align:center;color:var(--mute)}.heat b{font-size:11px;align-self:center}.heat i{font-style:normal;text-align:center;padding:9px 0;border-radius:5px;background:#EEF2FF}
/* lists */
.item{display:flex;gap:10px;align-items:center;padding:9px 0;border-bottom:1px solid var(--line)}.item:last-child{border:0}.item div{flex:1;min-width:0}.item small{color:var(--mute);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dot{width:9px;height:9px;border-radius:50%;flex:none}
.tag{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;margin-right:4px;background:#E2E8F0}
.tag.Confirmed{background:#D1FAE5}.tag.Pending,.tag.w{background:#FEF3C7}.tag.Conflict,.tag.x{background:#FFE4E6}
/* schedule */
.hours,.row{display:grid;grid-template-columns:140px 1fr}.hours div:last-child{display:flex}.hours span{flex:1;font:11px 'JetBrains Mono',monospace;color:var(--mute)}
.row{border-top:1px solid var(--line);min-height:56px}.rl{padding:8px 0}.rl small{display:block;color:var(--mute)}
.track{position:relative;background:repeating-linear-gradient(90deg,transparent 0 calc(8.333% - 1px),var(--line) calc(8.333% - 1px) 8.333%)}
.now{position:absolute;top:0;bottom:0;width:2px;background:var(--bad);z-index:4}
.blk{position:absolute;top:4px;bottom:4px;padding:4px 7px;border-radius:8px;overflow:hidden;font-size:11px;line-height:1.3;border-left:4px solid;transition:transform .15s,box-shadow .15s}
.blk:hover{transform:scale(1.04);z-index:5;box-shadow:0 8px 20px rgba(15,23,42,.2)}.blk i,.blk em{display:block;font-style:normal;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.blk.ok{background:#D1FAE5;border-color:var(--ok)}.blk.pend{background:#FEF3C7;border-color:var(--warn)}.blk.bad{background:#FFE4E6;border-color:var(--bad)}
.blk.hl{animation:pulse .7s 3;outline:2px solid var(--bad)}@keyframes pulse{50%{box-shadow:0 0 0 8px rgba(244,63,94,.3)}}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line)}th{color:var(--mute);font-weight:500}
.rooms{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px}.rooms .card{margin:0}.rooms .ring{width:100px;height:100px}.rooms .ring b{font-size:21px}
/* drawer */
#drawer{position:fixed;right:0;top:0;bottom:0;width:370px;padding:24px;background:#fff;border-left:1px solid var(--line);box-shadow:-12px 0 32px rgba(15,23,42,.1);overflow:auto;transition:transform .25s;z-index:20}
#drawer.hidden{transform:translateX(105%)}#drawer label{display:block;margin-bottom:10px;font-weight:500}#drawer label input,#drawer label select{margin-top:5px;font-weight:400}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}.err{display:block;min-height:16px;color:var(--bad);font-size:12px;font-weight:400}
.bad-field{border-color:var(--bad)!important;animation:shake .4s}@keyframes shake{25%{transform:translateX(-6px)}75%{transform:translateX(6px)}}
#conf{background:#FFF1F2;border:1px solid var(--bad);border-radius:9px;padding:10px;margin-bottom:12px;font-size:13px}#conf:empty{display:none}#conf button{margin:6px 6px 0 0;border-color:var(--ok)}
#toast{position:fixed;bottom:24px;left:50%;transform:translate(-50%,90px);background:var(--ink);color:#fff;padding:12px 20px;border-radius:11px;transition:transform .3s;z-index:30}#toast.show{transform:translate(-50%,0)}
.yes{color:var(--ok)}.no{color:var(--bad)}
@media(max-width:1000px){.g2,.g3,.g5{grid-template-columns:1fr 1fr}.tiles{grid-template-columns:repeat(2,1fr)}}
@media(max-width:760px){aside{display:none}main{padding:16px}.g2,.g3,.g5{grid-template-columns:1fr}.hours,.row{grid-template-columns:84px 1fr}#drawer{width:100%}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head>
<body>
<aside><h1>CampusOps</h1><small>Resource booking</small>
<nav>
<button data-v="overview" class="on">▦ Overview</button><button data-v="schedule">◷ Schedule</button><button data-v="rooms">◫ Rooms</button>
<button data-v="bookings">☰ Bookings</button><button data-v="analytics">◔ Analytics</button><button data-v="reports">⇩ Reports and import</button>
</nav>
<div class="live"><i></i>Live data<br><span id="clock" class="mono"></span><br><button id="reset" style="margin-top:10px;font-size:12px;padding:5px 10px">Reset demo data</button></div></aside>
<main>
<header><input id="q" placeholder="Search room, person or event"><span class="dt" id="dt"></span><button id="new" class="primary">New booking</button></header>
<section id="view"></section></main>

<form id="drawer" class="hidden" novalidate>
<h2>New booking</h2>
<label>Room<select name="resource_id"></select><span class="err"></span></label>
<label>Requester<input name="requester"><span class="err"></span></label>
<label>Role<select name="role"><option>Faculty</option><option>Student Club</option><option>Student Rep</option><option>Staff</option></select><span class="err"></span></label>
<label>Purpose<input name="purpose"><span class="err"></span></label>
<label>Date<input type="date" name="date"><span class="err"></span></label>
<div class="two"><label>Start<input type="time" name="start"><span class="err"></span></label><label>End<input type="time" name="end"><span class="err"></span></label></div>
<label>Expected capacity<input type="number" name="capacity" min="1"><span class="err"></span></label>
<div id="conf"></div>
<div class="two"><button type="button" id="cancel">Cancel</button><button class="primary">Book room</button></div>
</form>
<div id="toast"></div>

<script>
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const iso=d=>new Date(d.getTime()-d.getTimezoneOffset()*6e4).toISOString().slice(0,10);
const today=()=>iso(new Date());
const week=()=>Array.from({length:7},(_,i)=>{const d=new Date();d.setDate(d.getDate()+i);return iso(d)});
const wd=s=>new Date(s+'T00:00').toLocaleDateString('en-IN',{weekday:'short'});
const dm=s=>new Date(s+'T00:00').toLocaleDateString('en-IN',{day:'numeric',month:'short'});
const m=t=>+t.slice(0,2)*60+ +t.slice(3);
const nowMin=()=>{const d=new Date();return d.getHours()*60+d.getMinutes()};
const S={v:'overview',day:today(),type:'All',st:'All',q:'',B:[],R:[],A:[],K:{},hl:null};
const room=id=>S.R.find(r=>r.id===id);
const cls=s=>({Confirmed:'ok',Pending:'pend','Conflict Flagged':'bad'}[s]||'');
const act=()=>S.B.filter(b=>b.status!=='Cancelled');
const hrsOf=b=>(m(b.end)-m(b.start))/60;
const TYPES=['All','Lecture Hall','Computer Lab','Seminar Hall'],COL=['#4F46E5','#10B981','#F59E0B'];
const post=async(u,b)=>{const r=await fetch(u,{method:'POST',body:typeof b==='string'?b:JSON.stringify(b)});return{s:r.status,d:await r.json()}};
const toast=t=>{const e=$('#toast');e.textContent=t;e.classList.add('show');setTimeout(()=>e.classList.remove('show'),2800)};
async function load(){
  const [st,sx,au]=await Promise.all([fetch('/api/state').then(r=>r.json()),fetch('/api/stats').then(r=>r.json()),fetch('/export/txt').then(r=>r.text())]);
  S.R=st.rooms;S.B=st.bookings;S.K=sx.kpis;S.A=au.trim().split('\n').filter(l=>l.startsWith('['));
  const sel=$('[name=resource_id]');if(!sel.options.length)sel.innerHTML=S.R.map(r=>`<option value="${r.id}">${r.id} - ${r.name} (${r.capacity})</option>`).join('');
  render();
}
function match(b){const r=room(b.resource_id);if(S.type!=='All'&&r.type!==S.type)return false;if(S.st!=='All'&&b.status!==S.st)return false;
  return `${b.resource_id} ${b.requester} ${b.purpose} ${r.name}`.toLowerCase().includes(S.q.toLowerCase())}
const pills=(l,k)=>l.map(x=>`<button class="pill ${S[k]===x?'on':''}" data-k="${k}" data-x="${x}">${x}</button>`).join('');
const kpi=(l,v,c)=>`<div class="card kpi"><i style="background:${c}"></i><b ${typeof v==='number'?`data-n="${v}">0`:`>${v}`}</b><span>${l}</span></div>`;
const ring=(p,sub,c='var(--pri)')=>`<div class="ring"><svg viewBox="0 0 100 100"><circle class="rt" cx="50" cy="50" r="42"/><circle class="rf" style="stroke:${c}" cx="50" cy="50" r="42" stroke-dasharray="264" stroke-dashoffset="264" data-off="${264*(1-Math.min(p,100)/100)}"/></svg><b>${p}%</b></div><small style="display:block;text-align:center;color:var(--mute);margin-top:8px">${sub}</small>`;
const util=(list,days)=>Math.round(list.reduce((a,b)=>a+hrsOf(b),0)/(Math.max(list.length?1:1,1)*0+S.R.length*12*days)*100);
const weekBookings=()=>act().filter(b=>week().includes(b.date));

function overview(){
  const t=today(),nm=nowMin(),a=act(),wk=week();
  const tiles=S.R.map(r=>{const use=a.find(b=>b.resource_id===r.id&&b.date===t&&m(b.start)<=nm&&nm<m(b.end));
    const nx=a.filter(b=>b.resource_id===r.id&&b.date===t&&m(b.start)>nm).sort((x,y)=>m(x.start)-m(y.start))[0];
    return `<div class="tile ${use?'busy':'free'}"><b>${r.id}</b><span>${use?use.purpose:'Free'}</span><em>${use?'until '+use.end:nx?'next at '+nx.start:'free for the day'}</em></div>`}).join('');
  const inUse=S.R.filter(r=>a.some(b=>b.resource_id===r.id&&b.date===t&&m(b.start)<=nm&&nm<m(b.end))).length;
  const perDay=wk.map(d=>a.filter(b=>b.date===d).length),mx=Math.max(...perDay,1);
  const alerts=S.B.flatMap(b=>[...b.warnings.map(w=>({b,t:w,c:'w',d:'var(--warn)'})),...(b.status==='Conflict Flagged'?[{b,t:'Conflict flagged',c:'x',d:'var(--bad)'}]:[])]).slice(0,6);
  const feed=S.A.slice(-7).reverse().map(l=>{const x=l.match(/^\[(.+?)\] (\w+) ?(.*)$/)||[];const bad=/CONFLICT|VALIDATION/.test(x[2]);
    return `<div class="item"><span class="dot" style="background:${bad?'var(--bad)':'var(--ok)'}"></span><div><b class="mono" style="font-size:12px">${x[2]}</b><small>${x[3]||''}</small></div><small class="mono">${(x[1]||'').slice(11)}</small></div>`}).join('');
  const wkU=Math.round(weekBookings().reduce((s,b)=>s+hrsOf(b),0)/(S.R.length*12*7)*100);
  return `<div class="hero"><small>Right now</small><h2>${inUse} of ${S.R.length} rooms in use</h2><p>${S.R.length-inUse} available this minute. Bookings run 08:00 to 20:00.</p><div class="tiles">${tiles}</div></div>
  <div class="grid g5">${kpi('Bookings this week',a.length,'var(--pri)')}${kpi('Conflicts prevented',S.K['Conflicts prevented']||0,'var(--bad)')}${kpi('Pending approvals',S.K['Pending']||0,'var(--warn)')}${kpi('Overdue approvals',S.K['Overdue approvals']||0,'var(--bad)')}${kpi('Peak hour',S.K['Peak hour']||'-','var(--ok)')}</div>
  <div class="grid g2"><div class="card"><h3>Bookings over the next 7 days</h3><div class="cols">${perDay.map((n,i)=>`<div class="col ${i===0?'t':''}"><div data-h="${n/mx*100}%"><em>${n}</em></div>${wd(wk[i])}</div>`).join('')}</div></div>
  <div class="card"><h3>Weekly utilization</h3>${ring(wkU,'of bookable room hours')}</div></div>
  <div class="grid g2"><div class="card"><h3>Needs attention</h3>${alerts.map(x=>`<div class="item"><span class="dot" style="background:${x.d}"></span><div><b>${x.b.resource_id} ${x.b.purpose}</b><small>${x.b.requester}, ${dm(x.b.date)} ${x.b.start}</small></div><span class="tag ${x.c}">${x.t}</span></div>`).join('')||'<p>Nothing needs attention.</p>'}</div>
  <div class="card"><h3>Live activity</h3>${feed||'<p>No activity yet.</p>'}</div></div>`;
}
function schedule(){
  const wk=week(),hrs=Array.from({length:12},(_,i)=>`<span>${String(i+8).padStart(2,'0')}</span>`).join('');
  const nm=nowMin(),showNow=S.day===today()&&nm>=480&&nm<=1200;
  const rows=S.R.map(r=>{const bs=act().filter(b=>b.resource_id===r.id&&b.date===S.day&&match(b));
    return `<div class="row"><div class="rl"><b>${r.id}</b><small>${r.name}</small></div><div class="track">${showNow?`<div class="now" style="left:${(nm-480)/7.2}%"></div>`:''}${bs.map(b=>
    `<div class="blk ${cls(b.status)} ${S.hl===b.id?'hl':''}" title="${b.purpose} | ${b.requester} | ${b.status}" style="left:${(m(b.start)-480)/7.2}%;width:${(m(b.end)-m(b.start))/7.2}%"><span>${b.start}-${b.end}</span><i>${b.purpose}</i><em>${b.requester}, ${b.capacity}/${r.capacity}</em></div>`).join('')}</div></div>`}).join('');
  return `<div class="card"><div class="bar">${wk.map(d=>`<button class="pill ${S.day===d?'on':''}" data-day="${d}">${wd(d)} ${dm(d)}</button>`).join('')}<input type="date" id="day" value="${S.day}" style="width:auto"></div>
  <div class="bar">${pills(TYPES,'type')}</div><div class="hours"><div></div><div>${hrs}</div></div>${rows}</div>`;
}
function rooms(){
  const t=today(),nm=nowMin();
  return `<div class="rooms">${S.R.map(r=>{const bs=act().filter(b=>b.resource_id===r.id&&week().includes(b.date)),u=Math.round(bs.reduce((s,b)=>s+hrsOf(b),0)/(12*7)*100);
    const use=bs.find(b=>b.date===t&&m(b.start)<=nm&&nm<m(b.end)),nx=bs.filter(b=>b.date+b.start>t+hhmm(nm)).sort((x,y)=>(x.date+x.start).localeCompare(y.date+y.start))[0];
    return `<div class="card"><div class="bar"><b>${r.id}</b><span class="tag ${use?'Pending':'Confirmed'}">${use?'In use':'Free now'}</span></div><p style="margin:0 0 12px;color:var(--mute)">${r.name}<br>${r.type}, ${r.capacity} seats</p>${ring(u,'week utilization',COL[TYPES.indexOf(r.type)-1])}
    <p style="margin:14px 0 0;font-size:12px;color:var(--mute)">${nx?`Next: ${dm(nx.date)} ${nx.start}, ${nx.purpose}`:'No upcoming bookings'}</p></div>`}).join('')}</div>`;
}
const hhmm=n=>String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');
function bookings(){
  const list=S.B.filter(match).sort((a,b)=>(a.date+a.start).localeCompare(b.date+b.start));
  return `<div class="card"><div class="bar">${pills(TYPES,'type')}${pills(['All','Confirmed','Pending','Conflict Flagged'],'st')}</div>
  <table><tr><th>ID</th><th>Room</th><th>Event</th><th>When</th><th>People</th><th>Status</th><th></th></tr>${list.map(b=>`<tr><td class="mono">${b.id}</td><td class="mono">${b.resource_id}</td><td>${b.purpose}<br><small>${b.requester} (${b.role})</small></td>
  <td class="mono">${dm(b.date)}<br>${b.start}-${b.end}</td><td>${b.capacity}</td><td><span class="tag ${b.status.split(' ')[0]}">${b.status}</span>${b.warnings.map(w=>`<span class="tag w">${w}</span>`).join('')}</td>
  <td>${b.status==='Pending'?`<button data-ok="${b.id}">Approve</button>`:''}</td></tr>`).join('')||'<tr><td colspan=7>No bookings match. Clear the filters or search.</td></tr>'}</table><p style="color:var(--mute)">${list.length} booking(s)</p></div>`;
}
function heat(){
  const hrs=[...Array(12).keys()].map(i=>i+8),cnt=(r,h)=>act().filter(b=>b.resource_id===r.id&&m(b.start)<(h+1)*60&&m(b.end)>h*60).length;
  const mx=Math.max(1,...S.R.flatMap(r=>hrs.map(h=>cnt(r,h))));
  return `<div class="heat"><span></span>${hrs.map(h=>`<small>${h}</small>`).join('')}${S.R.map(r=>`<b>${r.id}</b>`+hrs.map(h=>{const n=cnt(r,h);return `<i style="background:rgba(79,70,229,${n?n/mx*.85+.1:0});${n&&n/mx>.5?'color:#fff':''}">${n||''}</i>`}).join('')).join('')}</div>`;
}
function analytics(){
  const a=act(),hrs=[...Array(12).keys()].map(i=>i+8),byH=hrs.map(h=>a.filter(b=>m(b.start)<(h+1)*60&&m(b.end)>h*60).length),mh=Math.max(...byH,1);
  const byT=TYPES.slice(1).map(t=>a.filter(b=>room(b.resource_id).type===t).length),tot=byT.reduce((x,y)=>x+y,0)||1;let c=0;
  const grad=byT.map((n,i)=>{const s=c;c+=n/tot*100;return `${COL[i]} ${s}% ${c}%`}).join(',');
  const occ=S.R.map(r=>[r.id,Math.round(a.filter(b=>b.resource_id===r.id).reduce((s,b)=>s+hrsOf(b),0)/(12*7)*100)]);
  const sc=['Confirmed','Pending','Conflict Flagged'].map(s=>[s,a.filter(b=>b.status===s).length]);
  return `<div class="card"><h3>Room usage heatmap (bookings per hour of day)</h3>${heat()}</div>
  <div class="grid g3"><div class="card"><h3>Bookings by room type</h3><div class="donut" style="background:conic-gradient(${grad})"></div><div class="leg">${TYPES.slice(1).map((t,i)=>`<span><i style="background:${COL[i]}"></i>${t} ${byT[i]}</span>`).join('')}</div></div>
  <div class="card"><h3>Peak hours</h3>${hrs.map((h,i)=>`<div class="hb"><span>${hhmm(h*60)}</span><div data-w="${byH[i]/mh*100}%"></div><small>${byH[i]}</small></div>`).join('')}</div>
  <div class="card"><h3>Room occupancy</h3>${occ.map(([r,p])=>`<div class="hb"><span>${r}</span><div data-w="${Math.min(p,100)}%"></div><small>${p}%</small></div>`).join('')}<h3 style="margin-top:18px">Status mix</h3>${sc.map(([s,n])=>`<div class="hb"><span style="width:110px;font-family:inherit">${s}</span><div data-w="${n/Math.max(a.length,1)*100}%"></div><small>${n}</small></div>`).join('')}</div></div>`;
}
const reports=()=>`<div class="grid g2"><div class="card"><h3>Download reports</h3><p style="color:var(--mute)">Generated from the live data in bookings.json.</p>
  <div class="bar"><a href="/export/csv"><button class="primary">CSV report</button></a><a href="/export/md"><button>Markdown summary</button></a><a href="/export/txt"><button>Audit log</button></a></div></div>
  <div class="card"><h3>Bulk CSV import</h3><p style="color:var(--mute)">Columns: <code>resource_id,requester,role,purpose,date,start,end,capacity</code>. Each row is validated and conflict-checked.</p>
  <input type="file" id="file" accept=".csv" style="width:auto"> <button class="primary" id="up">Import file</button><div id="log" style="margin-top:12px"></div></div></div>`;

function animate(){
  $$('[data-n]').forEach(el=>{const n=+el.dataset.n;let t0;const f=t=>{t0??=t;const p=Math.min((t-t0)/900,1);el.textContent=Math.round(n*(1-Math.pow(1-p,3)));if(p<1)requestAnimationFrame(f)};requestAnimationFrame(f)});
  setTimeout(()=>{$$('[data-h]').forEach(e=>e.style.height=e.dataset.h);$$('[data-w]').forEach(e=>e.style.width=e.dataset.w);$$('[data-off]').forEach(e=>e.style.strokeDashoffset=e.dataset.off)},60);
}
function render(){
  $$('nav button').forEach(b=>b.classList.toggle('on',b.dataset.v===S.v));
  $('#view').innerHTML={overview,schedule,rooms,bookings,analytics,reports}[S.v]();animate();
}
document.addEventListener('click',async e=>{
  const t=e.target;
  if(t.dataset.v){S.v=t.dataset.v;await load()}
  if(t.dataset.k){S[t.dataset.k]=t.dataset.x;render()}
  if(t.dataset.day){S.day=t.dataset.day;S.hl=null;render()}
  if(t.dataset.ok){await post('/api/approve',{id:t.dataset.ok});toast('Booking approved');load()}
  if(t.id==='up'){const f=$('#file').files[0];if(!f)return toast('Choose a CSV file first');
    const r=(await post('/api/import',await f.text())).d;
    $('#log').innerHTML=`<p><b>${r.imported} imported, ${r.rejected} rejected</b></p>`+r.log.map(l=>`<div class="${l.ok?'yes':'no'}">${l.ok?'OK':'X'} Row ${l.row}: ${l.msg}</div>`).join('');load().then(()=>{})}
  if(t.id==='reset'){await post('/api/reset',{});toast('Demo data restored');load()}
});
document.addEventListener('change',e=>{if(e.target.id==='day'){S.day=e.target.value;S.hl=null;render()}});
$('#q').oninput=()=>{clearTimeout(S.t);S.t=setTimeout(()=>{S.q=$('#q').value;if(['overview','analytics','reports','rooms'].includes(S.v))S.v='bookings';render()},200)};
const form=$('#drawer');
const clearErr=()=>{$$('#drawer .err').forEach(x=>x.textContent='');$$('#drawer .bad-field').forEach(x=>x.classList.remove('bad-field'));$('#conf').innerHTML=''};
function showErr(errs){for(const[k,msg]of Object.entries(errs)){const el=form.elements[k];if(!el)continue;void el.offsetWidth;el.classList.add('bad-field');el.parentElement.querySelector('.err').textContent=msg}}
$('#new').onclick=()=>{clearErr();form.reset();form.elements.date.value=S.day;form.classList.remove('hidden')};
$('#cancel').onclick=()=>form.classList.add('hidden');
document.addEventListener('keydown',e=>{if(e.key==='Escape')form.classList.add('hidden')});
form.onsubmit=async e=>{
  e.preventDefault();clearErr();
  const p=Object.fromEntries(new FormData(form)),r=await post('/api/book',p);
  if(r.s===201){form.classList.add('hidden');S.v='schedule';S.day=p.date;S.hl=r.d.ok.id;toast('Booking saved to bookings.json and bookings.csv');return load()}
  if(r.s===422)return showErr(r.d.errors);
  if(r.s===409){
    const c=r.d.conflicts[0];S.v='schedule';S.day=p.date;S.hl=c.id;await load();
    $('#conf').innerHTML=`<b>Conflict:</b> ${c.resource_id} is booked ${c.start}-${c.end} for "${c.purpose}" (${c.requester}).<br>`+(r.d.suggestions.length?'Next free slots:<br>'+r.d.suggestions.map(s=>`<button type="button" data-s="${s.start}" data-e="${s.end}">${s.start}-${s.end}</button>`).join(''):'No free slot of that length on this day.');
    $$('#conf button').forEach(b=>b.onclick=()=>{form.elements.start.value=b.dataset.s;form.elements.end.value=b.dataset.e;$('#conf').innerHTML=''});
    ['start','end'].forEach(k=>{void form.elements[k].offsetWidth;form.elements[k].classList.add('bad-field')});
  }
};
const tick=()=>{const d=new Date();$('#clock').textContent=d.toLocaleTimeString('en-IN');$('#dt').textContent=d.toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long'})};
tick();setInterval(tick,1000);setInterval(()=>{if(S.v==='overview'&&form.classList.contains('hidden'))load()},60000);
load();
</script></body></html>
"""


if __name__ == "__main__":
    load()   # creates data files on first run (or heals them)
    print("CampusOps running at http://127.0.0.1:8000   (press Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()