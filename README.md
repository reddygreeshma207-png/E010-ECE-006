# E010-ECE-006 — Wi-Fi Hotspot Voucher & Session Accounting Engine

Command-file driven engine for a Wi-Fi operator: issues time-based and data-based vouchers, processes
LOGIN / USAGE / LOGOUT events, enforces device limits and idle timeouts, and reports voucher consumption and revenue.
Language: **Python 3.10+**, standard library only.

**Team:** Greeshma Reddy R (voucher management) · Gowthami J (session management)

## How to run
```
python main.py                               # reads commands.txt, writes the four output CSVs next to it
python -m unittest discover -s tests -v      # 22 tests (voucher part + session part + full sample run)
```
`python main.py <folder>` runs on another folder that contains `commands.txt` and the CSV files (for example the hidden input set).

## Files
| File | Purpose | Owner |
|---|---|---|
| `models.py` | `VoucherType`, `Voucher`: balances, activation, 24 h validity, charging | Greeshma |
| `voucher_manager.py` | Loads voucher types and vouchers, activation, expiry check, voucher report, unused list | Greeshma |
| `session_engine.py` | LOGIN/USAGE/LOGOUT, device limit, idle timeout, TIME exhaustion, session log, errors | Gowthami |
| `main.py` | Reads `commands.txt`, calls both parts, writes the CSVs | Both |
| `tests/test_vouchers.py`, `tests/test_sessions.py` | Unit tests and a full sample run | Both |
| `Design_Document.pdf`, `DECISIONS.md` | Design document (BR register) and decision log | Both |
| `commands.txt`, `voucher_types.csv`, `vouchers.csv`, `events.csv` | Sample input | — |

## Input
`commands.txt` lines (separated by `|`): `LOAD_VOUCHER_TYPES|file`, `ISSUE_VOUCHERS|file`, `PROCESS_EVENTS|file`, `REPORT|YYYY-MM-DD`.

## Output
| File | Content |
|---|---|
| `session_log.csv` | `timestamp, voucher_code, device_mac, action, charged, remaining, reason` in time order |
| `voucher_report.csv` | `report_date, voucher_code, type_id, kind, activated_at, consumed, remaining, devices_used, revenue_rs, status` |
| `unused_vouchers.csv` | `voucher_code, type_id, issued_at` for vouchers never activated |
| `errors.csv` | `event_id, reason` for rejected events |

## Business rules and decisions
BR-01 to BR-13 and the policy decisions D1 to D7 are in `Design_Document.pdf` and `DECISIONS.md`.
Two policies can be switched at the top of `session_engine.py`: `DATA_ROUND_UP` (data rounding) and
`USAGE_AFTER_CUTOFF_REASON` (reason for a USAGE event after a cut-off).

## Sample result
60 vouchers issued, 53 activated, 7 unused, 692 session-log rows, 13 error records.
