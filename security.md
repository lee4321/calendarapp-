# Plan: User-Based Authorization for CalendarApp

## Context
The CalendarApp currently has no access control — all events and special days are visible to everyone. The database schema already has `events.user_id` and `specialdays.company`/`specialdays.user` columns but they're unused by the CLI and visualizers. This plan adds authentication (password-based) and authorization (user sees only their events, company's special days) to the CLI.

To create companies and users a new tool will be built that allows:
+ add company 
+ add user to company 
+ 

---

## Step 1: Schema — Add `companies` and `users` Tables

**File:** `shared/db_access.py` (add table-creation methods or inline DDL)
**File:** `tools/seed_auth_data.py` (new — seed script)

```sql
CREATE TABLE IF NOT EXISTS companies (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    legalname     TEXT NOT NULL,
    legalid       TEXT,
    commonname    TEXT,
    address1      TEXT,
    address2      TEXT,
    region        TEXT,
    city          TEXT,
    postalcode    TEXT,
    country  TEXT,
    primarycontactphone TEXT,
    primarycontactname  TEXT,
    active         INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    employeeid    TEXT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    company_id    INTEGER NOT NULL REFERENCES companies(id),
    givenname     TEXT,
    familyname    TEXT,
    email         TEXT,
    active        INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
```

Also ensure the `companyspecialdays` view exists (code already queries this name):
```sql
CREATE VIEW IF NOT EXISTS companyspecialdays AS SELECT * FROM specialdays;
```

```
CREATE TABLE IF NOT EXISTS company_defaults (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id    INTEGER NOT NULL REFERENCES companies(id),
    palette       TEXT,
    logo          TEXT,
    primary_font  TEXT,
    secondary_font TEXT,
    icon_set      TEXT
);
```


A method `CalendarDB.ensure_auth_tables()` will create these if missing.

---

## Step 2: Auth Module

**New file:** `shared/auth.py`

- `hash_password(password) -> str` — hashlib.pbkdf2_hmac() + random salt
- `verify_password(password, stored_hash) -> bool`
- `authenticate_user(db_path, username, password) -> dict | None` — returns `{id, username, company_id, givenname, familyname, active}` or `None` W
- `get_password(args_password) -> str` — uses `--password` arg or falls back to `getpass.getpass()`

WHERE company and user has active = 1

---

## Step 3: Config Fields

**File:** `config/config.py`

Add to `CalendarConfig`:
```python
user_id: int | None = None
company_id: int | None = None
company_commonname: str | None = None
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

## Step 5: Auth Gate

**5a.** Add `--username` and `--password` (`-pw`, str) to all calendar-view subparsers (weekly, mini, mini-icon, text-mini, timeline, blockplan, compactplan, excelheader, exportdata).

**5b.** In `run()`, after DB open but before calendar generation:
- If `--userid` provided: get password (flag or prompt), call `authenticate_user()`, set `config.user_id/company_id/company_name`
- If auth fails: print error, `return 1`
- If `--userid` missing on a view command: print error, `return 1`

Ensure no user can access any other's data. 


## Step 6: New CLIs  

**New file:** `tools/authorize.py`

**6a.** create a new tool to manage companies and users  
- Add `add-company` and `add-user` subcommands:
- `add-company <name> [--country CODE]` — inserts company, prints ID
- `add-user <username> --company-id ID [--name N] [--email E] [--password P]` — hashes password, inserts user, prints ID
- 'deactivate' --company-id ID sets the active flag to 0
- 'deactivate' --user-id ID set the active flag to 0
- 'activate' --company-id ID sets the active flag to 1
- 'activate' --user-id ID set the active flag to 1
- 'list-companies' prints a list of companies and their company-ids 
- 'list-users' --company-id prints a list of users for the company 
- 'update-company' --company-id ID updates the company attributes
- 'update-user' -- user-id ID updates the user attributes 
- 'resetpassword' --user-id ID [--email E] [--password P]` — hashes password
- 'delete' --user-id ID removes a user from the users table
- 'delete' --company-id ID removes a company from the companies table 

**New file:** `tools/defaults.py`

**6b.** create a new tool to manage defaults for companies
- 'list' --company-id ID prints a list of attributes and their values from the company_defaults table
- 'update' --company-id ID updates provided attributes with their new values
- 'delete' --company-id ID removes the default values for the specified company

---

## Step 7: Wire Filtering Into Visualizers

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

## Step 8: Seed Data Script

**New file:** `tools/seed_auth_data.py`

- Creates tables (idempotent)
- Inserts default company (id=1, "Default Company")
- Inserts default user (id=1, username="admin", password="changeme", company_id=1)
- Updates orphan events to `user_id=1`

Run: `uv run python tools/seed_auth_data.py [--database calendar.db]`

---

## Step 9: Tests

**New file:** `tests/test_auth.py`
- Hash/verify round-trip, wrong password, authenticate success/failure
- Verify if company or user active = 0 then the authentication should fail

**Update:** `tests/test_db_access_resilience.py`
- Event filtering by user_id, special days filtering by company

**Update:** existing test mocks (test_text_mini, test_excelheader, test_blockplan, test_mini_day_styles)
- Add `company=None` default to mock `get_special_days_for_date`, `is_nonworkday` signatures

**Update:** update existing tests to include authentication information 

---

## Implementation Order

1. Schema + seed script (Step 1, 8)
2. Auth module (Step 2)
3. Config fields (Step 3)
4. DB filtering (Step 4)
5. CLI args + auth gate + admin commands (Step 5)
6. CLI admin commands (Step 6)
7. Visualizer wiring (Step 7)
8. Tests (Step 9)

## Verification

1. `uv run python tools/seed_auth_data.py` — creates tables and seed data
2. `uv run python tools/authorize.py add-company "Acme Corp"` — returns company ID
3. `uv run python tools/authorize.py add-user alice --company-id 1 --password secret123`
4. `uv run python ecalendar.py weekly 20260301 20260401 --userid 1 --password changeme` — generates calendar with only user 1's events
5. `uv run python ecalendar.py weekly 20260301 20260401 --userid 1 --password wrong` — exits with auth error
6. `uv run python ecalendar.py weekly 20260301 20260401` — exits with "userid required" error
7. `uv run python -m pytest tests/ -v` — all tests pass
