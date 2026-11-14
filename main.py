"""Run the whole engine from commands.txt.

    python main.py                 (uses the files next to main.py)
    python main.py <folder>        (folder with commands.txt and the CSVs)

Commands (separated by |):
    LOAD_VOUCHER_TYPES|voucher_types.csv    -> voucher_manager.py
    ISSUE_VOUCHERS|vouchers.csv             -> voucher_manager.py
    PROCESS_EVENTS|events.csv               -> session_engine.py
    REPORT|YYYY-MM-DD                       -> voucher_manager.py (rows from the day snapshot)
"""
import csv
import os
import sys

from voucher_manager import VoucherManager
from session_engine import SessionEngine, load_events

SESSION_FIELDS = ["timestamp", "voucher_code", "device_mac", "action",
                  "charged", "remaining", "reason"]
REPORT_FIELDS = ["report_date", "voucher_code", "type_id", "kind", "activated_at",
                 "consumed", "remaining", "devices_used", "revenue_rs", "status"]
UNUSED_FIELDS = ["voucher_code", "type_id", "issued_at"]
ERROR_FIELDS = ["event_id", "reason"]


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(fieldnames)
        for row in rows:
            writer.writerow(row[k] for k in fieldnames) if isinstance(row, dict) else writer.writerow(row)


def read_commands(path):
    commands = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if line and not line.startswith("#"):
                commands.append([part.strip() for part in line.split("|")])
    return commands


def run(folder, out_folder=None):
    out_folder = out_folder or folder
    manager = VoucherManager()
    manager.verbose = False
    engine = SessionEngine(manager)
    requested_dates = []
    types_loaded = vouchers_loaded = events_loaded = False

    for command in read_commands(os.path.join(folder, "commands.txt")):
        name, args = command[0].upper(), command[1:]
        if name == "LOAD_VOUCHER_TYPES" and len(args) == 1:
            manager.load_types(os.path.join(folder, args[0]))
            types_loaded = True
        elif name == "ISSUE_VOUCHERS" and len(args) == 1:
            if not types_loaded:
                raise ValueError("LOAD_VOUCHER_TYPES must come before ISSUE_VOUCHERS.")
            manager.load_vouchers(os.path.join(folder, args[0]))
            vouchers_loaded = True
        elif name == "PROCESS_EVENTS" and len(args) == 1:
            if not vouchers_loaded:
                raise ValueError("ISSUE_VOUCHERS must come before PROCESS_EVENTS.")
            engine.process(load_events(os.path.join(folder, args[0])))
            events_loaded = True
        elif name == "REPORT" and len(args) == 1:
            requested_dates.append(args[0])
        else:
            raise ValueError(f"Invalid or unsupported command: {command}")

    if not (types_loaded and vouchers_loaded and events_loaded):
        raise ValueError("commands.txt must load types, vouchers and events.")

    report_rows = []
    for date_str in requested_dates:
        report_rows.extend(engine.snapshots.get(date_str, []))
    report_rows.sort(key=lambda r: (r[0], r[1]))        # by date, then voucher_code

    os.makedirs(out_folder, exist_ok=True)
    write_csv(os.path.join(out_folder, "session_log.csv"), SESSION_FIELDS, engine.session_log)
    write_csv(os.path.join(out_folder, "voucher_report.csv"), REPORT_FIELDS, report_rows)
    write_csv(os.path.join(out_folder, "unused_vouchers.csv"), UNUSED_FIELDS, manager.unused_rows())
    write_csv(os.path.join(out_folder, "errors.csv"), ERROR_FIELDS, engine.errors)

    print("Voucher types:", len(manager.voucher_types))
    print("Vouchers:", len(manager.vouchers))
    print("Events:", engine.events_processed)
    print("Session log records:", len(engine.session_log))
    print("Error records:", len(engine.errors))
    print("Unused vouchers:", len(manager.unused_rows()))
    print("Voucher report records:", len(report_rows))
    print("Output files saved in:", out_folder)
    return manager, engine


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    run(folder)
