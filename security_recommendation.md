# Security Recommendations for security.md

## Critical Issues

**1. Password in CLI arg (`--password`) is a major security risk**
Shell history (`~/.zsh_history`) and process listings (`ps aux`) expose plaintext passwords. The plan should either:
- Remove `--password` entirely and always use `getpass.getpass()`
- Or add an environment variable fallback (`CALENDAR_PASSWORD`) as the only non-interactive option
- If `--password` is kept for scripting, document the risk explicitly and recommend it only with secrets managers

**2. `tools/authorize.py` has no access control**
Anyone who can run the tool can add companies, reset passwords, or delete users — with no authentication required. The admin tool itself needs a protection mechanism (e.g., require a superadmin password, or restrict via file permissions + a dedicated admin account).

**3. Default seed credentials (`admin` / `changeme`) are a known-bad pattern**
Step 8 seeds a default admin account with a well-known password. If the database is deployed without a password change, this is an open door. Recommendations:
- Generate a random password at seed time and print it once
- Or require the operator to provide the admin password as an argument to the seed script
- Add a warning if the hash for "changeme" is still in the database at runtime

---

## Moderate Issues

**4. `pbkdf2_hmac` is acceptable but not best-in-class**
`argon2-cffi` (Argon2id) or `bcrypt` are the current recommendations for password hashing — they're memory-hard and more resistant to GPU cracking. If staying with `pbkdf2_hmac`, ensure iteration count is at least 600,000 (NIST 2023 guidance for SHA-256).

**5. No account lockout / brute-force protection**
The plan has no failed-login tracking. Add a `failed_login_count` and `locked_until` column to `users`, and lock the account after N failures (e.g., 5).

**6. `companyspecialdays` view doesn't filter**
```sql
CREATE VIEW IF NOT EXISTS companyspecialdays AS SELECT * FROM specialdays;
```
This view returns all companies' special days — it's not filtering by company at all. The actual filtering happens in Python query parameters, but the view name implies isolation it doesn't provide. Either make it a parameterized query (views can't take parameters in SQLite), or rename it to avoid the false security implication.

**7. No audit log**
Admin actions (add/delete/reset-password) and authentication events (success/failure) should be logged. At minimum, a simple `auth_log` table with `(timestamp, action, username, ip_or_pid, success)` allows forensics if accounts are compromised.

---

## Minor Issues / Improvements

**8. Inconsistency: `--userid` vs `--username`**
Step 5a adds `--username` to parsers, but Step 5b references `--userid`. Pick one. Username is more user-friendly; user_id is more backend-appropriate. The auth flow should accept username (human-readable) and resolve to `user_id` internally.

**9. `delete` commands lack cascade/safety checks**
Deleting a company that has users and events should either fail with a clear error ("company has N users; deactivate instead") or require `--force` with a confirmation prompt. Same for deleting users with events.

**10. No `created_at` / `updated_at` on `users`/`companies`**
Add `created_at TEXT DEFAULT (datetime('now'))` and `updated_at TEXT` to both tables. Useful for auditing and the `resetpassword` flow.

**11. Database file permissions not addressed**
The plan doesn't mention that `calendar.db` should be `chmod 600` (owner-read only). If the database lives in a shared directory, all the auth work is moot. Add a note in the seed script to set restrictive permissions after creation.

**12. `password_hash` column should store algorithm metadata**
Use a standard format like PHC string format (`$argon2id$...` or `$pbkdf2-sha256$...`) so the verify function can detect the algorithm and support future migration without a separate schema change. Python's `hashlib` doesn't do this automatically — the plan should specify the stored format.

**13. Timing-safe comparison**
`verify_password` must use `hmac.compare_digest()` (or equivalent) to prevent timing attacks when comparing hashes. This should be called out explicitly in the auth module spec.

---

## Summary Table

| # | Issue | Severity | Fix |
|---|-------|----------|-----|
| 1 | `--password` in CLI args | Critical | Use `getpass` or env var only |
| 2 | Admin tool unprotected | Critical | Require auth for admin ops |
| 3 | Seed default password | Critical | Generate random or require input |
| 4 | Weak hash params | Moderate | Use Argon2id or high-iter PBKDF2 |
| 5 | No brute-force protection | Moderate | Add failed login tracking |
| 6 | View name misleading | Moderate | Rename or document clearly |
| 7 | No audit log | Moderate | Add `auth_log` table |
| 8 | `--userid`/`--username` inconsistency | Minor | Pick one |
| 9 | Unsafe deletes | Minor | Add guards/`--force` |
| 10 | No timestamps on tables | Minor | Add `created_at` |
| 11 | DB file permissions | Minor | `chmod 600` in seed script |
| 12 | Hash format | Minor | Use PHC string format |
| 13 | Timing-safe comparison | Minor | Use `hmac.compare_digest()` |
