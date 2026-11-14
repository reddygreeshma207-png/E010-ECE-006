from datetime import datetime, timedelta
import math

EPS = 1e-8   # balances below this are treated as zero (float safety)


class VoucherType:

    def __init__(self, prefix, voucher_type, quantity,
                 price, max_devices, type_id=None):

        self.prefix = prefix
        self.voucher_type = voucher_type.upper()
        self.quantity = quantity
        self.price = price
        self.max_devices = max_devices
        self.type_id = type_id          # NEW: "VT-01" ... needed for the report


class Voucher:

    def __init__(self, code, voucher_type, issued_at=None):

        self.code = code
        self.voucher_type = voucher_type
        self.issued_at = issued_at      # NEW: needed for unused_vouchers.csv

        self.remaining_balance = float(voucher_type.quantity)
        self.activated = False
        self.activation_time = None
        self.expiry_time = None

        self.active_devices = set()
        self.devices_used = set()       # NEW: every MAC that ever logged in

    def activate(self, login_time):

        if not self.activated:
            self.activated = True
            self.activation_time = login_time
            self.expiry_time = login_time + timedelta(hours=24)

            return True

        return self.is_valid(login_time)

    def is_valid(self, current_time):

        if not self.activated:
            return True

        return current_time < self.expiry_time

    # ---- original methods (unchanged, so nothing that uses them breaks) ----
    def consume_time(self, minutes):

        if self.voucher_type.voucher_type != "TIME":
            return False

        if minutes <= 0:
            return False

        if minutes > self.remaining_balance:
            return False

        self.remaining_balance -= minutes
        return True

    def consume_data(self, mb):

        if self.voucher_type.voucher_type != "DATA":
            return False

        if mb <= 0:
            return False

        charged_mb = math.ceil(mb)

        if charged_mb > self.remaining_balance:
            return False

        self.remaining_balance -= charged_mb
        return True

    # ---- NEW methods: cap at the remaining balance instead of refusing ----
    # (BR-02 / BR-03: a session or event that would exceed the balance is
    #  cut exactly when the balance reaches zero, so we charge what is left.)
    def charge_minutes(self, minutes):
        """Deduct minutes (may be fractional while a session is running),
        never below 0. Returns the amount actually charged."""
        charged = max(0.0, min(minutes, self.remaining_balance))
        self.remaining_balance -= charged
        if self.remaining_balance <= EPS:
            self.remaining_balance = 0.0
        return charged

    def charge_mb(self, mb, round_up=True):
        """Deduct MB, never below 0. round_up=True rounds the event up to the
        next whole MB first (BR-06 as written); round_up=False deducts the raw
        MB. Returns the MB actually charged."""
        amount = math.ceil(mb) if round_up else mb
        charged = max(0.0, min(amount, self.remaining_balance))
        self.remaining_balance -= charged
        if self.remaining_balance <= EPS:
            self.remaining_balance = 0.0
        return charged

    def is_exhausted(self):
        return self.remaining_balance <= EPS

    def consumed(self):
        return self.voucher_type.quantity - self.remaining_balance
