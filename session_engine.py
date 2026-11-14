"""Session management: LOGIN / USAGE / LOGOUT processing, device limit, idle
timeout, TIME-voucher exhaustion, session log and error list.

This is the session-engine logic (clock advance, idle logout, shared TIME
balance, cut-offs) organised as a class that works on a VoucherManager.
All voucher state (balances, activation, 24 h validity, devices used,
report rows) lives in voucher_manager.py / models.py.
"""
import csv
import math
import os
from datetime import datetime, timedelta

# ---------------------------------------------------------------- policies
# D1: data rounding.  False = deduct raw MB as received (24.6 MB -> 24.6).
#                     True  = round each USAGE event up to the next MB (24.6 -> 25).
DATA_ROUND_UP = False
# D4: reason for a USAGE event whose session was already ended by a cut-off.
#     "NOT_LOGGED_IN" (device no longer has a session) or "BALANCE_EXHAUSTED".
USAGE_AFTER_CUTOFF_REASON = "NOT_LOGGED_IN"

IDLE_MINUTES = 10                 # BR-05
TIME_EPS_SKIP = 1e-10             # "no balance left" when looking for next event
TIME_EPS_CUT = 1e-8               # "balance reached zero" after advancing the clock

TS_FMT = "%Y-%m-%d %H:%M:%S"
PRIORITY = {"LOGIN": 1, "USAGE": 2, "LOGOUT": 3}    # BR-08


def parse_timestamp(value):
    return datetime.strptime(value.strip(), TS_FMT)


def format_timestamp(value):
    return value.strftime(TS_FMT)


