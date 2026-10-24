# Security assessment

Scope: ZTB ShiftOrbit 0.1.0 as a single-user application on a ZTB Windows laptop. It
handles staff names, optional emails, leave and work schedules (personal data).
Assessment date: October 2026. Method: design review plus automated tests
(`backend/tests/test_security*.py`, `test_admin.py`, `test_excel.py`).

## Threat model

| Actor | In scope? | Notes |
|---|---|---|
| Other computers on the network | Yes | Blocked: server binds 127.0.0.1 only. |
| Malicious web pages open in the user's browser (CSRF, DNS rebinding, cross-origin reads) | Yes | Main local-web risk; mitigated below. |
| Malicious spreadsheet files | Yes | Imports are parsed defensively. |
| Spreadsheet formula injection into exports | Yes | Neutralised. |
| Other software running as the same Windows user | **No (cannot be solved here)** | It can read the database file and call the API. |
| Physical theft of the laptop | Partly | Depends on disk encryption (BitLocker) and Windows login. |

## Controls

| Control | Implementation | Test evidence |
|---|---|---|
| Loopback-only binding | `config.Settings.validate` refuses non-loopback hosts unless `ZTB_ALLOW_NON_LOOPBACK=1`; scripts pass `127.0.0.1`; Vite dev server also bound to 127.0.0.1 | `test_non_loopback_host_refused` |
| DNS-rebinding protection | Host header must be 127.0.0.1, localhost or ::1 | `test_dns_rebinding_host_rejected` |
| CSRF / unauthorised origins | Every POST/PUT/PATCH/DELETE under /api needs `X-ZTB-Request: 1` (cannot be sent cross-origin without a CORS preflight), a foreign `Origin` is refused, and `Sec-Fetch-Site: cross-site` is refused | `test_every_state_changing_route_requires_csrf_header` checks **all** write routes |
| CORS | Only local frontend origins; no credentials | `test_cors_preflight_only_for_local_origin` |
| Browser hardening | CSP `default-src 'self'` (no external scripts, connections or frames), X-Frame-Options DENY, nosniff, no-referrer, COOP/CORP, Permissions-Policy | `test_security_headers_present` |
| Input validation | Pydantic schemas with `extra="forbid"`, length limits, patterns, control-character rejection, range checks; FastAPI 422 on bad types | `test_invalid_project_inputs`, `test_invalid_generation_input`, leave tests |
| SQL injection | SQLAlchemy ORM with bound parameters only; no string-built SQL | `test_sql_metacharacters_stored_literally` |
| Error leakage | Integrity errors return a generic 409; unhandled errors return a plain 500 | `test_duplicate_project_code_conflict`, `test_internal_errors_do_not_leak_details` |
| Upload limits | Global request body limit (5 MB + overhead, 200 MB only for restore); .xlsx/.csv only; zip magic check; total uncompressed size ≤ 60 MB; macro (vbaProject) workbooks refused; ≤ 5000 rows / 200 columns; formula cells refused | `test_upload_restrictions`, `test_oversized_body_rejected`, `test_unknown_code_and_formula_rejected` |
| Formula injection in exports | Text starting with `= + - @ TAB CR LF` is prefixed with `'` and stored as a string cell; the workbook is checked to contain no `<f>` formula elements | `test_export_has_all_sheets_and_formatting` |
| Path traversal | Backup names must match a strict pattern and resolve inside `data/backups`; SPA static files must resolve inside `dist/` | `test_backup_download_path_traversal_blocked`, `test_spa_static_path_traversal` |
| Restore safety | SQLite header check, `PRAGMA integrity_check`, required tables, schema version; safety backup before overwrite | `test_backup_restore_roundtrip`, `test_restore_rejects_bad_files` |
| Data deletion | Deletes all rows and backup files, then checkpoints the WAL and VACUUMs so deleted rows do not remain in free pages | `test_delete_all_data` (checks the raw file bytes) |
| Logging hygiene | Logs record IDs, counts and statuses, never names or free text; the audit log stores IDs and counts only | `test_logs_do_not_contain_staff_names` |
| No telemetry / third parties | No analytics, no external fonts (bundled), no CDN; API docs page (CDN assets) disabled by default | manual review of `frontend/dist` (only namespace/help-text URLs), CSP blocks outbound connections |
| Dependencies | Exact pins in `requirements.txt`; `npm ci` from `package-lock.json`; `npm install` reported 0 known vulnerabilities at build time | – |

## Residual risks and limitations (please read)

1. **No user authentication.** Anyone who can use this Windows account can use the app and
   read `data/shiftorbit.db`. Localhost is not an authentication boundary. Use a personal
   Windows account with a strong password and screen lock.
2. **No encryption at rest by the app.** Enable **BitLocker** (or equivalent) on the laptop.
   Backups and exported XLSX files contain personal data; store and share them carefully.
3. **Same-user local processes** can call the API (the CSRF header protects only against web
   pages). Malware on the machine is out of scope.
4. **Deleted data on SSDs.** VACUUM rewrites the database file, but SSD wear-levelling and OS
   copies (e.g. backups made outside the app, OneDrive sync of the folder) may keep fragments.
   Do not place the `data` folder in a cloud-synced directory.
5. **Exported files leave the app's control.** The formula guard protects the cells, but files
   emailed onward are outside ShiftOrbit's protection.
6. **Override reasons and notes** are free text stored locally; avoid putting sensitive personal
   details (e.g. medical reasons) in them. Leave *reason* fields are optional.
7. **Server logs** go to `.run/backend.log` (access log) and `.run/backend.err.log` (application
   log). They contain URLs with numeric IDs and statuses only, no names. Delete the `.run` folder if needed.
8. The Windows scripts were **not executed** during this build (no Windows/PowerShell available
   in the build environment). Check that the server listens only on 127.0.0.1 during UAT
   (`netstat -ano | findstr :8000` should show `127.0.0.1:8000` only).
9. **Cloud build environment:** development and testing used synthetic data only. No real
   employee data was used or uploaded.
