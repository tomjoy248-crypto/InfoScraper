"""敏感数据安全存储。

Windows 下使用 DPAPI（Data Protection API）加密当前用户可解密的数据；
其他平台使用 cryptography 的 Fernet 对称加密，密钥保存在用户主目录下
权限 0600 的密钥文件中（L-1 修复：不再使用 base64 明文编码）。
仅在 cryptography 不可用时才降级为 base64 编码并给出警告。
"""

import base64
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform.startswith("win")

# 非 Windows 平台的密钥文件（0600 权限，仅当前用户可读）
_KEY_PATH = os.path.join(os.path.expanduser("~"), ".info_scraper.key")
_FERNET = None


def _load_fernet():
    """惰性加载/创建 Fernet 实例；密钥不存在时生成并落盘（0600）。"""
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    from cryptography.fernet import Fernet

    try:
        with open(_KEY_PATH, "rb") as f:
            key = f.read().strip()
        if key:
            _FERNET = Fernet(key)
            return _FERNET
    except OSError:
        pass
    key = Fernet.generate_key()
    # O_CREAT|O_TRUNC + 0600，避免密钥文件被其他用户读取
    fd = os.open(_KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    os.chmod(_KEY_PATH, 0o600)
    _FERNET = Fernet(key)
    return _FERNET


def encrypt(value: Optional[str]) -> Optional[str]:
    """加密字符串，返回 base64 编码的 token；输入为空则直接返回空。"""
    if not value:
        return value
    raw = value.encode("utf-8")
    if not _IS_WINDOWS:
        # L-1 修复：非 Windows 平台使用 Fernet 真加密；
        # 仅在 cryptography 不可用时降级为 base64 并警告
        try:
            return "fernet:" + _load_fernet().encrypt(raw).decode("ascii")
        except ImportError:
            logger.warning("cryptography 未安装，敏感数据仅做 base64 编码，未加密")
            return "b64:" + base64.b64encode(raw).decode("ascii")

    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", wintypes.LPBYTE)]

    crypt32 = ctypes.windll.crypt32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPCVOID,
        wintypes.LPCVOID,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL

    in_blob = DATA_BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), wintypes.LPBYTE))
    out_blob = DATA_BLOB()

    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "InfoScraperSensitive",
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("DPAPI 加密失败")

    encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return "dpapi:" + base64.b64encode(encrypted).decode("ascii")


def decrypt(token: Optional[str]) -> Optional[str]:
    """解密 token；输入为空或不是加密 token 则原样返回。"""
    if not token:
        return token
    if token.startswith("fernet:"):
        # L-1 修复：Fernet 加密 token（非 Windows 平台）
        try:
            plain = _load_fernet().decrypt(token[7:].encode("ascii"))
        except ImportError as exc:
            raise OSError("无法解密：cryptography 未安装") from exc
        except Exception as exc:
            raise OSError("Fernet 解密失败：密钥文件可能已变更或数据损坏") from exc
        return plain.decode("utf-8")
    if token.startswith("dpapi:"):
        if not _IS_WINDOWS:
            raise OSError("无法解密 DPAPI 数据：当前不是 Windows 平台")

        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", wintypes.LPBYTE)]

        crypt32 = ctypes.windll.crypt32
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(DATA_BLOB),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(DATA_BLOB),
            wintypes.LPCVOID,
            wintypes.LPCVOID,
            wintypes.DWORD,
            ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL

        encrypted = base64.b64decode(token[6:].encode("ascii"))
        in_blob = DATA_BLOB(
            len(encrypted),
            ctypes.cast(ctypes.create_string_buffer(encrypted), wintypes.LPBYTE),
        )
        out_blob = DATA_BLOB()

        ok = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(out_blob),
        )
        if not ok:
            raise OSError("DPAPI 解密失败，数据可能由其他用户加密或已损坏")

        plain = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
        return plain.decode("utf-8")
    if token.startswith("b64:"):
        return base64.b64decode(token[4:].encode("ascii")).decode("utf-8")
    return token
