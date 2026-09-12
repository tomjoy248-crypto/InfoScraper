import re
from typing import Dict, List


CLEAN_RULES = {
    "strip": lambda v: v.strip(),
    "remove_space": lambda v: re.sub(r"\s+", "", v),
    "to_lower": lambda v: v.lower(),
    "to_upper": lambda v: v.upper(),
    "remove_html": lambda v: re.sub(r"<[^>]+>", "", v),
    "extract_number": lambda v: "".join(re.findall(r"\d+\.?\d*", v)),
    "extract_phone": lambda v: "".join(re.findall(r"1[3-9]\d{9}", v)),
    "extract_email": lambda v: ", ".join(re.findall(r"[\w.-]+@[\w.-]+\.\w+", v)),
}


def apply_clean_rules(data: List[Dict[str, str]], field_rules: Dict[str, List[str]]) -> List[Dict[str, str]]:
    """对数据应用清洗规则。

    field_rules: {字段名: [规则名, ...]}
    """
    result = []
    for row in data:
        new_row = dict(row)
        for field, rules in field_rules.items():
            if field not in new_row:
                continue
            value = new_row[field]
            for rule in rules:
                if rule in CLEAN_RULES:
                    value = CLEAN_RULES[rule](value)
            new_row[field] = value
        result.append(new_row)
    return result
