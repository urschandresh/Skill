# User guide

ZTB ShiftOrbit runs in your browser at **http://127.0.0.1:8000** after `start.ps1`. Only
this computer can open it.

## 1. First-time setup

1. **Projects & shifts.** Click *New project*. Default shifts M (06–15), A (14–23) and N (22–07)
   are created with a minimum of 1 analyst each.
   - Change timings with the pencil icon. An end time before the start time means the shift
     ends the next day.
   - Tick *Night shift* for shifts that count toward night fairness and night limits.
   - Add shifts such as D or AN with *Add shift*. Overlapping shift times are allowed;
     ShiftOrbit still never books one analyst on overlapping shifts.
   - *Add requirement* sets the minimum (and optional maximum) staff for a shift. It can apply
     to every day, one weekday, or a specific date. The most specific rule wins.
2. **Settings → Skills** (optional). Then require skills on a project or a shift.
3. **Analysts.** Click *New analyst*, or import a spreadsheet (section 6).
   - Add each project the analyst may work. Optionally restrict the shifts, e.g. "M, A".
   - Mark one project as primary.
   - Preferences (preferred or avoided shifts, preferred days off) are soft: they are
     followed when possible.
   - *Settings → Availability* holds hard exceptions, e.g. "unavailable on the 12th" or
     "no N on the 3rd".
4. **Settings → Policies.** The default policy is 5 working days per week (2 weekly offs),
   11 h minimum rest, at most 6 consecutive days, at most 5 consecutive nights and 48 h per
   week. The fairness weights are also set here.
5. **Settings → Code mappings.** These tell ShiftOrbit what codes in old roster files mean
   (M, A, N, D, AN, WO, OFF, L, LEAVE, PL, H are preset).

Want to explore first? *Settings → Backup & data → Load synthetic demo data* (empty database only).

## 2. Leave

*Leave → Submit leave.* Choose the analyst, dates and type. For part of a day, tick *Partial
day* and give times. New requests are **pending**.

- **Approve / Reject** with the row icons. Approved leave is always respected by the generator.
- **Edit** an approved leave → it goes back to pending.
- **Cancel** pending or approved leave.
- **Impact** opens a panel. It works for pending requests too and never changes the roster.
  - It shows which assigned shifts clash with the leave, and which rules would break if those
    shifts were dropped (coverage, weekly days…).
  - **Replacement suggestions**: analysts who could take each shift. Those marked green add no
    rule violations. *Assign* moves the shift (draft rosters only).
  - **Simulate regeneration** re-solves the days around the leave and reports how many
    assignments would change, without saving.
  - **Regenerate affected shifts** (approved leave) creates a new **draft** in which only those
    days changed.
- **Leave calendar** tab: monthly view of approved and pending leave.

## 3. Generating a roster

*Generate roster* opens a 10-step wizard:

1. **Month**
2. **Projects**
3. **Analysts.** Untick anyone to exclude.
4. **Leave.** Review it. Ticking pending leave turns the run into a simulation; nothing is saved.
5. **Rules.** Pick a policy and optionally override it for this run, including the solver time
   limit (default 30 s).
6. **Feasibility.** A quick check for definite blockers, such as a shift with fewer eligible
   people than required.
7. **Generate.** Shows the real solver state: elapsed time against the limit, solutions found,
   best objective and proven bound. *Cancel* stops the search; if a valid roster was already
   found, it is kept.
8. **Validate.** The independent validator's verdict.
9. **Review.** Per-analyst shifts, hours, nights, weekends and leave.
10. **Save / export.** The roster is saved as a **draft**. Open the editor or export to Excel.

Result meanings: **OPTIMAL** (best possible), **FEASIBLE** (valid, maybe not the fairest
possible; allow more time for better), **INFEASIBLE** (no roster can satisfy all hard rules;
the conflicting rules are listed, e.g. "SOC1/N on 14 Nov: needs 1, 0 available (2 on leave)"),
**TIMEOUT** (nothing found in time; increase the limit).

## 4. Editing a roster

Open it from *Rosters*.

**Views:**
- **Monthly matrix:** analysts × days. Cell markers:
  - **WO** weekly off, **LEAVE** approved leave, **H** holiday
  - **½L** partial leave
  - dashed amber outline with **PL?** = pending leave
  - red cell = a hard-rule problem (hover for details); red column header = understaffed day
- **Shift view:** shifts × days with assigned/required counts.
- **Week** and **Month calendar:** timed events. Use the filters for a project-wise,
  analyst-wise or shift-wise view.

**Edits (draft rosters only):**
- Drag a shift chip to another analyst or day (matrix), or drag an event to another day (calendars).
- Click a cell to add, change or remove a shift, or to lock or unlock it. Locked shifts (🔒)
  are kept by regeneration and cannot be dragged.
- Every edit is checked first. If it breaks a hard rule, you see exactly which rules, and you
  can cancel or save with a written reason. Overrides are recorded and the roster stays
  flagged.
- **Undo / Redo** (or Ctrl+Z / Ctrl+Y).

**Roster actions:**
- **Regenerate:** re-solve a date range with minimum disruption. The result is a new draft.
- **Publish:** makes the draft the official roster (read-only); the previous published version
  is archived. Publishing a roster with violations requires a reason.
- **New draft version:** copies a published roster for changes.

## 5. Dashboard

For the selected month: projects, active analysts, pending leave, coverage %, staffing
alerts, shift distribution, workload per analyst and recent solver runs.

## 6. Import and export

*Import / Export*:

**Export.** Download an editable XLSX with these sheets:
- Monthly Roster (colour-coded, frozen headers, filters)
- Project Coverage, Leave Register, Workload Summary
- Shift Legend, Validation Report, Configuration

**Import**, for analysts, leave or a roster:
1. Choose the type and the file (.xlsx or .csv, at most 5 MB), then click *Preview*.
2. Check the column mapping (ShiftOrbit guesses it from the headers).
3. Click *Validate & import*. If any row has a problem, **nothing** is imported and every
   problem is listed with its row number.

Templates for analysts and leave are available on the same page.

**Previous SOC roster format:** analysts in rows, days 1–31 (or dates) as columns, codes per
cell.
- Map unknown codes first in *Settings → Code mappings*.
- Choose the month, and the project the codes belong to.
- Save the roster as **Historical**, the read-only reference used for month continuity, or as
  **Draft**.
- Formulas and macro-enabled files are refused.

## 7. Data safety

*Settings → Backup & data*:
- **Create backup** writes a copy to `data/backups`. *Download* saves it elsewhere.
- **Restore** replaces all data with a backup. A safety backup is taken first.
- **Delete all local data** (type `DELETE ALL DATA`) removes everything, including backups.

Back up before major changes and keep backups on encrypted storage (see SECURITY.md).
