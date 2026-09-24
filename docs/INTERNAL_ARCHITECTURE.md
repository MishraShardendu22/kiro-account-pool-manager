# Kiro CLI Linux Authentication & Internals

This document details the reverse-engineered internal architecture of Kiro CLI (`kiro-cli` and `kiro-cli-chat` v2.24.0 on Linux x86_64) and explains how `kiro-pool` achieves multi-account concurrency and quota multiplexing.

---

## 1. Architectural Lineage

Kiro CLI evolved from the **Fig** shell autocomplete engine and the **Amazon Q Developer CLI**. Under the hood, it is built in Rust with modular crates:
* `crates/fig_auth`: Handles OAuth, PKCE, token persistence, and token refreshes.
* `crates/fig_settings`: Handles configuration and SQLite data storage.
* `crates/chat-cli-v2`: Drives the conversational agent and cloud execution.
* `crates/fig_ipc`: Manages local IPC and desktop integration.

---

## 2. Authentication Storage Mechanism

### Dispelling the Keyring Myth on Linux
On macOS, Kiro CLI integrates with Apple Keychain; on Windows, it uses Windows Credential Manager. 
However, **on Linux, Kiro CLI does not use the system keyring (`libsecret`, GNOME Keyring, or KWallet) for Google social authentication**. 
* Dynamic library inspection (`ldd`) shows only links to `libc.so.6`, `libm.so.6`, and `libgcc_s.so.1`.
* Linux social authentication tokens are stored directly in a file-backed SQLite database.

### SQLite Database & Schema
* **File Location:** `$XDG_DATA_HOME/kiro-cli/data.sqlite3` (defaults to `~/.local/share/kiro-cli/data.sqlite3`).
* **Table:** `auth_kv`
  ```sql
  CREATE TABLE auth_kv (
      key TEXT PRIMARY KEY,
      value TEXT
  );
  ```
* **Credential Key:** `kirocli:social:token`
* **Credential Value:** Plaintext JSON payload containing:
  ```json
  {
    "access_token": "aoaAAAA...",
    "expires_at": "2026-09-24T15:45:00.000000000Z",
    "refresh_token": "aorAAAA...",
    "provider": "google",
    "profile_arn": "arn:aws:codewhisperer:us-east-1:..."
  }
  ```

---

## 3. Why `KIRO_HOME` Alone Fails for Multi-Account

Kiro's official documentation highlights `KIRO_HOME` for setting up multiple profiles.
However:
* **`KIRO_HOME` only controls `~/.kiro/`** (settings, custom agents, prompts, steering, and `mcp.json`).
* **`KIRO_HOME` does not control `data.sqlite3`**.

If you only set `KIRO_HOME=/path/to/profile_b`, Kiro still reads and writes to `~/.local/share/kiro-cli/data.sqlite3`. Both profiles end up overwriting the same `kirocli:social:token` entry.

### The Required Environment Triple

To fully isolate an account instance on Linux, three variables must be set:

| Variable | Target Path | Purpose |
| :--- | :--- | :--- |
| `XDG_DATA_HOME` | `~/.local/share/kiro-profiles/<name>` | Isolates `data.sqlite3` (tokens, history, session store) |
| `KIRO_HOME` | `~/.kiro-profiles/<name>` | Isolates `cli.json`, agents, steering, and MCP configs |
| `XDG_RUNTIME_DIR` | `/tmp/kiro-run-<name>-<UID>` | Isolates Unix domain sockets (`kirorun/t/*.sock`) and logs |

---

## 4. Token Refresh Lifecycle

1. When a command or prompt is dispatched, Kiro CLI checks the `expires_at` timestamp inside `auth_kv`.
2. If `expires_at` has elapsed, `crates/fig_auth/src/refresh_coordinator.rs` acquires a file lock on `$XDG_DATA_HOME/kiro-cli/.refresh.lock`.
3. It sends an HTTPS request to `https://prod.us-east-1.auth.desktop.kiro.dev/api/kiroauth/refresh` using the `refresh_token`.
4. It receives an updated `access_token` and `expires_at`, writes the updated JSON back to `auth_kv` in `data.sqlite3`, and releases `.refresh.lock`.

**Why per-profile isolation is safe:**
Because each profile has its own `data.sqlite3` and `.refresh.lock`, background token refreshes happen autonomously without lock contention or race conditions between different accounts.

---

## 5. Tenancy & Conversation Threading

A key question is whether a single interactive multi-turn session can alternate accounts on every turn.

* **Backend Tenancy Constraint:**
  On Kiro's cloud runtime (`https://runtime.us-east-1.kiro.dev`), each conversation thread (`conversation_id`) is cryptographically tied to the user's `profile_arn`. 
* If Account B attempts to inject a turn into an active `conversation_id` created by Account A, Kiro's cloud server rejects the request with an `AccessDenied / InvalidConversationId` error.
* **How `kiro-pool` Solves This:**
  * **Stateless / Task Prompts (`--no-interactive`):** Every prompt is dispatched as an independent task, rotating accounts on every single call.
  * **Interactive Chat Sessions:** `kiro-pool chat` launches a session under the next available account. When that session ends, the next launch uses the subsequent account in the pool.
  * **Shared Codebase Context:** Because Kiro operates directly on your local workspace and git files, Account B naturally builds on the code modified by Account A.

---

## 6. Disk Optimization via Symlink Templating

The standard Kiro CLI distribution installs large binaries into `$XDG_DATA_HOME/kiro-cli/`:
* `node`: ~124 MB
* `bun`: ~79 MB
* `run/chat-cli-*`: ~430 MB – 830 MB
* `kas/`: ~50 MB
* `tui.js`: ~13 MB

Total per profile without optimization: **~1 GB**.

`kiro-pool` symlinks these static executable runtimes from the primary installation into each profile's directory (`~/.local/share/kiro-profiles/<name>/kiro-cli/`). Only the stateful files (`data.sqlite3` and locks) are created locally.

As a result, each enrolled profile consumes **less than 50 KB** of disk space. Enrolling 50 accounts uses only ~2.5 MB of disk space instead of 50 GB.
