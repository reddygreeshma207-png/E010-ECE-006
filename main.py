"""Runs commands.txt.   python main.py
Voucher commands are handled here (voucher_manager.py).
PROCESS_EVENTS is handled by the session engine (teammate's part)."""
import os
from voucher_manager import VoucherManager

folder = os.path.dirname(os.path.abspath(__file__))


def main():
    manager = VoucherManager()
    report_rows = []
    now = None                      # last event time, set by the session engine

    with open(os.path.join(folder, "commands.txt"), encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, *args = line.split("|")

            if name == "LOAD_VOUCHER_TYPES":
                manager.load_types(os.path.join(folder, args[0]))
            elif name == "ISSUE_VOUCHERS":
                manager.load_vouchers(os.path.join(folder, args[0]))
            elif name == "PROCESS_EVENTS":
                try:
                    from session_engine import process_events   # teammate: see note
                except ImportError:
                    print("PROCESS_EVENTS skipped: session_engine.process_events not connected yet")
                    continue
                now = process_events(manager, os.path.join(folder, args[0]))
            elif name == "REPORT":
                report_rows += manager.report_rows(args[0].strip(), now)

    manager.write_voucher_report(os.path.join(folder, "voucher_report.csv"), report_rows)
    manager.write_unused_vouchers(os.path.join(folder, "unused_vouchers.csv"))
    print("Vouchers:", len(manager.vouchers), "| report rows:", len(report_rows),
          "| unused:", len(manager.unused_rows()))


if __name__ == "__main__":
    main()
