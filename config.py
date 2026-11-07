import json
import os
import re
import tempfile
from typing import Any, Dict

import secure_storage

CONFIG_VERSION = 1


DEFAULT_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks")
SENSITIVE_KEYS = ("cookie", "proxy", "proxy_single")
# api_config 中的这两个子树可能携带 Authorization / X-API-Key / token 等凭证，
# 整体按敏感数据处理，避免明文写入任务 JSON（M-2 修复）
API_SENSITIVE_SUBKEYS = ("headers", "body")

# 任务名允许使用的字符：字母、数字、中文、下划线、中划线、点、空格
# 其他字符会替换为下划线；路径分隔符和 .. 明确禁止
_SAFE_NAME_RE = re.compile(r"^[\w\u4e00-\u9fa5\-. ]+$", re.UNICODE)
_INVALID_NAME_RE = re.compile(r"[\\/:*?\"<>|]|\.\.", re.UNICODE)


class ConfigError(Exception):
    """配置操作异常"""
    pass


def ensure_config_dir():
    os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)


def _sanitize_name(name: str) -> str:
    """把任务名处理为安全的文件名。"""
    if not name or not isinstance(name, str):
        raise ConfigError("任务名不能为空")
    name = name.strip()
    if not name:
        raise ConfigError("任务名不能为空")
    # 直接拒绝包含危险字符或 .. 的名字
    if _INVALID_NAME_RE.search(name):
        raise ConfigError(f"任务名包含非法字符: {name}")
    if not _SAFE_NAME_RE.match(name):
        # 将不允许的字符替换为下划线，再次检查
        sanitized = re.sub(r"[^\w\u4e00-\u9fa5\-. ]", "_", name, flags=re.UNICODE)
        sanitized = sanitized.strip(" ._")
        if not sanitized:
            raise ConfigError(f"任务名不合法: {name}")
        return sanitized
    return name


def _task_path(name: str) -> str:
    safe = _sanitize_name(name)
    ensure_config_dir()
    return os.path.join(DEFAULT_CONFIG_DIR, f"{safe}.json")


def save_task(name: str, task: Dict[str, Any]):
    path = _task_path(name)
    to_save = dict(task)
    to_save.setdefault("config_version", CONFIG_VERSION)
    # 默认不保存 Cookie；如明确选择保存，则加密存储
    if not to_save.get("save_cookie"):
        to_save["cookie"] = ""
    def protect(value, sensitive=False):
        if isinstance(value, dict):
            protected = {}
            for key, item in value.items():
                if key == "api_config" and isinstance(item, dict):
                    # M-2 修复：api_config 的 headers/body 可能包含 API 凭证，
                    # 必须加密存储；其余分页配置不含敏感信息，保持明文
                    protected[key] = {
                        sub: protect(subval, sensitive=(sub in API_SENSITIVE_SUBKEYS))
                        for sub, subval in item.items()
                    }
                else:
                    protected[key] = protect(
                        item,
                        sensitive=(sensitive or key in SENSITIVE_KEYS or key == "proxy_pool"),
                    )
            return protected
        if isinstance(value, list):
            return [secure_storage.encrypt(v) if sensitive and isinstance(v, str) else protect(v, sensitive) for v in value]
        return secure_storage.encrypt(value) if sensitive and isinstance(value, str) else value
    to_save = protect(to_save)
    # Write and replace atomically so an interruption cannot leave invalid JSON.
    directory = os.path.dirname(path)
    fd, temp_path = tempfile.mkstemp(prefix=".task-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _decrypt_tree(value):
    """递归解密 headers/body 子树；非 token 字符串原样返回（兼容旧明文任务）。"""
    if isinstance(value, dict):
        return {k: _decrypt_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decrypt_tree(v) for v in value]
    return secure_storage.decrypt(value) if isinstance(value, str) else value


def load_task(name: str) -> Dict[str, Any]:
    path = _task_path(name)
    with open(path, "r", encoding="utf-8") as f:
        task = json.load(f)
    for key in SENSITIVE_KEYS:
        if key in task and task[key]:
            try:
                task[key] = secure_storage.decrypt(task[key])
            except Exception as exc:
                raise ConfigError("敏感数据解密失败，请在当前 Windows 用户下重新输入") from exc
    if isinstance(task.get("proxy_pool"), list):
        try:
            task["proxy_pool"] = [secure_storage.decrypt(value) if isinstance(value, str) else value for value in task["proxy_pool"]]
        except Exception as exc:
            raise ConfigError("敏感数据解密失败，请在当前 Windows 用户下重新输入") from exc
    # M-2 修复：解密 api_config.headers/body 中加密的凭证
    api_cfg = task.get("api_config")
    if isinstance(api_cfg, dict):
        for key in API_SENSITIVE_SUBKEYS:
            if isinstance(api_cfg.get(key), (dict, list)):
                try:
                    api_cfg[key] = _decrypt_tree(api_cfg[key])
                except Exception as exc:
                    raise ConfigError("敏感数据解密失败，请在当前 Windows 用户下重新输入") from exc
    task.setdefault("config_version", 1)
    return task


def list_tasks() -> list:
    ensure_config_dir()
    names = []
    for f in os.listdir(DEFAULT_CONFIG_DIR):
        if f.endswith(".json"):
            names.append(f[:-5])
    return names
