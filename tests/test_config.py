import os
import shutil
import unittest

import config
from config import ConfigError, list_tasks, load_task, save_task


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "..", "tasks_test")
        config.DEFAULT_CONFIG_DIR = self.test_dir

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_save_and_load(self):
        save_task("test_task", {"url": "http://example.com", "fields": []})
        task = load_task("test_task")
        self.assertEqual(task["url"], "http://example.com")

    def test_path_traversal_rejected(self):
        with self.assertRaises(ConfigError):
            save_task("../escape", {"url": "http://example.com"})
        with self.assertRaises(ConfigError):
            save_task("a\\b", {"url": "http://example.com"})

    def test_cookie_not_saved_by_default(self):
        save_task("no_cookie", {"cookie": "session=123", "save_cookie": False})
        task = load_task("no_cookie")
        self.assertEqual(task["cookie"], "")

    def test_cookie_encrypted_when_saved(self):
        save_task("with_cookie", {"cookie": "session=123", "save_cookie": True})
        task = load_task("with_cookie")
        self.assertEqual(task["cookie"], "session=123")


if __name__ == "__main__":
    unittest.main()
