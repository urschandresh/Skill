# Local UAT checklist (Windows)

Perform on a ZTB Windows laptop. Use synthetic data first; switch to real data only on
the local machine with authorisation. Record pass/fail and notes for each item.

Tester: ____________  Date: ________  Windows version: ________  Python: ______  Node: ______

## A. Installation and startup

| # | Step | Expected | Pass |
|---|---|---|---|
| A1 | `powershell -ExecutionPolicy Bypass -File .\setup.ps1` | Ends with "Setup complete", prints OR-Tools version | ☐ |
| A2 | `.\start.ps1` | Browser opens http://127.0.0.1:8000; sidebar shows "Local-only" and the solver version | ☐ |
| A3 | `netstat -ano \| findstr :8000` | Only `127.0.0.1:8000` LISTENING (not 0.0.0.0) | ☐ |
| A4 | From another computer, open http://<laptop-ip>:8000 | Cannot connect | ☐ |
| A5 | `.\stop.ps1`, then reload the browser | App stops; `.\start.ps1` again works and data is still there | ☐ |
| A6 | Run `.\start.ps1` twice | Second run says already running | ☐ |

## B. Setup data

| # | Step | Expected | Pass |
|---|---|---|---|
| B1 | Settings → Backup & data → Load synthetic demo data | 2 projects, 12 SYN analysts appear | ☐ |
| B2 | Create a project "TEST" | M/A/N shifts with minimum 1 each | ☐ |
| B3 | Edit N to 21:00–06:00 | Shows "(+1)", 9.0 h | ☐ |
| B4 | Add a D shift 09:00–18:00 and a weekday requirement of 2 | Listed under staffing | ☐ |
| B5 | Try shift code `WO` or end time 30 minutes after start | Rejected with a clear message | ☐ |
| B6 | Create an analyst eligible for 2 projects, only M/A on one | Badges show the restriction | ☐ |

## C. Leave

| # | Step | Expected | Pass |
|---|---|---|---|
| C1 | Submit 3-day leave next month | Status pending | ☐ |
| C2 | Overlapping leave for the same analyst | Refused | ☐ |
| C3 | Partial-day leave 09:00–13:00 | Saved as partial | ☐ |
| C4 | Approve C1; edit it | Goes back to pending | ☐ |
| C5 | Leave calendar tab | Leave shown in colour by status | ☐ |

## D. Generation

| # | Step | Expected | Pass |
|---|---|---|---|
| D1 | Wizard: next month, both SYN projects, all analysts | Steps advance | ☐ |
| D2 | Feasibility check | "No blockers found" | ☐ |
| D3 | Generate (30 s) | Live elapsed time, solutions count; ends OPTIMAL or FEASIBLE; UI stays responsive (try navigating) | ☐ |
| D4 | Validate step | "every hard rule holds" | ☐ |
| D5 | Open the editor | Approved leave days show LEAVE with no shifts on them | ☐ |
| D6 | Spot-check: no analyst has M the morning after an N or A shift | Rest rule holds | ☐ |
| D7 | Spot-check full Mon–Sun weeks | 5 working days per analyst, minus full leave days | ☐ |
| D8 | Generate with only 3 analysts selected | INFEASIBLE with readable reasons; no roster saved | ☐ |
| D9 | Generate with a 120 s limit, then Cancel after a few seconds | Stops promptly; message says stopped by user | ☐ |

## E. Editing and versions

| # | Step | Expected | Pass |
|---|---|---|---|
| E1 | Drag a shift to the same analyst's WO day | Either saved, or a dialog lists the broken rules | ☐ |
| E2 | Cancel in that dialog | Roster unchanged | ☐ |
| E3 | Save with an override reason | Saved; cell red; reason visible in the cell editor | ☐ |
| E4 | Undo, then Redo (buttons and Ctrl+Z/Ctrl+Y) | Changes reverse and reapply | ☐ |
| E5 | Lock a shift; try to drag it | Not draggable; regeneration keeps it | ☐ |
| E6 | Week and Month calendar tabs, filters by project/analyst/shift | Correct times (night shifts end next morning) | ☐ |
| E7 | Publish | Read-only; previous published (if any) archived | ☐ |
| E8 | New draft version; regenerate a 5-day window | New draft; outside the window unchanged | ☐ |

## F. Leave impact on a published roster

| # | Step | Expected | Pass |
|---|---|---|---|
| F1 | Submit pending leave on a day an analyst works; open Impact | Clashing shift listed; roster NOT changed | ☐ |
| F2 | Replacement suggestions | Ranked candidates; green ones add no violations | ☐ |
| F3 | Simulate regeneration | Shows how many assignments would change; no new roster | ☐ |
| F4 | Approve, then Regenerate affected shifts | New draft, leave day shows LEAVE, validation passes | ☐ |

## G. Excel

| # | Step | Expected | Pass |
|---|---|---|---|
| G1 | Export XLSX; open in Excel | 7 sheets; colours; frozen headers; filters; no security warnings | ☐ |
| G2 | Rename an analyst to `=1+1` (synthetic), export | Cell shows `=1+1` as text, not 2 | ☐ |
| G3 | Re-import the exported roster as Draft | Same assignments; validation passes | ☐ |
| G4 | Import `sample-data/SYNTHETIC_analysts.csv` (create project SOC1 first) | 7 created; importing again skips 7 | ☐ |
| G5 | Import a file with one bad row | Nothing imported; the row is listed | ☐ |
| G6 | Import a .xlsm or a file > 5 MB | Refused | ☐ |
| G7 | **Real historical roster (August 2026), on this machine only.** Set code mappings, import as Historical | Imports or lists precise problems | ☐ |
| G8 | Generate September 2026 after G7 | Notes mention continuity from the previous month | ☐ |

## H. Data management and security

| # | Step | Expected | Pass |
|---|---|---|---|
| H1 | Create backup, change data, restore it | Data returns to backup state; pre-restore backup created | ☐ |
| H2 | Delete all local data (type the phrase) | Everything gone, including backups | ☐ |
| H3 | Dashboard on a phone-sized window (browser dev tools) | Usable layout, menu button works | ☐ |
| H4 | Check disk encryption and folder location | BitLocker on; data folder not in OneDrive or another synced folder | ☐ |

## Sign-off

Accepted for internal use:  ☐ Yes  ☐ No. Blocking issues: ______________________________
