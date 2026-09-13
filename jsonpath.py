"""轻量级 JSONPath 解析器。

支持常见语法：
- $ 或留空：根对象
- $.data.items 或 data.items：对象属性访问
- $.data.items[*]：取列表全部元素
- $.data.items[0]：取列表指定索引
- $.data.items[*].name：取列表元素的字段

返回结果始终为 list，便于统一处理。
"""

import re
from typing import Any, List, Optional

_TOKEN_RE = re.compile(r"\.|\[|\]|\*|[0-9]+|[a-zA-Z_][a-zA-Z0-9_]*")


class JSONPathError(Exception):
    pass


def _tokenize(path: str) -> List[str]:
    path = path.strip()
    if not path or path == "$":
        return []
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]
    tokens = _TOKEN_RE.findall(path)
    return tokens


def _walk(node: Any, tokens: List[str]) -> List[Any]:
    if not tokens:
        return [node]

    current = [node]
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        next_tok = tokens[i + 1] if i + 1 < len(tokens) else None

        if tok == ".":
            i += 1
            continue

        if tok == "[":
            if next_tok is None:
                raise JSONPathError("JSONPath 语法错误：缺少 ]")
            index_tok = next_tok
            i += 2  # skip '[' and index
            if i >= len(tokens) or tokens[i] != "]":
                raise JSONPathError("JSONPath 语法错误：缺少 ]")
            i += 1  # skip ']'

            new_current = []
            for item in current:
                if isinstance(item, list):
                    if index_tok == "*":
                        new_current.extend(item)
                    else:
                        try:
                            idx = int(index_tok)
                            if 0 <= idx < len(item):
                                new_current.append(item[idx])
                        except ValueError:
                            raise JSONPathError(f"非法索引: {index_tok}")
                elif isinstance(item, dict):
                    # 形如 obj[key] 的对象键访问
                    new_current.append(item.get(index_tok))
            current = new_current
            continue

        # 属性名
        new_current = []
        for item in current:
            if isinstance(item, dict) and tok in item:
                new_current.append(item[tok])
        current = new_current
        i += 1

    return current


def query(data: Any, path: Optional[str]) -> List[Any]:
    """对 data 执行 JSONPath 查询，返回匹配项列表。"""
    if path is None or path.strip() == "":
        return [data]
    tokens = _tokenize(path)
    return _walk(data, tokens)
