
from datetime import datetime, timedelta
import math


class VoucherType:

    def __init__(self, prefix, voucher_type, quantity,
                 price, max_devices):

        self.prefix = prefix
        self.voucher_type = voucher_type.upper()
        self.quantity = quantity
        self.price = price
        self.max_devices = max_devices


class Voucher:

    def __init__(self, code, voucher_type):

        self.code = code
        self.voucher_type = voucher_type

        self.remaining_balance = voucher_type.quantity
        self.activated = False
        self.activation_time = None
        self.expiry_time = None

        self.active_devices = set()

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
