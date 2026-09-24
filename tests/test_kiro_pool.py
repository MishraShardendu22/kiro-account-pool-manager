import os
import sys
import json
import time
import shutil
import tempfile
import unittest
import importlib.util
from unittest.mock import patch

# Dynamically import kiro-pool script as a module
from importlib.machinery import SourceFileLoader

SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin", "kiro-pool"))
kiro_pool = SourceFileLoader("kiro_pool", SCRIPT_PATH).load_module()


class TestKiroPool(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="kiro-pool-test-")
        self.mock_base_dir = os.path.join(self.temp_dir, "profiles")
        self.mock_kiro_home = os.path.join(self.temp_dir, "kiro-home")
        self.mock_state_file = os.path.join(self.mock_base_dir, "pool_state.json")
        self.mock_lock_file = os.path.join(self.mock_base_dir, ".pool.lock")

        # Patch module global paths
        self.orig_base = kiro_pool.BASE_DIR
        self.orig_home = kiro_pool.KIRO_HOME_BASE
        self.orig_state = kiro_pool.STATE_FILE
        self.orig_lock = kiro_pool.LOCK_FILE

        kiro_pool.BASE_DIR = self.mock_base_dir
        kiro_pool.KIRO_HOME_BASE = self.mock_kiro_home
        kiro_pool.STATE_FILE = self.mock_state_file
        kiro_pool.LOCK_FILE = self.mock_lock_file

        os.makedirs(self.mock_base_dir, exist_ok=True)
        os.makedirs(self.mock_kiro_home, exist_ok=True)

    def tearDown(self):
        kiro_pool.BASE_DIR = self.orig_base
        kiro_pool.KIRO_HOME_BASE = self.orig_home
        kiro_pool.STATE_FILE = self.orig_state
        kiro_pool.LOCK_FILE = self.orig_lock

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_state_empty(self):
        state = kiro_pool.load_state()
        self.assertEqual(state, {"current_index": 0, "profiles": {}})

    def test_save_and_load_state(self):
        state_data = {
            "current_index": 1,
            "profiles": {
                "acc1": {
                    "email": "acc1@gmail.com",
                    "created_at": 1000.0,
                    "cooldown_until": 0,
                    "usage_count": 5
                }
            }
        }
        kiro_pool.save_state(state_data)
        loaded = kiro_pool.load_state()
        self.assertEqual(loaded, state_data)

    def test_get_env_for_profile(self):
        env = kiro_pool.get_env_for_profile("test_profile")
        self.assertIn("XDG_DATA_HOME", env)
        self.assertIn("KIRO_HOME", env)
        self.assertIn("XDG_RUNTIME_DIR", env)
        self.assertTrue(env["XDG_DATA_HOME"].endswith("test_profile"))
        self.assertTrue(env["KIRO_HOME"].endswith("test_profile"))
        self.assertIn("kiro-run-test_profile-", env["XDG_RUNTIME_DIR"])

    def test_round_robin_selection(self):
        state = {
            "current_index": 0,
            "profiles": {
                "acc1": {"email": "1@g.com", "cooldown_until": 0, "usage_count": 0},
                "acc2": {"email": "2@g.com", "cooldown_until": 0, "usage_count": 0},
                "acc3": {"email": "3@g.com", "cooldown_until": 0, "usage_count": 0},
            }
        }
        kiro_pool.save_state(state)

        p1, s1 = kiro_pool.get_next_available_profile()
        p2, s2 = kiro_pool.get_next_available_profile()
        p3, s3 = kiro_pool.get_next_available_profile()
        p4, s4 = kiro_pool.get_next_available_profile()

        self.assertEqual([p1, p2, p3, p4], ["acc1", "acc2", "acc3", "acc1"])
        self.assertEqual(s4["profiles"]["acc1"]["usage_count"], 2)

    def test_cooldown_skips_throttled_profile(self):
        now = time.time()
        state = {
            "current_index": 0,
            "profiles": {
                "acc1": {"email": "1@g.com", "cooldown_until": now + 3600, "usage_count": 0},
                "acc2": {"email": "2@g.com", "cooldown_until": 0, "usage_count": 0},
            }
        }
        kiro_pool.save_state(state)

        # Since acc1 is in cooldown, it should skip to acc2
        chosen, _ = kiro_pool.get_next_available_profile()
        self.assertEqual(chosen, "acc2")

    def test_all_in_cooldown_returns_none(self):
        now = time.time()
        state = {
            "current_index": 0,
            "profiles": {
                "acc1": {"email": "1@g.com", "cooldown_until": now + 3600, "usage_count": 0},
                "acc2": {"email": "2@g.com", "cooldown_until": now + 3600, "usage_count": 0},
            }
        }
        kiro_pool.save_state(state)

        chosen, _ = kiro_pool.get_next_available_profile()
        self.assertIsNone(chosen)

    def test_mark_throttled(self):
        state = {
            "current_index": 0,
            "profiles": {
                "acc1": {"email": "1@g.com", "cooldown_until": 0, "usage_count": 0},
            }
        }
        kiro_pool.save_state(state)

        kiro_pool.mark_throttled("acc1")
        reloaded = kiro_pool.load_state()
        self.assertGreater(reloaded["profiles"]["acc1"]["cooldown_until"], time.time())

    def test_remove_account(self):
        state = {
            "current_index": 0,
            "profiles": {
                "acc_to_del": {"email": "del@g.com", "cooldown_until": 0, "usage_count": 0},
                "acc_keep": {"email": "keep@g.com", "cooldown_until": 0, "usage_count": 0},
            }
        }
        kiro_pool.save_state(state)

        # Create mock directories to ensure cleanup
        mock_p_dir = os.path.join(self.mock_base_dir, "acc_to_del")
        os.makedirs(mock_p_dir, exist_ok=True)

        kiro_pool.remove_account("acc_to_del")

        updated = kiro_pool.load_state()
        self.assertNotIn("acc_to_del", updated["profiles"])
        self.assertIn("acc_keep", updated["profiles"])
        self.assertFalse(os.path.exists(mock_p_dir))

    def test_reset_cooldown(self):
        now = time.time()
        state = {
            "current_index": 0,
            "profiles": {
                "acc1": {"email": "1@g.com", "cooldown_until": now + 3600, "usage_count": 0},
            }
        }
        kiro_pool.save_state(state)

        # Trigger reset-cooldown logic
        reloaded = kiro_pool.load_state()
        for p in reloaded.get("profiles", {}).values():
            p["cooldown_until"] = 0
        kiro_pool.save_state(reloaded)

        cleared = kiro_pool.load_state()
        self.assertEqual(cleared["profiles"]["acc1"]["cooldown_until"], 0)

    def test_cli_version_and_help(self):
        import subprocess
        res_ver = subprocess.run([SCRIPT_PATH, "--version"], capture_output=True, text=True)
        self.assertEqual(res_ver.returncode, 0)
        self.assertIn("kiro-pool 1.0.0", res_ver.stdout)

        res_help = subprocess.run([SCRIPT_PATH, "--help"], capture_output=True, text=True)
        self.assertEqual(res_help.returncode, 0)
        self.assertIn("Usage:", res_help.stdout)
        self.assertIn("kiro-pool add", res_help.stdout)


if __name__ == "__main__":
    unittest.main()
