"""secure_storage 跨平台加密回归测试（L-1 修复）。"""

import base64
import os

import secure_storage


def _use_fernet(monkeypatch, tmp_path):
    # 模拟非 Windows 平台 + 独立密钥文件，不影响真实环境
    monkeypatch.setattr(secure_storage, "_KEY_PATH", str(tmp_path / "test.key"))
    monkeypatch.setattr(secure_storage, "_FERNET", None)
    monkeypatch.setattr(secure_storage, "_IS_WINDOWS", False)


def test_fernet_round_trip(monkeypatch, tmp_path):
    _use_fernet(monkeypatch, tmp_path)
    token = secure_storage.encrypt("secret-cookie-123")
    assert token.startswith("fernet:")
    assert "secret-cookie-123" not in token  # 不能是明文/base64 直存
    assert secure_storage.decrypt(token) == "secret-cookie-123"
    assert os.path.exists(secure_storage._KEY_PATH)


def test_fernet_reuses_key_from_disk(monkeypatch, tmp_path):
    _use_fernet(monkeypatch, tmp_path)
    token = secure_storage.encrypt("value-a")
    # 清空内存缓存后应从磁盘重读同一密钥，旧 token 仍可解密
    monkeypatch.setattr(secure_storage, "_FERNET", None)
    assert secure_storage.decrypt(token) == "value-a"


def test_b64_legacy_token_still_decrypts():
    # 向后兼容：旧版本生成的 b64: token 仍可解密
    token = "b64:" + base64.b64encode("legacy".encode("utf-8")).decode("ascii")
    assert secure_storage.decrypt(token) == "legacy"


def test_plain_value_passthrough():
    assert secure_storage.encrypt("") == ""
    assert secure_storage.decrypt("") == ""
    assert secure_storage.decrypt("plaintext") == "plaintext"
