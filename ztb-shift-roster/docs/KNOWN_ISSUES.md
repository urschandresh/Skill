# Known issues and limitations

Honest list as of version 0.1.0. Items marked **UAT** need checking on a ZTB Windows machine.

## Not yet verified

1. **Windows has not been tested at all (UAT).**
   - Everything was built and tested in a Linux cloud container.
   - `setup.ps1`, `start.ps1` and `stop.ps1` were written for Windows PowerShell 5.1 and 7.x
     but **were never executed**. No PowerShell was available, and downloading one was not
     permitted in the build environment.
   - Expect possible first-run fixes.
   - The Linux/macOS equivalents (`setup.sh`, `start.sh`, `stop.sh`) were run from a fresh
     clone and work. They follow the same steps, so a Windows failure is most likely a
     PowerShell-specific detail.
   - `start.ps1` starts the backend with `Start-Process -WindowStyle Hidden` plus output
     redirection. On some systems a console window may still appear briefly.
2. **OR-Tools wheels on Windows (UAT).** `ortools==9.15.6755` publishes Windows wheels for
   Python 3.11–3.13. Not installed on Windows yet.
3. **The real historical roster (August 2026) has not been supplied.**
   - The import adapter is tested only with a *synthetic* file in the expected layout
     (`sample-data/`).
   - The real file may use other codes, merged header cells or extra rows; adjust
     *Settings → Code mappings* and report anything that fails.
4. **Meaning of the D and AN codes is unconfirmed.** They are mapped to shift templates named
   D and AN, but no default timings exist. Create those templates with the real times before
   importing rosters that use them.

## Functional limitations

5. **Single user, no login.** See SECURITY.md.
6. **No schema migrations.** The database stores a schema version. A future version with a
   different schema refuses to open the old database instead of migrating it. Export or back up
   before upgrading.
7. **Solver performance.** Measured in the 4-vCPU build container:

   | Size | Result |
   |---|---|
   | 7 analysts, 1 project, Nov 2026 | OPTIMAL in 0.8 s |
   | 12 analysts, 2 projects | OPTIMAL in 2.3 s |
   | 30 analysts, 4 projects | OPTIMAL in 4.0 s |
   | 40 analysts, 4 shared projects (14,400 variables) | OPTIMAL in 14.7 s |

   - The synthetic demo set (leave, preferences, two-person weekday mornings) stopped at
     **FEASIBLE** after the 30 s limit. The roster is valid; fairness may not be perfectly
     minimal. Allow more time for better results.
   - Building very large models takes several seconds in Python before solving starts.
   - The maximum time limit is 600 s.
   - Laptop speed will differ.
   - With soft preferences switched on, the reported "bound" can stay far below the objective
     (e.g. objective 2.7 M vs bound 0.7 k after 15 s on the demo set). A large gap here mostly
     means the solver could not *prove* how good the roster is. Some preference penalties are
     unavoidable. It is not an error.
8. **Non-deterministic optima.** Multi-threaded CP-SAT can return different, equally good
   rosters on repeated runs.
9. **Month-boundary weeks.**
   - In the last week of a month, days in the next month are unknown. That week may get fewer
     than 5 days in this roster; the next month's run completes it using the published roster.
   - If an imported or previous roster makes a boundary week impossible, the rule is limited
     to what can still change, and a `weekly_days_inherited` warning is shown.
10. **Full-day leave blocks shifts that *start* on the leave day.** A night shift starting the
    evening before (ending at 07:00 on the leave day) is not blocked. Use partial-day leave
    (e.g. 00:00–07:00) when that matters.
11. **Holidays** are informational unless "blocks work" is ticked. Holiday pay and comp-off
    accounting are not implemented.
12. **No leave balances, entitlements, emails or notifications.**
13. **Replacement suggestions** consider single swaps only. They are not a full re-solve; use
    *Regenerate affected shifts* for that. Response time grows with team size: about one full
    validation per candidate per shift.
14. **Imported historical rosters** store LEAVE and H as day markers, not as leave records, so
    they do not appear in the Leave Register.
15. **Calendar drag-and-drop changes the date only.** Use the cell editor to change the shift
    or project. The week view becomes crowded with many analysts; use the filters.
16. **Undo/redo history** lasts only while the roster page is open. Undoing a change that was
    saved with an override may need a new override.
17. **Stored rosters are validated against today's leave and settings.** A roster that was
    valid can show violations after new leave is approved; that is the intended "impact"
    signal.
18. **Partial-day leave times** are read in the analyst's primary project timezone.
19. **Keyboard users** cannot drag in the matrix; the cell editor offers the same actions by
    keyboard.
20. **API documentation page** (`/api/docs`) is off by default because it loads assets from a
    public CDN. `/api/openapi.json` is available.

## Engineering notes

- The frontend bundle is a single ~0.96 MB JS chunk (290 KB gzipped); this is acceptable for
  local use.
- `@hookform/resolvers` is pinned to 5.9.2 (6.0.0 had a broken peer-dependency chain).
  FullCalendar is pinned to 6.1.22 and react-hook-form to 7.91.0 (stable lines).
- Playwright 1.64 expects its own browser build. In environments with a different Chromium,
  set `PW_CHROMIUM` to its path. On Windows, `npx playwright install chromium` is enough.
