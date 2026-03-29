# Plan: User-Based Authorization for CalendarApp

## Context
The CalendarApp currently has no access control — all events and special days are visible to everyone. The database schema already has `events.user_id` and `specialdays.company`/`specialdays.user` columns but they're unused by the CLI and visualizers. This plan adds authentication (password-based) and authorization (user sees only their events, company's special days) to the CLI.

---

## Step 1: Schema — Add `companies` and `users` Tables

**File:** `shared/db_access.py` (add table-creation methods or inline DDL)
**File:** `tools/seed_auth_data.py` (new — seed script)

```sql
CREATE TABLE IF NOT EXISTS companies (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    country  TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    company_id    INTEGER NOT NULL REFERENCES companies(id),
    name          TEXT,
    email         TEXT,
    active        INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
```

Also ensure the `companyspecialdays` view exists (code already queries this name):
```sql
CREATE VIEW IF NOT EXISTS companyspecialdays AS SELECT * FROM specialdays;
```

A method `CalendarDB.ensure_auth_tables()` will create these if missing.

---

## Step 2: Auth Module

**New file:** `shared/auth.py`

- `hash_password(password) -> str` — SHA-256 + random salt (stdlib `hashlib`, no new deps)
- `verify_password(password, stored_hash) -> bool`
- `authenticate_user(db_path, user_id, password) -> dict | None` — returns `{id, username, company_id, name}` or `None`
- `get_password(args_password) -> str` — uses `--password` arg or falls back to `getpass.getpass()`

---

## Step 3: Config Fields

**File:** `config/config.py`

Add to `CalendarConfig`:
```python
user_id: int | None = None
company_id: int | None = None
company_name: str | None = None
```

---

## Step 4: DB Filtering

**File:** `shared/db_access.py`

| Method | Change |
|--------|--------|
| `get_all_events_in_range(start, end)` | Add `user_id: int | None = None` param; append `AND user_id = ?` when set |
| `get_special_days_for_date(daykey)` | Add `company: str | None = None` param; append `AND company = ?` when set |
| `is_nonworkday(daykey, country)` | Add `company: str | None = None` param; pass to special-days query |
| `get_special_markings_for_date(daykey)` | Add `company: str | None = None` param; pass through |
| `get_holiday_title_for_date(daykey, country)` | Add `company: str | None = None` param; pass through |
| NEW: `get_user_company_name(user_id)` | JOIN users/companies, return company name |

---

## Step 5: CLI Arguments + Auth Gate

**File:** `ecalendar.py`

**5a.** Add `--userid` (`-uid`, int) and `--password` (`-pw`, str) to all calendar-view subparsers (weekly, mini, mini-icon, text-mini, timeline, blockplan, compactplan, excelheader, exportdata).

**5b.** In `run()`, after DB open but before calendar generation:
- If `--userid` provided: get password (flag or prompt), call `authenticate_user()`, set `config.user_id/company_id/company_name`
- If auth fails: print error, `return 1`
- If `--userid` missing on a view command: print error, `return 1`

**5c.** Add `add-company` and `add-user` subcommands:
- `add-company <name> [--country CODE]` — inserts company, prints ID
- `add-user <username> --company-id ID [--name N] [--email E] [--password P]` — hashes password, inserts user, prints ID

---

## Step 6: Wire Filtering Into Visualizers

**File:** `visualizers/base.py` (~line 381)
- Pass `user_id=config.user_id` to `db.get_all_events_in_range()`

**Files with special-day calls** — pass `company=config.company_name`:
- `visualizers/weekly/renderer.py` (lines 452, 551)
- `visualizers/blockplan/renderer.py` (line 408)
- `visualizers/mini/day_styles.py` (line 124)
- `visualizers/text_mini/renderer.py` (line 289)
- `visualizers/excelheader.py` (lines 203, 345)
- `ecalendar.py` exportdata path (line 2815)

---

## Step 7: Seed Data Script

**New file:** `tools/seed_auth_data.py`

- Creates tables (idempotent)
- Inserts default company (id=1, "Default Company")
- Inserts default user (id=1, username="admin", password="changeme", company_id=1)
- Updates orphan events to `user_id=1`

Run: `uv run python tools/seed_auth_data.py [--database calendar.db]`

---

## Step 8: Tests

**New file:** `tests/test_auth.py`
- Hash/verify round-trip, wrong password, authenticate success/failure

**Update:** `tests/test_db_access_resilience.py`
- Event filtering by user_id, special days filtering by company

**Update:** existing test mocks (test_text_mini, test_excelheader, test_blockplan, test_mini_day_styles)
- Add `company=None` default to mock `get_special_days_for_date`, `is_nonworkday` signatures

---

## Implementation Order

1. Schema + seed script (Step 1, 7)
2. Auth module (Step 2)
3. Config fields (Step 3)
4. DB filtering (Step 4)
5. CLI args + auth gate + admin commands (Step 5)
6. Visualizer wiring (Step 6)
7. Tests (Step 8)

## Verification

1. `uv run python tools/seed_auth_data.py` — creates tables and seed data
2. `uv run python ecalendar.py add-company "Acme Corp"` — returns company ID
3. `uv run python ecalendar.py add-user alice --company-id 1 --password secret123`
4. `uv run python ecalendar.py weekly 20260301 20260401 --userid 1 --password changeme` — generates calendar with only user 1's events
5. `uv run python ecalendar.py weekly 20260301 20260401 --userid 1 --password wrong` — exits with auth error
6. `uv run python ecalendar.py weekly 20260301 20260401` — exits with "userid required" error
7. `uv run python -m pytest tests/ -v` — all tests pass
