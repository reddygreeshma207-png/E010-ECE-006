# E010-ECE-006 — Wi-Fi Hotspot Voucher & Session Accounting Engine

Command-file driven engine for a Wi-Fi operator: issues time-based and data-based vouchers, processes
LOGIN / USAGE / LOGOUT events, enforces device limits and idle timeouts, and reports voucher consumption and revenue.
Language: **Python 3.10+**, standard library only.

**Team:** Greeshma Reddy R (voucher management) · Gowthami J (session management)

## Files
| File | Purpose |
|---|---|
| `models.py` | `VoucherType`, `Voucher` (balances, activation, 24 h validity, charging) |
| `voucher_manager.py` | Loads voucher types and vouchers, activation, status, `voucher_report.csv`, `unused_vouchers.csv` |
| `session_engine_corrected_v3.py` | LOGIN/LOGOUT/USAGE processing, device limit, idle timeout, session log, errors |
| `main.py` | Reads `commands.txt` and runs the voucher commands |
| `tests/test_vouchers.py` | Unit tests for the voucher part |
| `commands.txt`, `voucher_types.csv`, `vouchers.csv`, `events.csv` | Sample input |
| `Design_Document.pdf`, `DECISIONS.md` | Design document and decision log |

## How to run
```
python session_engine_corrected_v3.py        # full run: writes the four output CSVs
python -m unittest discover -s tests -v      # voucher tests (8 tests)
```

## Input
`commands.txt` lines (separated by `|`): `LOAD_VOUCHER_TYPES`, `ISSUE_VOUCHERS`, `PROCESS_EVENTS`, `REPORT|YYYY-MM-DD`.

## Output
| File | Content |
|---|---|
| `session_log.csv` | `timestamp, voucher_code, device_mac, action, charged, remaining, reason` in time order |
| `voucher_report.csv` | `report_date, voucher_code, type_id, kind, activated_at, consumed, remaining, devices_used, revenue_rs, status` |
| `unused_vouchers.csv` | `voucher_code, type_id, issued_at` for vouchers never activated |
| `errors.csv` | `event_id, reason` for rejected events |

## Business rules
BR-01 to BR-13 are listed in `Design_Document.pdf`. Key ones: the 24 h window starts at the first successful LOGIN and
a LOGIN at exactly 24 h is `EXPIRED`; time is rounded up per session, data per event; idle timeout is 10 minutes;
revenue counts on the activation date.

## Sample result
60 vouchers issued, 53 activated, 7 unused, 13 error records.
