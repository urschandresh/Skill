# Sample data: SYNTHETIC ONLY

Every file here is invented test data. No real ZTB employees, rosters or leave appear.

| File | Purpose |
|---|---|
| `SYNTHETIC_historical_soc_roster_2026-08.xlsx` | Mimics the *layout* of the previous SOC roster (7 analysts, M/A/N, WO, L). The assignments are invented. **It is not the real August 2026 roster**, which has not been supplied yet. |
| `SYNTHETIC_analysts.csv` | Analyst import example (needs a project with code `SOC1`). |
| `SYNTHETIC_leave_2026-11.csv` | Leave import example (needs the analysts above). |

Regenerate with `python scripts/make_synthetic_fixtures.py`.

When the real historical roster is provided, import it on the local Windows machine only
(Import / Export > Roster, "Historical"), and check the code mappings in
Settings > Code mappings first. Do not commit it to this repository.
