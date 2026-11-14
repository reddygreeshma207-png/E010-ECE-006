# Decision log — E010-ECE-006

Each entry: what the brief left open, what we chose, why, and how to change it.

| # | Question | Decision | Reason | If changed |
|---|---|---|---|---|
| D1 | Is data rounded up per event, or is raw MB deducted? | Raw MB as received (24.6 MB charges 24.6). | The sample README accepts either if stated, and the brief's "0.4 MB remaining, 1 MB event" edge case only arises with raw deduction. | Set `DATA_ROUND_UP = True` in `session_engine.py`; sample voucher `D100-G6S6M5` then ends at 12:16 instead of 12:20. |
| D2 | Is a repeated LOGIN from an already-connected MAC an error? | Ignored: no new session, no log row, no error. | Sample README: "ignored (no error, no new session)". | Log it as `REJECTED / DUPLICATE_LOGIN`. |
| D3 | When is report status (ACTIVE / EXPIRED / EXHAUSTED) judged? | At the end of the report date (midnight snapshot). EXHAUSTED wins over EXPIRED. | One clock per report date; a voucher can only be EXPIRED once 24 h have passed. | Judge at the last processed event. |
| D4 | Reason for a USAGE event after the device was cut off (balance exhausted)? | `NOT_LOGGED_IN`. | The README treats LOGOUT after a cut and USAGE after an idle logout as `NOT_LOGGED_IN`; the device has no session. | `USAGE_AFTER_CUTOFF_REASON = "BALANCE_EXHAUSTED"` in `session_engine.py` (changes 5 sample rows). |
| D5 | What happens to a running session when the 24 h window ends? | It keeps running; only new LOGINs are rejected. | The brief only says logins after the window are rejected. | Cut running sessions at the expiry time. |
| D6 | What does `remaining` show on a TIME voucher row? | The live balance at the event time (clock runs continuously). | Matches how the shared balance is consumed. | Show closed-session balance only. |
| D7 | Time consumed continuously vs charged rounded up per session. | Balance is consumed continuously; a session row charges minutes rounded up. | All sample timestamps are whole minutes, so both agree (checked: report consumed equals the sum of session charges for every TIME voucher). | If timestamps carried seconds, round the balance per session. |
| D8 | Exactly 24 h after activation. | Expired: window is `[activation, activation + 24 h)`. | Listed in the brief; the sample plants it (`T180-95CUW7`). | Use `<=` in `Voucher.is_valid`. |
| D9 | Amount larger than the balance. | Charge only what remains, never below 0 (`charge_minutes`, `charge_mb`). | Brief: the session is cut at the exact moment the balance hits zero. | — |
| D10 | Folder path of the input files. | `main.py` uses its own folder (or the folder given as an argument). | The evaluators run the code on their own machine. | — |
