
from models import VoucherType, Voucher


class VoucherManager:

    def __init__(self):
        self.voucher_types = {}
        self.vouchers = {}
        self.counters = {}

    def register_type(self, prefix, voucher_type,
                      quantity, price, max_devices):

        prefix = prefix.upper()
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

        if not isinstance(max_devices, int):
            print("Error: Device limit must be an integer!")
            return False

        if not isinstance(quantity, (int, float)):
            print("Error: Invalid quantity!")
            return False

        if not isinstance(price, (int, float)):
            print("Error: Invalid price!")
            return False

        if isinstance(quantity, bool) or isinstance(price, bool):
            print("Error: Invalid numeric values!")
            return False

        if isinstance(max_devices, bool):
            print("Error: Invalid device limit!")
            return False

        if isinstance(quantity, float) and quantity.is_integer():
            quantity = int(quantity)

        new_type = VoucherType(
            prefix, voucher_type, quantity,
            price, max_devices
        )

        self.voucher_types[prefix] = new_type
        self.counters[prefix] = 0

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
