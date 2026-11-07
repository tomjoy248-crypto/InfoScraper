"""轻量级 JSONPath 解析器。

支持语法：
- $ 或留空：根对象
- .child 或 ['child']：对象属性访问（支持中文、连字符等键名）
- ..child：递归下降查找
- [n]：数组索引
- [*]：数组全部元素（对象表示所有值）
- [?(@.key op value)]：过滤表达式

过滤表达式支持：==、!=、>、<、>=、<=，值支持数字、字符串（单/双引号）、true/false/null。

返回结果始终为 list，便于统一处理。
"""

import re
from typing import Any, List, Optional, Tuple


class JSONPathError(Exception):
    pass


_TOKEN_SPEC = [
    ("ROOT", r"\$"),
    ("RECURSIVE", r"\.\."),
    ("DOT", r"\."),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("RPAREN", r"\)"),
    ("WILDCARD", r"\*"),
    ("FILTER", r"\?\s*\("),
    ("AT", r"@"),
    ("STRING", r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\""),
    # 数字后不能紧跟 word/连字符字符，避免吞掉 "3d" 这类键名
    ("NUMBER", r"-?\d+(?:\.\d+)?(?![\w\-])"),
    ("BOOL", r"\b(?:true|false|null)\b"),
    # 属性名支持中文、连字符，甚至以数字开头（如 "3d"）
    ("IDENT", r"[\w\-]+"),
    ("CMP", r"==|!=|>=|<=|>|<"),
    ("WS", r"\s+"),
]
_TOKEN_RE = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC))


def _tokenize(path: str) -> List[Tuple[str, Any]]:
    path = path.strip()
    if not path or path == "$":
        return []
    # 只剥掉根标记 $，保留后面的语法（如 ..name 的递归下降）
    if path.startswith("$"):
        path = path[1:]
    tokens = []
    pos = 0
    while pos < len(path):
        m = _TOKEN_RE.match(path, pos)
        if not m:
            raise JSONPathError(f"JSONPath 无法解析，位置 {pos}: {path[pos:]!r}")
        kind = m.lastgroup
        value = m.group()
        pos = m.end()
        if kind == "WS":
            continue
        if kind == "STRING":
            value = value[1:-1]
        elif kind == "NUMBER":
            value = float(value) if "." in value else int(value)
        elif kind == "BOOL":
            if value == "true":
                value = True
            elif value == "false":
                value = False
            else:
                value = None
        tokens.append((kind, value))
    return tokens


