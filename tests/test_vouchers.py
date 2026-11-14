import os, sys, unittest
from datetime import datetime
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from voucher_manager import VoucherManager


def loaded():
    m = VoucherManager()
    m.load_types(os.path.join(ROOT, "voucher_types.csv"))
    m.load_vouchers(os.path.join(ROOT, "vouchers.csv"))
    return m


class VoucherTests(unittest.TestCase):

    def test_load_types_and_vouchers(self):
        m = loaded()
        self.assertEqual(len(m.voucher_types), 4)
        self.assertEqual(len(m.vouchers), 60)
        self.assertEqual(len(m.unused_rows()), 60)          # nothing activated yet

    def test_activation_starts_24h_window(self):
        m = loaded(); c = "T180-95CUW7"
        t0 = datetime(2026, 10, 15, 6, 30)
        m.activate(c, t0)
        m.activate(c, datetime(2026, 10, 15, 9, 0))         # later login must not reset it
        self.assertEqual(m.vouchers[c].activation_time, t0)

    def test_24h_boundary(self):
        m = loaded(); c = "T180-95CUW7"
        m.activate(c, datetime(2026, 10, 15, 6, 30))
        self.assertFalse(m.is_expired(c, datetime(2026, 10, 16, 6, 29, 59)))
        self.assertTrue(m.is_expired(c, datetime(2026, 10, 16, 6, 30, 0)))   # exactly 24 h

    def test_data_rounds_up_and_stops_at_zero(self):
        m = loaded(); v = m.get("D100-G6S6M5")
        self.assertEqual(v.charge_mb(24.6), 25)
        self.assertEqual(v.remaining_balance, 75)
        v.charge_mb(30.0); v.charge_mb(25.0); v.charge_mb(20.0)
        self.assertTrue(v.is_exhausted())
        self.assertEqual(v.charge_mb(5.0), 0)
        self.assertEqual(v.remaining_balance, 0)

    def test_time_never_negative(self):
        m = loaded(); v = m.get("T60-GPQAF7")
        self.assertEqual(v.charge_minutes(70), 60)
        self.assertEqual(v.remaining_balance, 0)

    def test_report_revenue_on_activation_day(self):
        m = loaded(); c = "T60-HV4WBX"
        v = m.get(c)
        v.activate(datetime(2026, 10, 16, 0, 40)); v.devices_used.add("AA:BB")
        now = datetime(2026, 10, 16, 7, 0)
        self.assertEqual(m.report_rows("2026-10-15", now), [])
        row = m.report_rows("2026-10-16", now)[0]
        self.assertEqual(row, ["2026-10-16", c, "VT-01", "TIME", "2026-10-16 00:40:00",
                               "0", "60", 1, "20.00", "ACTIVE"])
        self.assertEqual(len(m.unused_rows()), 59)

    def test_exhausted_and_expired_status(self):
        m = loaded()
        a = m.get("T60-GPQAF7"); a.activate(datetime(2026, 10, 15, 10, 0)); a.charge_minutes(60)
        b = m.get("T180-95CUW7"); b.activate(datetime(2026, 10, 15, 6, 30))
        now = datetime(2026, 10, 16, 7, 0)
        self.assertEqual(m.status(a, now), "EXHAUSTED")
        self.assertEqual(m.status(b, now), "EXPIRED")

    def test_bad_type_input_does_not_crash(self):
        m = VoucherManager()
        self.assertFalse(m.register_type("T60", "TIME", "sixty", 20, 2))
        self.assertFalse(m.register_type("T60", "TIME", 60, 20, 0))
        self.assertTrue(m.register_type("T60", "TIME", 60, 20, 2))
        self.assertFalse(m.register_type("T60", "TIME", 60, 20, 2))   # duplicate prefix


if __name__ == "__main__":
    unittest.main()
