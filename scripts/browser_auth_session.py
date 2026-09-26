#!/usr/bin/env python3
import os
import sys
import pty
import time
import json
import shutil
import sqlite3
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_DIR = os.path.dirname(SCRIPT_DIR)
BASE_DIR = os.path.expanduser("~/.local/share/kiro-profiles")
KIRO_HOME_BASE = os.path.expanduser("~/.kiro-profiles")
KIRO_BIN = shutil.which("kiro-cli") or os.path.expanduser("~/.local/bin/kiro-cli")

def main():
    if len(sys.argv) < 2:
        print("Usage: browser_auth_session.py <profile_name>")
        sys.exit(1)

    profile_name = sys.argv[1]
    profile_dir = os.path.join(BASE_DIR, profile_name, "kiro-cli")
    os.makedirs(profile_dir, exist_ok=True)
    os.makedirs(os.path.join(KIRO_HOME_BASE, profile_name), exist_ok=True)

    # Wipe existing data.sqlite3 if unauthenticated
    db_path = os.path.join(profile_dir, "data.sqlite3")
    if os.path.exists(db_path):
        os.remove(db_path)

    # Symlink binaries
    system_data_dir = os.path.expanduser("~/.local/share/kiro-cli")
    for item in ["node", "bun", "tui.js", "run", "kas"]:
        src = os.path.join(system_data_dir, item)
        dst = os.path.join(profile_dir, item)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                os.symlink(src, dst)
            except OSError:
                pass

    # Setup capture script for xdg-open
    fake_dir = f"/tmp/fake_bin_{profile_name}"
    os.makedirs(fake_dir, exist_ok=True)
    capture_script = os.path.join(fake_dir, "xdg-open")
    url_file = f"/tmp/kiro_oauth_url_{profile_name}.txt"
    status_file = f"/tmp/kiro_oauth_status_{profile_name}.json"

    if os.path.exists(url_file):
        os.remove(url_file)

    with open(capture_script, "w") as f:
        f.write(f"""#!/bin/sh
echo "$1" > "{url_file}"
exit 0
""")
    os.chmod(capture_script, 0o755)

    env = os.environ.copy()
    env["PATH"] = fake_dir + ":" + env["PATH"]
    env["BROWSER"] = capture_script
    env["XDG_DATA_HOME"] = os.path.join(BASE_DIR, profile_name)
    env["KIRO_HOME"] = os.path.join(KIRO_HOME_BASE, profile_name)
    env["XDG_RUNTIME_DIR"] = f"/tmp/kiro-run-{profile_name}-{os.getuid()}"
    os.makedirs(env["XDG_RUNTIME_DIR"], exist_ok=True)

    print(f"[bridge] Starting kiro-cli login for profile '{profile_name}'...")
    master, slave = pty.openpty()
    proc = subprocess.Popen([KIRO_BIN, "login"], stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
    os.close(slave)

    # Wait up to 10 seconds for URL capture
    captured_url = None
    start_t = time.time()
    while time.time() - start_t < 10:
        if os.path.exists(url_file):
            try:
                captured_url = open(url_file).read().strip()
                if captured_url.startswith("http"):
                    break
            except Exception:
                pass
        time.sleep(0.2)

    if not captured_url:
        print("[bridge ERROR] Failed to capture OAuth URL within 10s.")
        proc.kill()
        sys.exit(1)

    print(f"[bridge] Captured OAuth URL: {captured_url}")
    with open(status_file, "w") as f:
        json.dump({"status": "waiting", "url": captured_url, "pid": proc.pid}, f)

    # Wait for the login to complete (redirect to localhost:3128 writes to db_path)
    print(f"[bridge] Waiting up to 90s for browser authentication callback...")
    start_wait = time.time()
    authed = False
    while time.time() - start_wait < 90:
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path, timeout=0.5)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auth_kv'")
                if cur.fetchone():
                    cur.execute("SELECT value FROM auth_kv WHERE key = 'kirocli:social:token'")
                    row = cur.fetchone()
                    if row and row[0]:
                        data = json.loads(row[0])
                        if data.get("access_token") or data.get("refresh_token"):
                            authed = True
                            conn.close()
                            break
                conn.close()
            except Exception:
                pass
        time.sleep(1)

    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    if not authed:
        print("[bridge ERROR] Timed out waiting for OAuth callback or token save.")
        with open(status_file, "w") as f:
            json.dump({"status": "timeout"}, f)
        sys.exit(1)

    print(f"[bridge] Detected authenticated token in {db_path}!")

    # Query whoami in target profile env
    whoami_proc = subprocess.run([KIRO_BIN, "whoami"], env=env, capture_output=True, text=True)
    print(f"[bridge] whoami output:\n{whoami_proc.stdout}")

    email = "Unknown"
    for line in whoami_proc.stdout.splitlines():
        if "Email:" in line:
            email = line.split("Email:")[1].strip()

    # Determine provider from db
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT value FROM auth_kv WHERE key = 'kirocli:social:token'")
    row = cur.fetchone()
    conn.close()

    provider = "unknown"
    if row and row[0]:
        data = json.loads(row[0])
        provider = data.get("provider", "unknown")

    # Update pool_state.json
    state_file = os.path.join(BASE_DIR, "pool_state.json")
    try:
        with open(state_file, "r") as f:
            state = json.load(f)
    except Exception:
        state = {"current_index": 0, "profiles": {}}

    state["profiles"][profile_name] = {
        "email": email,
        "provider": provider,
        "created_at": time.time(),
        "cooldown_until": 0,
        "usage_count": 0
    }

    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

    print(f"[bridge SUCCESS] Profile '{profile_name}' enrolled! ({provider}: {email})")
    with open(status_file, "w") as f:
        json.dump({"status": "success", "profile": profile_name, "email": email, "provider": provider}, f)

if __name__ == "__main__":
    main()
