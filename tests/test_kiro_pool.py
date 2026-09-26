import os
import sys
import json
import time
import shutil
import sqlite3
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
        self.mock_system_data = os.path.join(self.temp_dir, "system-kiro")
        self.mock_state_file = os.path.join(self.mock_base_dir, "pool_state.json")
        self.mock_lock_file = os.path.join(self.mock_base_dir, ".pool.lock")

        # Patch module global paths
        self.orig_base = kiro_pool.BASE_DIR
        self.orig_home = kiro_pool.KIRO_HOME_BASE
        self.orig_system_data = kiro_pool.SYSTEM_DATA_DIR
        self.orig_state = kiro_pool.STATE_FILE
        self.orig_lock = kiro_pool.LOCK_FILE

        kiro_pool.BASE_DIR = self.mock_base_dir
        kiro_pool.KIRO_HOME_BASE = self.mock_kiro_home
        kiro_pool.SYSTEM_DATA_DIR = self.mock_system_data
        kiro_pool.STATE_FILE = self.mock_state_file
        kiro_pool.LOCK_FILE = self.mock_lock_file

        os.makedirs(self.mock_base_dir, exist_ok=True)
        os.makedirs(self.mock_kiro_home, exist_ok=True)
        os.makedirs(self.mock_system_data, exist_ok=True)

    def _create_mock_auth_db(self, name, provider="google"):
        cli_dir = os.path.join(self.mock_base_dir, name, "kiro-cli")
        os.makedirs(cli_dir, exist_ok=True)
        db_path = os.path.join(cli_dir, "data.sqlite3")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
        payload = json.dumps({"access_token": "mock_token", "provider": provider})
        cur.execute("INSERT INTO auth_kv (key, value) VALUES ('kirocli:social:token', ?)", (payload,))
        conn.commit()
        conn.close()

    def tearDown(self):
        kiro_pool.BASE_DIR = self.orig_base
        kiro_pool.KIRO_HOME_BASE = self.orig_home
        kiro_pool.SYSTEM_DATA_DIR = self.orig_system_data
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
        self._create_mock_auth_db("acc1")
        self._create_mock_auth_db("acc2")
        self._create_mock_auth_db("acc3")
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
        self._create_mock_auth_db("acc1")
        self._create_mock_auth_db("acc2")
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

    def test_unauthenticated_profile_skipped(self):
        # acc1 is authed, acc2 is unauthenticated
        self._create_mock_auth_db("acc1")
        state = {
            "current_index": 0,
            "profiles": {
                "acc1": {"email": "1@g.com", "cooldown_until": 0, "usage_count": 0},
                "acc2": {"email": "2@g.com", "cooldown_until": 0, "usage_count": 0},
            }
        }
        kiro_pool.save_state(state)

        # Both attempts should return acc1 because acc2 has no SQLite token
        p1, _ = kiro_pool.get_next_available_profile()
        p2, _ = kiro_pool.get_next_available_profile()
        self.assertEqual(p1, "acc1")
        self.assertEqual(p2, "acc1")

    def test_prune_unauthenticated(self):
        self._create_mock_auth_db("acc_valid")
        state = {
            "current_index": 0,
            "profiles": {
                "acc_valid": {"email": "valid@g.com", "cooldown_until": 0, "usage_count": 0},
                "acc_unauthed": {"email": "unauthed@g.com", "cooldown_until": 0, "usage_count": 0},
            }
        }
        kiro_pool.save_state(state)

        unauthed_dir = os.path.join(self.mock_base_dir, "acc_unauthed")
        os.makedirs(unauthed_dir, exist_ok=True)

        kiro_pool.prune_unauthenticated()

        reloaded = kiro_pool.load_state()
        self.assertIn("acc_valid", reloaded["profiles"])
        self.assertNotIn("acc_unauthed", reloaded["profiles"])
        self.assertFalse(os.path.exists(unauthed_dir))

    def test_get_profile_auth_details(self):
        self._create_mock_auth_db("acc_google", provider="google")
        authed, prov = kiro_pool.get_profile_auth_details("acc_google")
        self.assertTrue(authed)
        self.assertEqual(prov, "google")

        # Non-existent profile
        authed_none, prov_none = kiro_pool.get_profile_auth_details("non_existent")
        self.assertFalse(authed_none)
        self.assertIsNone(prov_none)

    def test_check_db_auth_builder_id(self):
        cli_dir = os.path.join(self.mock_base_dir, "acc_builder", "kiro-cli")
        os.makedirs(cli_dir, exist_ok=True)
        db_path = os.path.join(cli_dir, "data.sqlite3")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
        payload = json.dumps({"accessToken": "mock_builder_token", "refreshToken": "mock_rf"})
        cur.execute("INSERT INTO auth_kv (key, value) VALUES ('kirocli:builder-id:token', ?)", (payload,))
        conn.commit()
        conn.close()

        authed, prov = kiro_pool.check_db_auth(db_path)
        self.assertTrue(authed)
        self.assertEqual(prov, "builder-id")

    @patch("subprocess.run")
    def test_import_current_account(self, mock_run):
        # Setup mock system db
        sys_db = os.path.join(self.mock_system_data, "data.sqlite3")
        conn = sqlite3.connect(sys_db)
        cur = conn.cursor()
        cur.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
        payload = json.dumps({"access_token": "valid_token", "provider": "google"})
        cur.execute("INSERT INTO auth_kv (key, value) VALUES ('kirocli:social:token', ?)", (payload,))
        conn.commit()
        conn.close()

        # Mock whoami proc output
        mock_proc = unittest.mock.MagicMock()
        mock_proc.stdout = "Logged in with Google\nEmail: imported@gmail.com\n"
        mock_run.return_value = mock_proc

        success = kiro_pool.import_current_account("imp_prof")
        self.assertTrue(success)

        # Verify state
        state = kiro_pool.load_state()
        self.assertIn("imp_prof", state["profiles"])
        self.assertEqual(state["profiles"]["imp_prof"]["email"], "imported@gmail.com")
        self.assertEqual(state["profiles"]["imp_prof"]["provider"], "google")

        # Verify target file exists
        target_db = os.path.join(self.mock_base_dir, "imp_prof", "kiro-cli", "data.sqlite3")
        self.assertTrue(os.path.exists(target_db))

    def test_switch_default_account(self):
        self._create_mock_auth_db("acc_to_switch", provider="github")
        state = {
            "current_index": 0,
            "profiles": {
                "acc_to_switch": {"email": "switched@gh.com", "cooldown_until": 0, "usage_count": 0}
            }
        }
        kiro_pool.save_state(state)

        success = kiro_pool.switch_default_account("acc_to_switch")
        self.assertTrue(success)

        # Verify system db has the credentials
        sys_db = os.path.join(self.mock_system_data, "data.sqlite3")
        self.assertTrue(os.path.exists(sys_db))
        authed, prov = kiro_pool.check_db_auth(sys_db)
        self.assertTrue(authed)
        self.assertEqual(prov, "github")

    def test_preferred_provider_selection(self):
        self._create_mock_auth_db("g_acc1", provider="google")
        self._create_mock_auth_db("g_acc2", provider="google")
        self._create_mock_auth_db("gh_acc1", provider="github")

        state = {
            "current_index": 0,
            "profiles": {
                "g_acc1": {"email": "g1@gmail.com", "cooldown_until": 0, "usage_count": 0},
                "g_acc2": {"email": "g2@gmail.com", "cooldown_until": 0, "usage_count": 0},
                "gh_acc1": {"email": "gh1@github.com", "cooldown_until": 0, "usage_count": 0},
            }
        }
        kiro_pool.save_state(state)

        # When requesting google, should return g_acc1
        chosen, _ = kiro_pool.get_next_available_profile(preferred_provider="google")
        self.assertEqual(chosen, "g_acc1")

        # Mark g_acc1 and g_acc2 in cooldown
        now = time.time()
        state["profiles"]["g_acc1"]["cooldown_until"] = now + 3600
        state["profiles"]["g_acc2"]["cooldown_until"] = now + 3600
        kiro_pool.save_state(state)

        # When requesting google but all google accounts are in cooldown, should fall back to github
        chosen_fb, _ = kiro_pool.get_next_available_profile(preferred_provider="google")
        self.assertEqual(chosen_fb, "gh_acc1")

    def test_cli_version_and_help(self):
        import subprocess
        res_ver = subprocess.run([SCRIPT_PATH, "--version"], capture_output=True, text=True)
        self.assertEqual(res_ver.returncode, 0)
        self.assertIn("kiro-pool 1.1.0", res_ver.stdout)

        res_help = subprocess.run([SCRIPT_PATH, "--help"], capture_output=True, text=True)
        self.assertEqual(res_help.returncode, 0)
        self.assertIn("Usage:", res_help.stdout)
        self.assertIn("kiro-pool add", res_help.stdout)
        self.assertIn("kiro-pool import", res_help.stdout)
        self.assertIn("kiro-pool switch", res_help.stdout)
        self.assertIn("kiro-pool prune", res_help.stdout)


if __name__ == "__main__":
    unittest.main()

