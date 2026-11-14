import csv
from datetime import datetime

TS_FMT = "%Y-%m-%d %H:%M:%S"
REPORT_HEADER = ["report_date", "voucher_code", "type_id", "kind", "activated_at",
                 "consumed", "remaining", "devices_used", "revenue_rs", "status"]
UNUSED_HEADER = ["voucher_code", "type_id", "issued_at"]


def parse_ts(s):
    return datetime.strptime(s.strip(), TS_FMT)


def fmt_ts(t):
    return t.strftime(TS_FMT)


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)

from models import VoucherType, Voucher


class VoucherManager:

    def __init__(self):
        self.voucher_types = {}
        self.vouchers = {}
        self.counters = {}
        self.types_by_id = {}          # NEW: "VT-01" -> VoucherType

    def register_type(self, prefix, voucher_type,
                      quantity, price, max_devices, type_id=None):

        prefix = prefix.upper()

        # type checks first, so bad input gives a friendly error, not a crash
        if isinstance(quantity, bool) or isinstance(price, bool) \
                or isinstance(max_devices, bool):
            print("Error: Invalid numeric values!")
            return False

        if not isinstance(max_devices, int):
            print("Error: Device limit must be an integer!")
            return False

        if not isinstance(quantity, (int, float)):
            print("Error: Invalid quantity!")
            return False

        if not isinstance(price, (int, float)):
            print("Error: Invalid price!")
            return False

        voucher_type = voucher_type.upper()

        if not prefix.isalnum():
            print("Error: Prefix must be alphanumeric!")
            return False

        if voucher_type not in ["TIME", "DATA"]:
            print("Error: Invalid voucher type!")
            return False

        if prefix in self.voucher_types:
            print("Error: Prefix already registered!")
            return False

        if quantity <= 0 or price < 0 or max_devices <= 0:
            print("Error: Invalid voucher values!")
            return False

        if isinstance(quantity, float) and quantity.is_integer():
            quantity = int(quantity)

        new_type = VoucherType(
            prefix, voucher_type, quantity,
            price, max_devices, type_id
        )

        self.voucher_types[prefix] = new_type
        self.counters[prefix] = 0
        if type_id:
            self.types_by_id[type_id] = new_type

        print("Voucher type registered successfully!")
        return True

    def issue_voucher(self, prefix):

        prefix = prefix.upper()

        if prefix not in self.voucher_types:
            print("Error: Voucher type not found!")
            return None

        self.counters[prefix] += 1

        code = prefix + str(self.counters[prefix]).zfill(3)

        voucher = Voucher(
            code,
            self.voucher_types[prefix]
        )

        self.vouchers[code] = voucher

        print("Voucher issued successfully:", code)

        return voucher

    def view_vouchers(self):

        if not self.vouchers:
            print("No vouchers issued.")
            return

        for code, voucher in self.vouchers.items():

            print("\nVoucher Code:", code)
            print("Type:", voucher.voucher_type.voucher_type)
            print("Balance:", voucher.remaining_balance)
            print("Price:", voucher.voucher_type.price)
            print("Device Limit:",
                  voucher.voucher_type.max_devices)

    # =====================================================================
    # NEW: everything below is what the command file (commands.txt) needs
    # =====================================================================

    # ---- LOAD_VOUCHER_TYPES ----
    def load_types(self, path):
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                self.register_type(
                    row["code_prefix"], row["kind"],
                    int(row["quantity"]), float(row["price_rs"]),
                    int(row["max_devices"]), row["type_id"])

    # ---- ISSUE_VOUCHERS ----
    def load_vouchers(self, path):
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                code = row["voucher_code"].strip()
                vtype = self.types_by_id.get(row["type_id"].strip())
                if vtype is None or code in self.vouchers:
                    continue                      # unknown type / duplicate code
                self.vouchers[code] = Voucher(
                    code, vtype, parse_ts(row["issued_at"]))

    # ---- helpers the session engine calls ----
    def get(self, code):
        return self.vouchers.get(code)            # None -> UNKNOWN_VOUCHER

    def activate(self, code, ts):
        """First successful LOGIN starts the 24 h window (BR-01)."""
        return self.vouchers[code].activate(ts)

    def is_expired(self, code, ts):
        """True from activation + 24 h onwards; window is [start, start+24h)."""
        return not self.vouchers[code].is_valid(ts)

    # ---- reports ----
    def status(self, voucher, now):
        if voucher.is_exhausted():
            return "EXHAUSTED"
        if now is not None and not voucher.is_valid(now):
            return "EXPIRED"
        return "ACTIVE"

    def report_rows(self, date_str, now=None):
        """Vouchers activated on date_str, ordered by voucher_code (BR-07)."""
        rows = []
        for code in sorted(self.vouchers):
            v = self.vouchers[code]
            if v.activated and v.activation_time.strftime("%Y-%m-%d") == date_str:
                kind = v.voucher_type.voucher_type
                fmt = str if kind == "TIME" else (lambda n: f"{n:.1f}")
                rows.append([
                    date_str, code, v.voucher_type.type_id, kind,
                    fmt_ts(v.activation_time),
                    fmt(v.consumed()), fmt(v.remaining_balance),
                    len(v.devices_used),
                    f"{v.voucher_type.price:.2f}",
                    self.status(v, now)])
        return rows

    def unused_rows(self):
        return [[code, v.voucher_type.type_id, fmt_ts(v.issued_at)]
                for code, v in sorted(self.vouchers.items())
                if not v.activated]

    def write_voucher_report(self, path, rows):
        _write_csv(path, REPORT_HEADER, rows)

    def write_unused_vouchers(self, path):
        _write_csv(path, UNUSED_HEADER, self.unused_rows())
