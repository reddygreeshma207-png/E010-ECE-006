import os, sys, unittest
from datetime import datetime
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from voucher_manager import VoucherManager
from models import Voucher
from session_engine import SessionEngine
import main

DAY = "2026-10-15"


def build(vouchers, data_round_up=False):
    """vouchers: list of (code, kind). TIME = 60 min / 2 devices, DATA = 100 MB / 1 device
    (D500 = 500 MB / 2 devices)."""
    m = VoucherManager(); m.verbose = False
    m.register_type("T60", "TIME", 60, 20, 2, "VT-01")
    m.register_type("T180", "TIME", 180, 40, 3, "VT-02")
    m.register_type("D100", "DATA", 100, 30, 1, "VT-03")
    m.register_type("D500", "DATA", 500, 99, 2, "VT-04")
    for code in vouchers:
        prefix = code.split("-")[0]
        m.vouchers[code] = Voucher(code, m.voucher_types[prefix], datetime(2026, 10, 14, 10, 0))
    return m, SessionEngine(m, data_round_up=data_round_up)


def ev(rows, day=DAY):
    """rows: (HH:MM:SS, TYPE, code, mac, mb)"""
    return [{"event_id": f"EVT-{i:04d}", "timestamp": f"{day} {t}", "event_type": k,
             "voucher_code": c, "device_mac": mac, "mb": str(mb)}
            for i, (t, k, c, mac, mb) in enumerate(rows, 1)]


def actions(engine, code=None):
    return [(r["timestamp"][11:], r["action"], r["device_mac"], r["charged"], r["remaining"], r["reason"])
            for r in engine.session_log if code in (None, r["voucher_code"])]


def keepalive(code, mac, start_min, end_min, step=5, hour=10):
    return [(f"{hour:02d}:{m:02d}:00", "USAGE", code, mac, 0.0) for m in range(start_min + step, end_min, step)]


class SessionTests(unittest.TestCase):

    def test_two_devices_exhaust_together(self):
        m, e = build(["T60-A"])
        rows = [("10:00:00", "LOGIN", "T60-A", "M1", 0.0), ("10:00:00", "LOGIN", "T60-A", "M2", 0.0)]
        rows += keepalive("T60-A", "M1", 0, 30) + keepalive("T60-A", "M2", 0, 30)
        rows += [("10:35:00", "LOGOUT", "T60-A", "M1", 0.0), ("10:35:00", "LOGOUT", "T60-A", "M2", 0.0)]
        e.process(ev(rows))
        cuts = [a for a in actions(e) if a[1] == "CUT_OFF"]
        self.assertEqual([(a[0], a[3]) for a in cuts], [("10:30:00", 30.0), ("10:30:00", 30.0)])
        self.assertEqual([x["reason"] for x in e.errors], ["NOT_LOGGED_IN", "NOT_LOGGED_IN"])
        self.assertTrue(m.get("T60-A").is_exhausted())

    def test_single_device_cut_before_logout(self):
        m, e = build(["T60-A"])
        rows = [("16:00:00", "LOGIN", "T60-A", "M1", 0.0)]
        rows += [(f"{16 + k // 60:02d}:{k % 60:02d}:00", "USAGE", "T60-A", "M1", 0.0) for k in range(6, 60, 6)]
        rows += [("17:15:00", "LOGOUT", "T60-A", "M1", 0.0)]
        e.process(ev(rows))
        self.assertIn(("17:00:00", "CUT_OFF", "M1", 60.0, 0.0, "NONE"), actions(e))
        self.assertEqual(e.errors[-1]["reason"], "NOT_LOGGED_IN")

    def test_idle_logout_then_late_usage_rejected_and_not_deducted(self):
        m, e = build(["D500-A"])
        e.process(ev([("11:00:00", "LOGIN", "D500-A", "M1", 0.0),
                      ("11:06:00", "USAGE", "D500-A", "M1", 8.0),
                      ("11:20:00", "USAGE", "D500-A", "M1", 50.0)]))
        self.assertIn(("11:16:00", "IDLE_LOGOUT", "M1", 0.0, 492.0, "NONE"), actions(e))
        self.assertEqual(e.errors, [{"event_id": "EVT-0003", "reason": "NOT_LOGGED_IN"}])
        self.assertEqual(m.get("D500-A").remaining_balance, 492.0)

    def test_idle_logout_on_time_voucher_charges_to_idle_moment(self):
        m, e = build(["T180-A"])
        e.process(ev([("17:00:00", "LOGIN", "T180-A", "M1", 0.0), ("17:09:00", "USAGE", "T180-A", "M1", 1.0)]))
        self.assertIn(("17:19:00", "IDLE_LOGOUT", "M1", 19.0, 161.0, "NONE"), actions(e))

    def test_device_limit_and_repeated_mac_ignored(self):
        m, e = build(["D500-A"])
        e.process(ev([("15:00:00", "LOGIN", "D500-A", "M1", 0.0), ("15:02:00", "LOGIN", "D500-A", "M2", 0.0),
                      ("15:05:00", "LOGIN", "D500-A", "M3", 0.0), ("15:07:00", "LOGIN", "D500-A", "M1", 0.0)]))
        self.assertEqual(e.errors, [{"event_id": "EVT-0003", "reason": "DEVICE_LIMIT"}])
        self.assertEqual(sum(1 for a in actions(e) if a[1] == "LOGIN"), 2)       # repeat: no new session
        self.assertEqual(sum(1 for a in actions(e) if a[1] == "REJECTED"), 1)    # and no log row

    def test_login_exactly_24h_after_activation_is_expired(self):
        m, e = build(["T180-A"])
        e.process(ev([("06:30:00", "LOGIN", "T180-A", "M1", 0.0), ("06:35:00", "USAGE", "T180-A", "M1", 0.0),
                      ("06:40:00", "LOGOUT", "T180-A", "M1", 0.0)]) +
                  ev([("06:29:59", "LOGIN", "T180-A", "M2", 0.0), ("06:30:00", "LOGIN", "T180-A", "M3", 0.0)],
                     day="2026-10-16"))
        logins = [(a[0], a[1], a[5]) for a in actions(e) if a[2] in ("M2", "M3") and a[1] != "IDLE_LOGOUT"]
        self.assertEqual(logins, [("06:29:59", "LOGIN", "NONE"), ("06:30:00", "REJECTED", "EXPIRED")])

    def test_unknown_voucher_and_logout_without_login(self):
        m, e = build(["D100-A"])
        e.process(ev([("13:00:00", "LOGIN", "T60-ZZZ", "M1", 0.0), ("13:40:00", "LOGOUT", "D100-A", "DE:AD", 0.0)]))
        self.assertEqual([x["reason"] for x in e.errors], ["UNKNOWN_VOUCHER", "NOT_LOGGED_IN"])

    def _data_case(self, round_up):
        m, e = build(["D100-A"], data_round_up=round_up)
        rows = [("12:00:00", "LOGIN", "D100-A", "M1", 0.0)] + [
            (f"12:{4 * i:02d}:00", "USAGE", "D100-A", "M1", mb) for i, mb in enumerate([24.6, 30.0, 25.0, 20.0, 1.0, 2.0], 1)]
        e.process(ev(rows)); return m, e

    def test_data_raw_policy_04mb_remaining_then_1mb_event(self):
        m, e = self._data_case(False)
        a = actions(e)
        self.assertIn(("12:16:00", "USAGE", "M1", 20.0, 0.4, "NONE"), a)
        self.assertIn(("12:20:00", "USAGE", "M1", 0.4, 0.0, "NONE"), a)       # only 0.4 MB left is charged
        self.assertIn(("12:20:00", "CUT_OFF", "M1", 0.0, 0.0, "NONE"), a)
        self.assertEqual(e.errors, [{"event_id": "EVT-0007", "reason": "NOT_LOGGED_IN"}])

    def test_data_round_up_policy_exhausts_earlier(self):
        m, e = self._data_case(True)
        a = actions(e)
        self.assertIn(("12:16:00", "USAGE", "M1", 20.0, 0.0, "NONE"), a)
        self.assertIn(("12:16:00", "CUT_OFF", "M1", 0.0, 0.0, "NONE"), a)

    def test_out_of_order_rows_and_same_second_priority(self):
        m, e = build(["T60-A"])
        e.process(ev([("10:00:00", "LOGOUT", "T60-A", "M1", 0.0), ("10:00:00", "USAGE", "T60-A", "M1", 1.0),
                      ("10:00:00", "LOGIN", "T60-A", "M1", 0.0)]))
        self.assertEqual([a[1] for a in actions(e)], ["LOGIN", "USAGE", "LOGOUT"])

    def test_malformed_event_is_reported_not_crash(self):
        m, e = build(["T60-A"])
        e.process([{"event_id": "EVT-9", "timestamp": "not a time", "event_type": "LOGIN",
                    "voucher_code": "T60-A", "device_mac": "M1", "mb": "0.0"}])
        self.assertEqual(e.errors, [{"event_id": "EVT-9", "reason": "INVALID_EVENT"}])