def _walk(node: Any, tokens: List[Tuple[str, Any]], idx: int = 0) -> Tuple[List[Any], int]:
    """递归遍历 JSON 数据，返回 (结果列表, 下一个 token 索引)。"""
    if idx >= len(tokens):
        return [node], idx

    kind, value = tokens[idx]

    if kind == "DOT":
        if idx + 1 >= len(tokens):
            raise JSONPathError("JSONPath 语法错误：点后缺少属性名")
        next_kind, next_value = tokens[idx + 1]
        if next_kind not in ("IDENT", "STRING"):
            raise JSONPathError(f"JSONPath 语法错误：点后应为属性名，得到 {next_kind}")
        if isinstance(node, dict) and next_value in node:
            return _walk(node[next_value], tokens, idx + 2)
        return [], idx + 2

    if kind == "RECURSIVE":
        if idx + 1 >= len(tokens):
            raise JSONPathError("JSONPath 语法错误：.. 后缺少属性名")
        next_kind, next_value = tokens[idx + 1]
        if next_kind not in ("IDENT", "STRING"):
            raise JSONPathError(f"JSONPath 语法错误：.. 后应为属性名，得到 {next_kind}")
        collected = []
        _collect_recursive(node, next_value, collected)
        if not collected:
            return [], idx + 2
        results = []
        for item in collected:
            sub_results, _ = _walk(item, tokens, idx + 2)
            results.extend(sub_results)
        return results, len(tokens)

    if kind == "LBRACKET":
        if idx + 1 >= len(tokens):
            raise JSONPathError("JSONPath 语法错误：[ 后缺少内容")
        inner_kind, inner_value = tokens[idx + 1]

        # 通配符 [*]
        if inner_kind == "WILDCARD":
            if idx + 2 >= len(tokens) or tokens[idx + 2][0] != "RBRACKET":
                raise JSONPathError("JSONPath 语法错误：缺少 ]")
            if isinstance(node, list):
                items = node
            elif isinstance(node, dict):
                items = list(node.values())
            else:
                return [], idx + 3
            results = []
            for item in items:
                sub_results, _ = _walk(item, tokens, idx + 3)
                results.extend(sub_results)
            return results, len(tokens)

        # 过滤 [?(@.key op value)]
        if inner_kind == "FILTER":
            f_idx = idx + 2
            if f_idx >= len(tokens) or tokens[f_idx][0] != "AT":
                raise JSONPathError("JSONPath 过滤表达式必须以 @ 开头")
            f_idx += 1
            if f_idx >= len(tokens) or tokens[f_idx][0] != "DOT":
                raise JSONPathError("JSONPath 过滤表达式格式错误")
            f_idx += 1
            if f_idx >= len(tokens) or tokens[f_idx][0] not in ("IDENT", "STRING"):
                raise JSONPathError("JSONPath 过滤表达式缺少字段名")
            field = tokens[f_idx][1]
            f_idx += 1
            if f_idx >= len(tokens) or tokens[f_idx][0] != "CMP":
                raise JSONPathError("JSONPath 过滤表达式缺少比较运算符")
            op = tokens[f_idx][1]
            f_idx += 1
            if f_idx >= len(tokens):
                raise JSONPathError("JSONPath 过滤表达式缺少比较值")
            cmp_value = tokens[f_idx][1]
            f_idx += 1
            # 可选的闭括号 )：形如 [?(@.key == 'v')]
            if f_idx < len(tokens) and tokens[f_idx][0] == "RPAREN":
                f_idx += 1
            if f_idx >= len(tokens) or tokens[f_idx][0] != "RBRACKET":
                raise JSONPathError("JSONPath 过滤表达式缺少 ]")

            if isinstance(node, list):
                results = []
                for item in node:
                    if _evaluate_filter(item, field, op, cmp_value):
                        sub_results, _ = _walk(item, tokens, f_idx + 1)
                        results.extend(sub_results)
                return results, len(tokens)
            return [], f_idx + 1

        # 索引或对象键
        if inner_kind in ("NUMBER", "STRING"):
            if idx + 2 >= len(tokens) or tokens[idx + 2][0] != "RBRACKET":
                raise JSONPathError("JSONPath 语法错误：缺少 ]")
            if isinstance(node, list) and isinstance(inner_value, int):
                if 0 <= inner_value < len(node):
                    return _walk(node[inner_value], tokens, idx + 3)
                return [], idx + 3
            if isinstance(node, dict):
                if inner_value in node:
                    return _walk(node[inner_value], tokens, idx + 3)
                return [], idx + 3
            return [], idx + 3

        raise JSONPathError(f"JSONPath 语法错误：[ 后不支持的 token: {inner_kind}")

    if kind == "IDENT":
        if isinstance(node, dict) and value in node:
            return _walk(node[value], tokens, idx + 1)
        return [], idx + 1

    raise JSONPathError(f"JSONPath 语法错误：意外的 token {kind}({value})")


def _collect_recursive(node: Any, target: str, collected: List[Any]):
    """递归收集所有名为 target 的属性。"""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == target:
                collected.append(v)
            _collect_recursive(v, target, collected)
    elif isinstance(node, list):
        for item in node:
            _collect_recursive(item, target, collected)


def _evaluate_filter(item: Any, field: str, op: str, cmp_value: Any) -> bool:
    if not isinstance(item, dict):
        return False
    actual = item.get(field)
    try:
        if op == "==":
            return actual == cmp_value
        if op == "!=":
            return actual != cmp_value
        if actual is None or cmp_value is None:
            return False
        if op == ">":
            return actual > cmp_value
        if op == "<":
            return actual < cmp_value
        if op == ">=":
            return actual >= cmp_value
        if op == "<=":
            return actual <= cmp_value
    except TypeError:
        return False
    return False


def query(data: Any, path: Optional[str]) -> List[Any]:
    """对 data 执行 JSONPath 查询，返回匹配项列表。"""
    if path is None or path.strip() == "":
        return [data]
    tokens = _tokenize(path)
    if not tokens:
        return [data]
    results, _ = _walk(data, tokens)
    return results
