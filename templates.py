from typing import Dict


TEMPLATES: Dict[str, Dict] = {
    "person_info": {
        "name": "人物信息",
        "description": "适用于人物主页、简历页、社交资料等",
        "url": "",
        "mode": "static",
        "selector_type": "css",
        "list_selector": ".person-item",
        "cookie": "",
        "ua": "",
        "max_pages": 1,
        "page_mode": "none",
        "page_selector": "page",
        "page_step": 1,
        "fields": [
            {"name": "姓名", "selector": ".name", "attr": None},
            {"name": "职位", "selector": ".title", "attr": None},
            {"name": "公司", "selector": ".company", "attr": None},
            {"name": "邮箱", "selector": ".email", "attr": None},
            {"name": "电话", "selector": ".phone", "attr": None},
            {"name": "个人链接", "selector": "a.profile", "attr": "href"},
        ],
        "random_ua": True,
        "render": False,
        "retries": 2,
        "delay": 1.0,
        "delay_random": True,
    },
    "product_info": {
        "name": "商品信息",
        "description": "适用于电商、商品列表页",
        "url": "",
        "mode": "static",
        "selector_type": "css",
        "list_selector": ".product-item",
        "cookie": "",
        "ua": "",
        "max_pages": 1,
        "page_mode": "none",
        "page_selector": "page",
        "page_step": 1,
        "fields": [
            {"name": "商品名", "selector": ".title", "attr": None},
            {"name": "价格", "selector": ".price", "attr": None},
            {"name": "原价", "selector": ".original-price", "attr": None},
            {"name": "销量", "selector": ".sales", "attr": None},
            {"name": "店铺", "selector": ".shop", "attr": None},
            {"name": "商品链接", "selector": "a", "attr": "href"},
            {"name": "图片链接", "selector": "img", "attr": "src"},
        ],
        "random_ua": True,
        "render": False,
        "retries": 2,
        "delay": 1.0,
        "delay_random": True,
    },
    "news_list": {
        "name": "新闻列表",
        "description": "适用于新闻站、博客列表",
        "url": "",
        "mode": "static",
        "selector_type": "css",
        "list_selector": "article",
        "cookie": "",
        "ua": "",
        "max_pages": 1,
        "page_mode": "none",
        "page_selector": "page",
        "page_step": 1,
        "fields": [
            {"name": "标题", "selector": "h2", "attr": None},
            {"name": "摘要", "selector": ".summary", "attr": None},
            {"name": "发布时间", "selector": ".time", "attr": None},
            {"name": "作者", "selector": ".author", "attr": None},
            {"name": "链接", "selector": "a", "attr": "href"},
        ],
        "random_ua": True,
        "render": False,
        "retries": 2,
        "delay": 0.5,
        "delay_random": True,
    },
}


def get_template_names() -> list:
    return [(k, v["name"], v["description"]) for k, v in TEMPLATES.items()]


def get_template(key: str) -> Dict:
    return TEMPLATES.get(key, {})
