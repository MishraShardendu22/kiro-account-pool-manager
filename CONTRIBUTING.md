# Contributing to `kiro-account-pool-manager`

Thank you for your interest in contributing to **`kiro-account-pool-manager`**! We welcome bug reports, feature suggestions, documentation enhancements, and pull requests.

---

## Code of Conduct

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md) in all community interactions.

---

## Development Setup

### Prerequisites

- **Python**: v3.9 or later (uses Python standard library only; zero pip dependencies)
- **Kiro CLI**: installed at `~/.local/bin/kiro-cli` or in `PATH`
- **Linux x86_64** / POSIX environment

### Setting Up Locally

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/MishraShardendu22/kiro-account-pool-manager.git
   cd kiro-account-pool-manager
   ```

2. **Run tests**:
   ```bash
   python3 -m unittest discover -s tests -v
   ```

3. **Install locally**:
   ```bash
   ./install.sh
   ```

---

## Codebase Layout

```
├── bin/
│   └── kiro-pool          # Standalone executable Python orchestrator
├── docs/
│   └── INTERNAL_ARCHITECTURE.md # Reverse-engineered deep dive into Kiro CLI SQLite & OAuth
├── tests/
│   └── test_kiro_pool.py  # Automated unit and CLI integration tests
├── install.sh             # User-space symlink / installer
├── uninstall.sh           # Cleanup uninstaller
└── README.md              # Documentation & usage guide
```

---

## Submitting Pull Requests

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. Commit your changes with semantic commit messages (e.g. `feat: ...`, `fix: ...`, `docs: ...`).
3. Ensure all tests pass:
   ```bash
   python3 -m unittest discover -s tests -v
   ```
4. Push your branch to GitHub and open a Pull Request.