class FullSampleRun(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.out = tempfile.mkdtemp()
        cls.manager, cls.engine = main.run(ROOT, cls.out)

    def test_counts_match_sample_pack(self):
        self.assertEqual(len(self.manager.vouchers), 60)
        self.assertEqual(len(self.manager.unused_rows()), 7)       # README: 7 never activated
        self.assertEqual(len(self.engine.session_log), 692)
        self.assertEqual(len(self.engine.errors), 13)

    def test_planted_scenarios(self):
        a = lambda code: actions(self.engine, code)
        self.assertIn(("10:30:00", "CUT_OFF", "19:57:B3:94:13:54", 30.0, 0.0, "NONE"), a("T60-GPQAF7"))
        self.assertTrue(any(x[1] == "REJECTED" and x[5] == "EXPIRED" for x in a("T180-95CUW7")))
        self.assertTrue(any(x[0] == "11:16:00" and x[1] == "IDLE_LOGOUT" for x in a("D500-B8WV6W")))
        self.assertTrue(any(x[0] == "17:00:00" and x[1] == "CUT_OFF" for x in a("T60-XFUU7K")))
        self.assertTrue(any(x[0] == "17:19:00" and x[1] == "IDLE_LOGOUT" and x[3] == 19.0 for x in a("T180-A6FNRH")))
        self.assertTrue(any(x[5] == "DEVICE_LIMIT" for x in a("D500-8ET9ZG")))
        self.assertTrue(any(x[5] == "UNKNOWN_VOUCHER" for x in actions(self.engine)))
        self.assertTrue(any(x[0] == "12:20:00" and x[1] == "CUT_OFF" for x in a("D100-G6S6M5")))

    def test_log_is_in_time_order_and_files_written(self):
        stamps = [r["timestamp"] for r in self.engine.session_log]
        self.assertEqual(stamps, sorted(stamps))
        for f in ("session_log.csv", "voucher_report.csv", "unused_vouchers.csv", "errors.csv"):
            self.assertTrue(os.path.exists(os.path.join(self.out, f)))


if __name__ == "__main__":
    unittest.main()
