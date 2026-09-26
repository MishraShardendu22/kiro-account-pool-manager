#!/usr/bin/env python3
"""
Playwright-based Headless/Automated Authentication Helper for kiro-pool.

Automates the OAuth login flow for Kiro CLI profiles using Playwright.
Supports Google and GitHub authentication in both headless and headed modes.

Prerequisites:
  pip install playwright
  playwright install chromium
"""

import os
import sys
import json
import time
import argparse
import subprocess

BASE_DIR = os.getenv("KIRO_POOL_BASE_DIR") or os.path.expanduser("~/.local/share/kiro-profiles")
KIRO_HOME_BASE = os.getenv("KIRO_POOL_HOME_BASE") or os.path.expanduser("~/.kiro-profiles")
KIRO_BIN = os.getenv("KIRO_BIN") or os.path.expanduser("~/.local/bin/kiro-cli")

def check_playwright():
    try:
        import playwright
        return True
    except ImportError:
        return False

def get_env_for_profile(name):
    env = os.environ.copy()
    data_dir = os.path.join(BASE_DIR, name)
    home_dir = os.path.join(KIRO_HOME_BASE, name)
    run_dir = f"/tmp/kiro-run-{name}-{os.getuid()}"
    os.makedirs(run_dir, exist_ok=True)
    env["XDG_DATA_HOME"] = data_dir
    env["KIRO_HOME"] = home_dir
    env["XDG_RUNTIME_DIR"] = run_dir
    return env

def authenticate_profile_playwright(profile_name, provider="google", email=None, password=None, headless=True):
    if not check_playwright():
        print("\033[1;31m[ERROR]\033[0m Playwright is not installed in the current Python environment.")
        print("To install Playwright, run:")
        print("  python3 -m pip install playwright")
        print("  python3 -m playwright install chromium")
        return False

    from playwright.sync_api import sync_playwright

    print(f"\033[1;34m[auto-auth]\033[0m Preparing automated authentication for profile '{profile_name}' ({provider})...")
    env = get_env_for_profile(profile_name)

    # Launch kiro login in background
    cmd = [KIRO_BIN, "login", "--use-device-flow"]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Monitor output for device code and verification URL
    verification_url = None
    user_code = None

    start_time = time.time()
    while time.time() - start_time < 30:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue

        line_str = line.strip()
        print(f"  [kiro-cli] {line_str}")

        if "http" in line_str and not verification_url:
            for word in line_str.split():
                if word.startswith("http"):
                    verification_url = word
        if "code" in line_str.lower() or "-" in line_str:
            parts = line_str.split(":")
            if len(parts) > 1 and len(parts[1].strip()) >= 8:
                user_code = parts[1].strip()

        if verification_url:
            break

    if not verification_url:
        print("\033[1;31m[ERROR]\033[0m Failed to capture OAuth verification URL from kiro-cli.")
        proc.kill()
        return False

    print(f"\033[1;32m[auto-auth]\033[0m Captured verification URL: {verification_url}")
    if user_code:
        print(f"\033[1;32m[auto-auth]\033[0m Captured user code: {user_code}")

    # Launch Playwright browser
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        print(f"\033[1;34m[auto-auth]\033[0m Navigating to verification page...")
        page.goto(verification_url)

        # If user code input field exists, fill it in
        if user_code:
            try:
                code_input = page.wait_for_selector("input[name='user_code'], input[type='text']", timeout=5000)
                if code_input:
                    code_input.fill(user_code)
                    page.keyboard.press("Enter")
            except Exception:
                pass

        # Handle login credentials if provided
        if email:
            try:
                email_input = page.wait_for_selector("input[type='email'], input[name='login']", timeout=5000)
                if email_input:
                    email_input.fill(email)
                    page.keyboard.press("Enter")
                    time.sleep(2)
            except Exception:
                pass

        if password:
            try:
                pass_input = page.wait_for_selector("input[type='password']", timeout=5000)
                if pass_input:
                    pass_input.fill(password)
                    page.keyboard.press("Enter")
                    time.sleep(2)
            except Exception:
                pass

        # Wait for approval/consent button
        try:
            approve_btn = page.wait_for_selector("button:has-text('Allow'), button:has-text('Authorize'), button:has-text('Confirm')", timeout=8000)
            if approve_btn:
                approve_btn.click()
                print("\033[1;32m[auto-auth]\033[0m Clicked authorization consent button.")
        except Exception:
            pass

        time.sleep(5)
        browser.close()

    # Wait for kiro-cli to complete
    proc.wait(timeout=15)
    if proc.returncode == 0:
        print(f"\033[1;32m[auto-auth]\033[0m Profile '{profile_name}' successfully authenticated!")
        return True
    else:
        print(f"\033[1;33m[auto-auth]\033[0m Verification submitted. Check 'kiro-pool status' to verify.")
        return False

def main():
    parser = argparse.ArgumentParser(description="Automated Headless Kiro Authentication via Playwright")
    parser.add_argument("profile", help="Profile name to authenticate (e.g. google03)")
    parser.add_argument("--provider", choices=["google", "github"], default="google", help="OAuth provider")
    parser.add_argument("--email", "-e", help="Account email address")
    parser.add_argument("--password", "-p", help="Account password (optional, prefer interactive session)")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible mode (default: headless)")

    args = parser.parse_args()
    success = authenticate_profile_playwright(
        profile_name=args.profile,
        provider=args.provider,
        email=args.email,
        password=args.password,
        headless=not args.headed
    )
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
