# Kiro Account Pool Manager (`kiro-pool`)

<div align="center">

### Multi-Account Pooling, Quota Multiplexing & Auto-Failover for Kiro CLI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-%3E%3D3.9-blue.svg)](https://python.org/)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20POSIX-lightgrey.svg)](https://www.kernel.org/)
[![CI](https://github.com/MishraShardendu22/kiro-account-pool-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/MishraShardendu22/kiro-account-pool-manager/actions)
[![GitHub Stars](https://img.shields.io/github/stars/MishraShardendu22/kiro-account-pool-manager?style=social)](https://github.com/MishraShardendu22/kiro-account-pool-manager)

<p align="center">
  <b>Scale beyond single-account limits by pooling an arbitrary number ($N$) of Google accounts together under one Linux user. Rotate prompts round-robin across accounts to multiply your available AI quotas, and automatically fail over to healthy accounts when rate limits hit.</b>
</p>

</div>

---

## Key Features

* **Unlimited Accounts ($N$):** Connect 2, 5, 10, or 50+ Google accounts with independent session tokens.
* **Ultra-Lightweight (~50 KB / account):** Uses symlink templating to share heavy engine runtimes (`node`, `bun`, `tui.js`, `run/`). 50 accounts use ~2.5 MB instead of 50 GB.
* **Automatic Quota Failover:** Detects HTTP `429`, `ThrottlingError`, or quota exhaustion and immediately retries the prompt with the next available account.
* **Intelligent Cooldown:** Automatically benches throttled accounts for 60 minutes and resumes them once their rate limit resets.
* **Pool Health Dashboard:** View all enrolled Google accounts, active status, cooldown timers, and request counts via `kiro-pool status`.
* **Zero Impact on Default CLI:** Your official `kiro-cli` installation and default primary account remain 100% untouched.

---

## How It Works

Kiro CLI stores authentication tokens in an unencrypted SQLite table at `$XDG_DATA_HOME/kiro-cli/data.sqlite3`.

`kiro-pool` wraps your installed `kiro-cli` binary, dynamically injecting isolated environment variables (`XDG_DATA_HOME`, `KIRO_HOME`, `XDG_RUNTIME_DIR`) per command:

```mermaid
flowchart TD
    A[You run: kiro-pool chat --no-interactive 'Prompt'] --> B[kiro-pool Orchestrator]
    B --> C[1. Read state & pick next healthy account]
    B --> D[2. Bench throttled accounts in cooldown window]
    B --> E[3. Inject isolated XDG & KIRO environment triple]
    E --> F[Execute official kiro-cli binary]
    F --> G{Execution Result}
    G -- Success --> H[Return response to stdout]
    G -- Throttled 429 / RateLimit --> I[Mark account in 60m cooldown]
    I --> J[Auto-retry with next available account]
    J --> F
```

*(See [docs/INTERNAL_ARCHITECTURE.md](docs/INTERNAL_ARCHITECTURE.md) for full reverse-engineered details.)*

---

## Quickstart

### 1. Installation

Clone and run the installer:

```bash
git clone https://github.com/MishraShardendu22/kiro-account-pool-manager.git
cd kiro-account-pool-manager
./install.sh
```

Ensure `~/.local/bin` is in your `PATH` (default in Ubuntu and most distributions).

### 2. Enroll Accounts

Enroll as many Google accounts as you want:

```bash
kiro-pool add acc1
kiro-pool add acc2
kiro-pool add acc3
```

> [!IMPORTANT]
> **Avoid Google Cookie Collision:**
> When adding Account 2 or higher:
> 1. In the terminal prompt, select **Use with Google**.
> 2. Copy the authorization URL and open it in an **Incognito / Private window** (or separate browser profile) signed into that specific Google account.

### 3. Check Pool Status & Prune Unhealthy Accounts

```bash
# View active accounts, OAuth provider, and health
kiro-pool status

# Clean up / remove any accounts that lost authentication or were logged out
kiro-pool prune
```

**Example Output:**
```text
Kiro Multi-Account Pool Status
============================================================================
Profile        Email                            Auth State           Used  
----------------------------------------------------------------------------
acc1           work.dev@gmail.com               Ready (Google)     16    
acc2           personal.code@gmail.com          Ready (Google)     14    
acc3           experimental@gmail.com           Cooldown (45m)     8     
acc4           old.dev@gmail.com                Login Required     2     
============================================================================
Tip: 1 account(s) require re-login. Run kiro-pool prune to remove them from rotation.
```

---

## Unattended & Headless Safety

`kiro-pool` is designed for autonomous agents, CI/CD runners, and background subtasks:
1. **Pre-flight Auth Filtering**: Before any prompt is executed, `kiro-pool` inspects the profile's SQLite session. If an account is logged out or unauthenticated, it is **automatically skipped**—it will never block your terminal.
2. **Headless Safety Guard**: If an account's token is revoked mid-flight and `kiro-cli` attempts to launch an interactive browser callback (`localhost:3128`), `kiro-pool` catches it immediately, skips the expired profile, and transparently retries on the next healthy account.
3. **Automated Playwright Login**: For headless server environments, `scripts/auto_auth_playwright.py` is included to automate device flow logins via Chromium.

---

## Usage

### A. Non-Interactive Task Prompts (Automatic Rotation)

Every prompt automatically alternates across your account pool:

```bash
# Prompt 1 -> Uses acc1
kiro-pool chat --v3 --model claude-haiku-4.5 --no-interactive "Scaffold a FastAPI application"

# Prompt 2 -> Uses acc2
kiro-pool chat --v3 --model claude-haiku-4.5 --no-interactive "Write pytest integration tests"

# Prompt 3 -> Uses acc1 (or acc3)
kiro-pool chat --v3 --model claude-haiku-4.5 --no-interactive "Generate Dockerfile and compose file"
```

If an account hits a rate limit or requires authentication, `kiro-pool` automatically benches that account and reroutes the prompt to a backup account without failing.

### B. Interactive Chat Session (TUI)

```bash
kiro-pool chat
```
* Launches an interactive terminal UI session using the **next available account**.
* That specific multi-turn conversation will stay on that account until you exit (`Ctrl+C` or `/quit`).
* Running `kiro-pool chat` again picks the next account in rotation.

### C. Convenient Shell Alias

Add this alias to your `~/.bashrc` or `~/.zshrc`:
```bash
alias kiro="kiro-pool"
```

Now you can run:
```bash
kiro status
kiro chat --no-interactive "Review PR #42"
```

---

## Command Reference

| Command | Description |
| :--- | :--- |
| `kiro-pool add <name>` | Enroll a new Google/GitHub account into the pool |
| `kiro-pool remove <name> [name2...]` | Remove account(s) from the pool (aliases: `rm`, `delete`, `del`) |
| `kiro-pool prune` | Remove unauthenticated or expired accounts from the pool (alias: `clean-unauthed`) |
| `kiro-pool status` | View account health, auth state, cooldowns, and usage (aliases: `list`, `ls`) |
| `kiro-pool reset-cooldown` | Manually clear cooldown timers for all accounts |
| `kiro-pool run <args...>` | Run any Kiro CLI command rotated through healthy accounts |
| `kiro-pool <args...>` | Shorthand for `run` (e.g., `kiro-pool whoami`) |
| `kiro-pool --version` | Display current version number |
| `kiro-pool --help` | Show command usage and options |

---

## Practical Tradeoffs & Honest Evaluation

| Dimension | Real-World Assessment |
| :--- | :--- |
| **Best For** | Background code generation, PR review delegation, test scaffolding, bulk script generation. |
| **Not Suited For** | Real-time interactive keystroke completions (due to 5–8s daemon cold-start latency). |
| **Strengths** | Free frontier model compute (Claude 3.5 Sonnet / Haiku 4.5, Qwen Coder), multiplied quotas, zero card required. |
| **Limitations** | Session token expiration, device OAuth management overhead, background daemon spin-up time. |

### Where `kiro-pool` Genuinely Shines
1. **Free Frontier Model Compute**: Access AWS-backed models (Claude 3.5 Sonnet, Claude Haiku 4.5, Qwen Coder) using standard Google and GitHub accounts without paying for OpenAI or Anthropic API subscriptions.
2. **Quota Multiplication**: By pooling 3–10 accounts, you multiply daily usage allowances and avoid single-account rate limit blocks.
3. **Disposable Background Sub-agents**: Perfect for offloading heavy, secondary tasks (e.g., analyzing large git diffs during PR reviews or generating boilerplate unit test suites) without consuming your primary AI coding assistant's context window or paid token budget.

### Practical Friction Points to Know
1. **Daemon Cold-Start Latency**: The official `kiro-cli` engine spawns background runtimes (`kas`, `node`, `bun`) and runs local SQLite synchronization. This introduces an intrinsic **5–8 second startup latency** before output streams. It is best suited for batch prompts and background delegation rather than instant sub-second queries.
2. **Session Maintenance Overhead**: Google and GitHub OAuth device tokens periodically expire. While `kiro-pool` protects headless automation by auto-skipping expired profiles (and provides `kiro-pool prune`), maintaining a large pool of 10+ accounts requires occasional re-enrollment (which can be automated using `scripts/auto_auth_playwright.py`).
3. **Execution Model**: `kiro-pool` acts as a prompt runner and tool execution pipeline. It is not an autonomous IDE agent with native workspace tree indexing.

---

## Running Tests

The test suite runs using Python's native `unittest` framework (zero third-party dependencies):

```bash
python3 -m unittest discover -s tests -v
```

---

## Frequently Asked Questions

#### Does this modify my default `kiro-cli`?
No. Standard `kiro-cli` continues to use your primary default account and configuration. `kiro-pool` operates strictly in isolated profile directories (`~/.local/share/kiro-profiles/`).

#### Can one open chat window switch accounts mid-conversation?
No. Kiro's cloud runtime anchors conversation threads to the user's Profile ARN. Alternating accounts per message within a single unbroken conversation thread causes backend rejection (`InvalidConversationId`). Rotation happens **per prompt** or **per session**.

#### How do tokens refresh?
Kiro CLI automatically refreshes expired tokens in the background using each profile's independent `.refresh.lock` and SQLite database. No manual re-login is required.

---

## Contributing

Contributions are warmly welcomed! Please read our [Contributing Guide](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md).

---

## License

MIT License. See [LICENSE](LICENSE) for details.
