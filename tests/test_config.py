import os
import shutil
import unittest

import config


def test_proxy_pool_round_trip_encrypted(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_CONFIG_DIR", str(tmp_path))
    values = ["http://u:p@9.9.9.9:80", "http://a:b@8.8.8.8:3128"]
    config.save_task("proxy-task", {"proxy_pool": values})
    assert all(value not in (tmp_path / "proxy-task.json").read_text(encoding="utf-8") for value in values)
    assert config.load_task("proxy-task")["proxy_pool"] == values


def test_api_config_credentials_encrypted(monkeypatch, tmp_path):
    # M-2 回归测试：api_config.headers/body 中的凭证必须加密落盘，且能正确还原
    monkeypatch.setattr(config, "DEFAULT_CONFIG_DIR", str(tmp_path))
    task = {
        "api_config": {
            "body_type": "json",
            "headers": {"Authorization": "Bearer secret-token-123", "X-API-Key": "key-abc"},
            "body": {"token": "secret-in-body", "nested": {"password": "p@ss"}},
            "pagination_type": "param",
            "pagination_param": "page",
        }
    }
    config.save_task("api-task", task)
    raw = (tmp_path / "api-task.json").read_text(encoding="utf-8")
    for secret in ("secret-token-123", "key-abc", "secret-in-body", "p@ss"):
        assert secret not in raw
    # 非敏感的分页配置保持明文，便于排查
    assert "pagination_param" in raw and '"page"' in raw
    loaded = config.load_task("api-task")["api_config"]
    assert loaded["headers"]["Authorization"] == "Bearer secret-token-123"
    assert loaded["headers"]["X-API-Key"] == "key-abc"
    assert loaded["body"]["token"] == "secret-in-body"
    assert loaded["body"]["nested"]["password"] == "p@ss"
    assert loaded["pagination_param"] == "page"


def test_api_config_plaintext_task_still_loads(monkeypatch, tmp_path):
    # 向后兼容：旧版任务 JSON 中 headers/body 为明文时仍可正常加载
    monkeypatch.setattr(config, "DEFAULT_CONFIG_DIR", str(tmp_path))
    (tmp_path / "old-task.json").write_text(
        '{"api_config": {"headers": {"Authorization": "Bearer legacy"}, "body": {}}}',
        encoding="utf-8",
    )
    loaded = config.load_task("old-task")["api_config"]
    assert loaded["headers"]["Authorization"] == "Bearer legacy"


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
