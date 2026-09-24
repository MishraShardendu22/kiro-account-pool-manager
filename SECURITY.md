# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |

---

## Token & Account Isolation Security

`kiro-account-pool-manager` manages OAuth tokens with strict isolation:
- Each profile's OAuth token is stored in its own isolated SQLite database at `~/.local/share/kiro-profiles/<name>/kiro-cli/data.sqlite3`.
- Tokens are never logged to `stdout`, and `kiro-pool status` displays account names, emails, and cooldown timers only.
- Profile directories are created under the running user's home directory with POSIX user-only access.
- Temporary runtime directories are scoped to `/tmp/kiro-run-<name>-<UID>`.
- The repository `.gitignore` explicitly prevents checking in SQLite databases, lock files, or state data.

---

## Reporting a Vulnerability

If you discover a potential security vulnerability within this project, please **do not open a public issue**. Instead, report it privately via GitHub Security Advisories or contact the maintainer directly.
