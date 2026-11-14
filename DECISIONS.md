# Decision log — E010-ECE-006

Each entry: what the brief left open, what we chose, why, and what would change if the evaluators decide otherwise.

| # | Date | Question | Decision | Reason | If changed |
|---|---|---|---|---|---|
| D1 | 14 Nov | Is data rounded up per event, or is raw MB deducted? | Round up per event (`math.ceil`). 24.6 MB charges 25 MB. | Business rule 6 says so explicitly. | Use `charge_mb` without ceil; one sample voucher (`D100-G6S6M5`) would end at 12:20 instead of 12:16. |
| D2 | 14 Nov | Is a repeated LOGIN from an already-connected MAC an error? | Logged as `REJECTED / DUPLICATE_LOGIN` in the session log, not written to `errors.csv`. | The sample-data README says it is ignored with no error. | Also append it to `errors.csv`. |
| D3 | 14 Nov | When is voucher status (ACTIVE / EXPIRED / EXHAUSTED) evaluated? | At the last processed event time. EXHAUSTED wins over EXPIRED. | One consistent clock for all report dates. | Evaluate at the end of each report date. |
| D4 | 14 Nov | What does `remaining` show on LOGIN/USAGE rows of a time voucher? | The committed balance (closed sessions only). | Running sessions are charged when they end, so the value stays deterministic. | Subtract live elapsed time. |
| D5 | 14 Nov | What happens to a running session when the 24 h window ends? | It keeps running; only new LOGINs are rejected. | The brief only says logins after the window are rejected. | Cut running sessions at the expiry time. |
| D6 | 14 Nov | Exactly 24 h after activation. | Expired (window is `[activation, activation + 24 h)`). | Brief lists it as an explicit edge case and the sample file plants it (`T180-95CUW7`). | Use `<=` in `is_valid`. |
| D7 | 14 Nov | Balance rules when an amount exceeds what is left. | Charge only what remains, never below 0 (`charge_minutes`, `charge_mb`). | Brief: the session is cut at the exact moment the balance hits zero. | — |
| D8 | 14 Nov | Hardcoded folder path in the session engine. | Use the script's own folder (`os.path.dirname(os.path.abspath(__file__))`). | The evaluators run it on their own machine. | — |
| D9 | 14 Nov | Which unit tests prove the voucher part? | `tests/test_vouchers.py`: loading, activation, 24 h boundary, rounding, negative balance, revenue day, status, bad input. | Covers every voucher-related rule and edge case in the brief. | — |
