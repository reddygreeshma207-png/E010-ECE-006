import csv
import os
import math
from datetime import datetime, timedelta

# ------------------------------------------------------------
# 1. PROJECT FOLDER
# ------------------------------------------------------------
# By default, this is the sample-data folder on your computer.
# You can change this path if your folder is in a different place.
folder = os.environ.get(
    "WIFI_PROJECT_FOLDER",
    r"C:\Users\Alex\Downloads\WiFi\E010-ECE-006-sample-data"
)


def load_csv(filename):
    path = os.path.join(folder, filename)
    with open(path, "r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(filename, rows, fieldnames):
    path = os.path.join(folder, filename)
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_timestamp(value):
    return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")


def format_timestamp(value):
    return value.strftime("%Y-%m-%d %H:%M:%S")


def event_id_key(value):
    # EVT-0009 sorts before EVT-0010; numeric IDs also sort numerically.
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if digits:
        return (0, int(digits), str(value))
    return (1, 0, str(value))


# ------------------------------------------------------------
# 2. LOAD INPUTS AND REGISTER VOUCHERS
# ------------------------------------------------------------
# Read and follow commands.txt in its listed order.
commands = []
with open(os.path.join(folder, "commands.txt"), "r", encoding="utf-8-sig") as command_file:
    for raw_line in command_file:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        commands.append([part.strip() for part in line.split("|")])

voucher_types = []
vouchers = []
events = []
requested_report_dates = []

for command in commands:
    name = command[0].upper()
    args = command[1:]

    if name == "LOAD_VOUCHER_TYPES" and len(args) == 1:
        voucher_types = load_csv(args[0])
    elif name == "ISSUE_VOUCHERS" and len(args) == 1:
        if not voucher_types:
            raise ValueError("LOAD_VOUCHER_TYPES must come before ISSUE_VOUCHERS.")
        vouchers = load_csv(args[0])
    elif name == "PROCESS_EVENTS" and len(args) == 1:
        if not vouchers:
            raise ValueError("ISSUE_VOUCHERS must come before PROCESS_EVENTS.")
        events = load_csv(args[0])
    elif name == "REPORT" and len(args) == 1:
        requested_report_dates.append(args[0])
    else:
        raise ValueError(f"Invalid or unsupported command: {command}")

if not voucher_types or not vouchers or not events:
    raise ValueError("commands.txt must load voucher types, vouchers, and events before reports.")

voucher_type_dict = {row["type_id"]: row for row in voucher_types}
voucher_dict = {}

for row in vouchers:
    type_id = row["type_id"]
    if type_id not in voucher_type_dict:
        continue

    info = voucher_type_dict[type_id]
    quantity = float(info["quantity"])
    voucher_dict[row["voucher_code"]] = {
        "type_id": type_id,
        "issued_at": row.get("issued_at", ""),
        "kind": info["kind"].strip().upper(),
        "activated_at": None,
        "consumed": 0.0,
        "remaining": quantity,
        "status": "ACTIVE",
        "devices": set(),
    }

priority = {"LOGIN": 1, "USAGE": 2, "LOGOUT": 3}
sorted_events = sorted(
    events,
    key=lambda row: (
        parse_timestamp(row["timestamp"]),
        priority.get(row["event_type"].strip().upper(), 99),
        event_id_key(row.get("event_id", "")),
    ),
)

# ------------------------------------------------------------
# 3. SIMULATION STATE
# ------------------------------------------------------------
active_sessions = {}  # key: (voucher_code, device_mac)
session_log = []
errors = []
simulation_time = None


def add_log(when, code, mac, action, charged, remaining, reason="NONE"):
    session_log.append({
        "timestamp": format_timestamp(when),
        "voucher_code": code,
        "device_mac": mac,
        "action": action,
        "charged": round(float(charged), 6),
        "remaining": round(float(remaining), 6),
        "reason": reason,
    })


def sessions_for_voucher(code):
    return [key for key in active_sessions if key[0] == code]


def reject_event(event, reason):
    errors.append({"event_id": event.get("event_id", ""), "reason": reason})
    code = event.get("voucher_code", "")
    mac = event.get("device_mac", "")
    voucher = voucher_dict.get(code)
    remaining = voucher["remaining"] if voucher else 0.0
    add_log(parse_timestamp(event["timestamp"]), code, mac,
            "REJECTED", 0, remaining, reason)


def finish_session(key, when, action):
    session = active_sessions.get(key)
    if session is None:
        return

    code, mac = key
    voucher = voucher_dict[code]

    # TIME vouchers charge connected minutes. DATA vouchers charge MB on
    # accepted USAGE events, so a session-closing row charges zero MB.
    if voucher["kind"] == "TIME":
        charged = math.ceil(max(0.0, session["connected_minutes"]) - 1e-10)
    else:
        charged = 0.0

    add_log(when, code, mac, action, charged, voucher["remaining"])
    del active_sessions[key]


# ------------------------------------------------------------
# 4. ADVANCE GLOBAL CLOCK
#    Every active device on a TIME voucher consumes one minute per
#    real minute. Idle logout and TIME exhaustion happen at exact times.
# ------------------------------------------------------------
def advance_to(target_time):
    global simulation_time

    if simulation_time is None:
        simulation_time = target_time
        return

    if target_time < simulation_time:
        raise ValueError("Events are not in chronological order.")

    while simulation_time < target_time:
        if not active_sessions:
            simulation_time = target_time
            return

        next_time = target_time

        # Find earliest idle deadline.
        for session in active_sessions.values():
            deadline = session["last_activity"] + timedelta(minutes=10)
            if simulation_time < deadline <= next_time:
                next_time = deadline

        # Find earliest shared TIME-voucher exhaustion.
        for code, voucher in voucher_dict.items():
            if voucher["kind"] != "TIME" or voucher["remaining"] <= 1e-10:
                continue
            device_count = len(sessions_for_voucher(code))
            if device_count:
                minutes_left = voucher["remaining"] / device_count
                exhaustion_time = simulation_time + timedelta(minutes=minutes_left)
                if simulation_time < exhaustion_time <= next_time:
                    next_time = exhaustion_time

        elapsed = (next_time - simulation_time).total_seconds() / 60.0

        # Deduct shared TIME balance based on the number of active devices.
        if elapsed > 0:
            for code, voucher in voucher_dict.items():
                if voucher["kind"] != "TIME" or voucher["remaining"] <= 1e-10:
                    continue
                device_count = len(sessions_for_voucher(code))
                if device_count:
                    amount = min(elapsed * device_count, voucher["remaining"])
                    voucher["consumed"] += amount
                    voucher["remaining"] = max(0.0, voucher["remaining"] - amount)

            # Track connected duration for every session, including DATA.
            for session in active_sessions.values():
                session["connected_minutes"] += elapsed

        simulation_time = next_time

        # Close sessions whose idle deadline has arrived.
        for key, session in list(active_sessions.items()):
            deadline = session["last_activity"] + timedelta(minutes=10)
            if deadline <= simulation_time:
                finish_session(key, deadline, "IDLE_LOGOUT")

        # Close every remaining device on an exhausted TIME voucher.
        for code, voucher in voucher_dict.items():
            if voucher["kind"] == "TIME" and voucher["remaining"] <= 1e-8:
                voucher["remaining"] = 0.0
                voucher["status"] = "EXHAUSTED"
                for key in list(sessions_for_voucher(code)):
                    finish_session(key, simulation_time, "CUT_OFF")


def process_login(event):
    code = event["voucher_code"]
    mac = event["device_mac"]
    when = parse_timestamp(event["timestamp"])
    key = (code, mac)

    voucher = voucher_dict.get(code)
    if voucher is None:
        reject_event(event, "UNKNOWN_VOUCHER")
        return

    # Duplicate login for an already-active device is ignored.
    if key in active_sessions:
        return

    # The voucher is valid for the half-open interval [activation, activation+24h).
    if voucher["activated_at"] is not None:
        activation = parse_timestamp(voucher["activated_at"])
        if when >= activation + timedelta(hours=24):
            if voucher["status"] == "ACTIVE":
                voucher["status"] = "EXPIRED"
            reject_event(event, "EXPIRED")
            return

    type_info = voucher_type_dict[voucher["type_id"]]
    if len(sessions_for_voucher(code)) >= int(type_info["max_devices"]):
        reject_event(event, "DEVICE_LIMIT")
        return

    if voucher["remaining"] <= 1e-10:
        voucher["remaining"] = 0.0
        voucher["status"] = "EXHAUSTED"
        reject_event(event, "BALANCE_EXHAUSTED")
        return

    if voucher["activated_at"] is None:
        voucher["activated_at"] = event["timestamp"]

    active_sessions[key] = {
        "login_time": when,
        "last_activity": when,
        "connected_minutes": 0.0,
    }
    voucher["devices"].add(mac)
    add_log(when, code, mac, "LOGIN", 0, voucher["remaining"])


def process_usage(event):
    code = event["voucher_code"]
    mac = event["device_mac"]
    when = parse_timestamp(event["timestamp"])
    key = (code, mac)

    voucher = voucher_dict.get(code)
    if voucher is None:
        reject_event(event, "UNKNOWN_VOUCHER")
        return

    if key not in active_sessions:
        reason = "BALANCE_EXHAUSTED" if voucher["remaining"] <= 1e-10 else "NOT_LOGGED_IN"
        reject_event(event, reason)
        return

    charged = 0.0
    if voucher["kind"] == "DATA":
        mb_used = float(event.get("mb", 0) or 0)
        if mb_used < 0:
            reject_event(event, "INVALID_USAGE")
            return
        charged = min(mb_used, voucher["remaining"])
        voucher["consumed"] += charged
        voucher["remaining"] = max(0.0, voucher["remaining"] - charged)

    active_sessions[key]["last_activity"] = when
    add_log(when, code, mac, "USAGE", charged, voucher["remaining"])

    if voucher["kind"] == "DATA" and voucher["remaining"] <= 1e-8:
        voucher["remaining"] = 0.0
        voucher["status"] = "EXHAUSTED"
        for active_key in list(sessions_for_voucher(code)):
            finish_session(active_key, when, "CUT_OFF")


def process_logout(event):
    code = event["voucher_code"]
    mac = event["device_mac"]
    when = parse_timestamp(event["timestamp"])
    key = (code, mac)

    if code not in voucher_dict:
        reject_event(event, "UNKNOWN_VOUCHER")
        return
    if key not in active_sessions:
        reject_event(event, "NOT_LOGGED_IN")
        return

    finish_session(key, when, "LOGOUT")


# ------------------------------------------------------------
# 5. PROCESS EVENTS BY DAY AND TAKE DAILY REPORT SNAPSHOTS
# ------------------------------------------------------------
def snapshot_for_day(report_date):
    rows = []
    for code, voucher in voucher_dict.items():
        if not voucher["activated_at"] or voucher["activated_at"][:10] != report_date:
            continue

        info = voucher_type_dict[voucher["type_id"]]
        price = float(info.get("price_rs", 0) or 0)
        status = voucher["status"]
        activation = parse_timestamp(voucher["activated_at"])
        end_of_day = datetime.strptime(report_date, "%Y-%m-%d") + timedelta(days=1)
        if status == "ACTIVE" and end_of_day >= activation + timedelta(hours=24):
            status = "EXPIRED"

        rows.append({
            "report_date": report_date,
            "voucher_code": code,
            "type_id": voucher["type_id"],
            "kind": voucher["kind"],
            "activated_at": voucher["activated_at"],
            "consumed": round(voucher["consumed"], 6),
            "remaining": round(voucher["remaining"], 6),
            "devices_used": len(voucher["devices"]),
            "revenue_rs": price,
            "status": status,
        })
    return rows


report_snapshots = {}
index = 0
while index < len(sorted_events):
    day = parse_timestamp(sorted_events[index]["timestamp"]).date()
    next_index = index
    while next_index < len(sorted_events) and parse_timestamp(sorted_events[next_index]["timestamp"]).date() == day:
        event = sorted_events[next_index]
        when = parse_timestamp(event["timestamp"])
        advance_to(when)

        event_type = event["event_type"].strip().upper()
        if event_type == "LOGIN":
            process_login(event)
        elif event_type == "USAGE":
            process_usage(event)
        elif event_type == "LOGOUT":
            process_logout(event)
        else:
            reject_event(event, "UNKNOWN_EVENT_TYPE")
        next_index += 1

    # Advance to midnight so idle timeouts and TIME exhaustion before the
    # next report date are included in this day's snapshot.
    midnight = datetime.combine(day + timedelta(days=1), datetime.min.time())
    advance_to(midnight)
    report_date = day.strftime("%Y-%m-%d")
    report_snapshots[report_date] = snapshot_for_day(report_date)
    index = next_index

# Execute REPORT requests in the same order as commands.txt and sort each
# report by voucher_code as required by the sample-data specification.
report_rows = []
for report_date in requested_report_dates:
    report_rows.extend(report_snapshots.get(report_date, []))
report_rows.sort(key=lambda row: (row["report_date"], row["voucher_code"]))

# ------------------------------------------------------------
# 6. WRITE OUTPUT FILES
# ------------------------------------------------------------
write_csv(
    "session_log.csv",
    session_log,
    ["timestamp", "voucher_code", "device_mac", "action", "charged", "remaining", "reason"],
)
write_csv("errors.csv", errors, ["event_id", "reason"])

unused_rows = []
for code, voucher in voucher_dict.items():
    if voucher["activated_at"] is None:
        unused_rows.append({
            "voucher_code": code,
            "type_id": voucher["type_id"],
            "issued_at": voucher["issued_at"],
        })
write_csv("unused_vouchers.csv", unused_rows, ["voucher_code", "type_id", "issued_at"])

write_csv(
    "voucher_report.csv",
    report_rows,
    ["report_date", "voucher_code", "type_id", "kind", "activated_at",
     "consumed", "remaining", "devices_used", "revenue_rs", "status"],
)

# ------------------------------------------------------------
# 7. SUMMARY
# ------------------------------------------------------------
print("CSV FILES LOADED SUCCESSFULLY")
print("Voucher types:", len(voucher_types))
print("Vouchers:", len(vouchers))
print("Events:", len(events))
print("\nEVENT PROCESSING COMPLETED")
print("Session log records:", len(session_log))
print("Error records:", len(errors))
print("Unused vouchers:", len(unused_rows))
print("Voucher report records:", len(report_rows))
print("\nOutput files saved in:", folder)
print(" - session_log.csv")
print(" - voucher_report.csv")
print(" - unused_vouchers.csv")
print(" - errors.csv")