def event_id_key(value):
    """EVT-0009 sorts before EVT-0010."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if digits:
        return (0, int(digits), str(value))
    return (1, 0, str(value))


def load_events(path):
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class SessionEngine:

    def __init__(self, manager, data_round_up=DATA_ROUND_UP):
        self.manager = manager
        self.data_round_up = data_round_up
        self.active = {}            # (voucher_code, device_mac) -> session dict
        self.session_log = []
        self.errors = []
        self.snapshots = {}         # report_date -> report rows (taken at midnight)
        self.clock = None
        self.events_processed = 0

    # ----------------------------------------------------------- logging
    def _log(self, when, code, mac, action, charged, remaining, reason="NONE"):
        self.session_log.append({
            "timestamp": format_timestamp(when),
            "voucher_code": code,
            "device_mac": mac,
            "action": action,
            "charged": round(float(charged), 6),
            "remaining": round(float(remaining), 6),
            "reason": reason,
        })

    def _reject(self, event, reason):
        self.errors.append({"event_id": event.get("event_id", ""), "reason": reason})
        code = event.get("voucher_code", "")
        voucher = self.manager.get(code)
        remaining = voucher.remaining_balance if voucher else 0.0
        self._log(parse_timestamp(event["timestamp"]), code,
                  event.get("device_mac", ""), "REJECTED", 0, remaining, reason)

    def _sessions_of(self, code):
        return [key for key in self.active if key[0] == code]

    def _is_time(self, voucher):
        return voucher.voucher_type.voucher_type == "TIME"

    # ----------------------------------------------------- ending sessions
    def _finish(self, key, when, action):
        session = self.active.get(key)
        if session is None:
            return
        code, mac = key
        voucher = self.manager.get(code)
        # TIME: whole minutes, rounded up per session (BR-06).
        # DATA: MB is charged on USAGE rows, so closing a session charges 0.
        if self._is_time(voucher):
            charged = math.ceil(max(0.0, session["connected_minutes"]) - 1e-10)
        else:
            charged = 0.0
        self._log(when, code, mac, action, charged, voucher.remaining_balance)
        del self.active[key]

    # ------------------------------------------------------------ the clock
    def advance_to(self, target):
        """Move the clock to `target`, applying idle logouts (BR-05) and TIME
        exhaustion (BR-02) at their exact moments (BR-09)."""
        if self.clock is None:
            self.clock = target
            return
        if target < self.clock:
            raise ValueError("Events are not in chronological order.")

        vouchers = self.manager.vouchers
        while self.clock < target:
            if not self.active:
                self.clock = target
                return

            next_time = target

            # earliest idle deadline
            for s in self.active.values():
                deadline = s["last_activity"] + timedelta(minutes=IDLE_MINUTES)
                if self.clock < deadline <= next_time:
                    next_time = deadline

            # earliest shared TIME-voucher exhaustion
            for code, v in vouchers.items():
                if not self._is_time(v) or v.remaining_balance <= TIME_EPS_SKIP:
                    continue
                devices = len(self._sessions_of(code))
                if devices:
                    exhaustion = self.clock + timedelta(minutes=v.remaining_balance / devices)
                    if self.clock < exhaustion <= next_time:
                        next_time = exhaustion

            elapsed = (next_time - self.clock).total_seconds() / 60.0

            if elapsed > 0:
                # every active device on a TIME voucher consumes 1 min per minute
                for code, v in vouchers.items():
                    if not self._is_time(v) or v.remaining_balance <= TIME_EPS_SKIP:
                        continue
                    devices = len(self._sessions_of(code))
                    if devices:
                        v.charge_minutes(elapsed * devices)
                for s in self.active.values():
                    s["connected_minutes"] += elapsed

            self.clock = next_time

            # idle logouts that have arrived
            for key, s in list(self.active.items()):
                deadline = s["last_activity"] + timedelta(minutes=IDLE_MINUTES)
                if deadline <= self.clock:
                    self._finish(key, deadline, "IDLE_LOGOUT")

            # cut every remaining device on an exhausted TIME voucher
            for code, v in vouchers.items():
                if self._is_time(v) and v.remaining_balance <= TIME_EPS_CUT:
                    v.remaining_balance = 0.0
                    for key in list(self._sessions_of(code)):
                        self._finish(key, self.clock, "CUT_OFF")

    # ------------------------------------------------------------- events
    def login(self, event):
        code, mac = event["voucher_code"], event["device_mac"]
        when = parse_timestamp(event["timestamp"])
        key = (code, mac)
        voucher = self.manager.get(code)

        if voucher is None:
            return self._reject(event, "UNKNOWN_VOUCHER")
        if key in self.active:                                   # BR-10: ignored
            return
        if self.manager.is_expired(code, when):                  # BR-01
            return self._reject(event, "EXPIRED")
        if len(self._sessions_of(code)) >= voucher.voucher_type.max_devices:   # BR-04
            return self._reject(event, "DEVICE_LIMIT")
        if voucher.remaining_balance <= TIME_EPS_SKIP:
            voucher.remaining_balance = 0.0
            return self._reject(event, "BALANCE_EXHAUSTED")

        self.manager.activate(code, when)                        # first login starts 24 h
        self.active[key] = {"login_time": when, "last_activity": when,
                            "connected_minutes": 0.0}
        voucher.devices_used.add(mac)
        self._log(when, code, mac, "LOGIN", 0, voucher.remaining_balance)

    def usage(self, event):
        code, mac = event["voucher_code"], event["device_mac"]
        when = parse_timestamp(event["timestamp"])
        key = (code, mac)
        voucher = self.manager.get(code)

        if voucher is None:
            return self._reject(event, "UNKNOWN_VOUCHER")
        if key not in self.active:                               # BR-12
            exhausted = voucher.remaining_balance <= TIME_EPS_SKIP
            if exhausted and USAGE_AFTER_CUTOFF_REASON == "BALANCE_EXHAUSTED":
                return self._reject(event, "BALANCE_EXHAUSTED")
            return self._reject(event, "NOT_LOGGED_IN")

        charged = 0.0
        if not self._is_time(voucher):
            mb_used = float(event.get("mb", 0) or 0)
            if mb_used < 0:
                return self._reject(event, "INVALID_USAGE")
            charged = voucher.charge_mb(mb_used, round_up=self.data_round_up)   # BR-03/06

        self.active[key]["last_activity"] = when                 # restart idle clock
        self._log(when, code, mac, "USAGE", charged, voucher.remaining_balance)

        if not self._is_time(voucher) and voucher.remaining_balance <= TIME_EPS_CUT:
            voucher.remaining_balance = 0.0                      # BR-03: end all sessions
            for k in list(self._sessions_of(code)):
                self._finish(k, when, "CUT_OFF")

    def logout(self, event):
        code, mac = event["voucher_code"], event["device_mac"]
        when = parse_timestamp(event["timestamp"])
        key = (code, mac)

        if self.manager.get(code) is None:
            return self._reject(event, "UNKNOWN_VOUCHER")
        if key not in self.active:                               # BR-12
            return self._reject(event, "NOT_LOGGED_IN")
        self._finish(key, when, "LOGOUT")

    # ---------------------------------------------------------- main loop
    def process(self, events):
        """Process events in timestamp order. After each calendar day the clock
        moves to midnight and that day's report snapshot is taken."""
        good = []
        for row in events:
            try:
                parse_timestamp(row["timestamp"])
                good.append(row)
            except (KeyError, ValueError, AttributeError):
                self.errors.append({"event_id": row.get("event_id", ""),
                                    "reason": "INVALID_EVENT"})

        ordered = sorted(good, key=lambda r: (
            parse_timestamp(r["timestamp"]),
            PRIORITY.get((r.get("event_type") or "").strip().upper(), 99),   # BR-08
            event_id_key(r.get("event_id", ""))))
        self.events_processed = len(events)

        i = 0
        while i < len(ordered):
            day = parse_timestamp(ordered[i]["timestamp"]).date()
            j = i
            while j < len(ordered) and parse_timestamp(ordered[j]["timestamp"]).date() == day:
                event = ordered[j]
                self.advance_to(parse_timestamp(event["timestamp"]))
                kind = event["event_type"].strip().upper()
                if kind == "LOGIN":
                    self.login(event)
                elif kind == "USAGE":
                    self.usage(event)
                elif kind == "LOGOUT":
                    self.logout(event)
                else:
                    self._reject(event, "UNKNOWN_EVENT_TYPE")
                j += 1

            midnight = datetime.combine(day + timedelta(days=1), datetime.min.time())
            self.advance_to(midnight)
            date_str = day.strftime("%Y-%m-%d")
            self.snapshots[date_str] = self.manager.report_rows(date_str, midnight)
            i = j
