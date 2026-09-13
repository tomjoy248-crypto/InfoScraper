"""敏感数据安全存储。

Windows 下使用 DPAPI（Data Protection API）加密当前用户可解密的数据；
其他平台由于没有统一的系统级密钥保护机制，回退到 base64 编码（不加密），
并给出警告。
"""

import base64
import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform.startswith("win")


def _blob(data: bytes):
    """构造 Windows DATA_BLOB 结构。"""
    class DATA_BLOB:
        _fields_ = [("cbData", "uint32"), ("pbData", "pointer")]

    import ctypes

    blob = DATA_BLOB()
    blob.cbData = len(data)
    if data:
        blob.pbData = ctypes.cast(ctypes.create_string_buffer(data), ctypes.c_void_p)
    else:
        blob.pbData = None
    return blob


def encrypt(value: Optional[str]) -> Optional[str]:
    """加密字符串，返回 base64 编码的 token；输入为空则直接返回空。"""
    if not value:
        return value
    raw = value.encode("utf-8")
    if not _IS_WINDOWS:
        logger.warning("非 Windows 平台，敏感数据仅做 base64 编码，未加密")
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
